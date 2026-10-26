from __future__ import annotations

import dataclasses
import io
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastmcp import Client
from pydantic import SecretStr
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.ports.types import Account, InstallPatch, InstallTerms
from ecosemantic.view.app import build_view
from tests.mcp.test_installs import sources
from tests.memory_installs import MemoryInstaller, MemoryInstalls

NOWHERE = Path("/nonexistent-static")
ACCOUNTS = {
    "ecoinvent": Account(username="me", password=SecretStr("hunter2")),
    "nexus": Account(username="me", password=SecretStr("hunter2")),
}
Held = tuple[ServerContext, MemoryInstalls, MemoryInstaller]
Page = tuple[TestClient, ServerContext, MemoryInstalls, MemoryInstaller]
OPENLCA = {"name": "my database", "version": "2024", "system_model": "unit process"}


def zipped() -> bytes:
    """A zip file holding one entry, which is all the upload route reads of an openLCA package."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        out.writestr("processes/widget.json", "{}")
    return buffer.getvalue()


@pytest.fixture
def held(context: ServerContext, tmp_path: Path) -> Held:
    """The fixture's ports with the install doubles, both accounts held, and the uploads directory
    under a directory of this test's own."""
    installs = MemoryInstalls()
    installer = MemoryInstaller(sources())
    over = dataclasses.replace(
        context,
        installs=installs,
        installer=installer,
        credentials=dict(ACCOUNTS),
        data_dir=tmp_path,
        uploads_dir=tmp_path / "installs" / "uploads",
        watchers=set(),
    )
    return over, installs, installer


@pytest.fixture
def page(held: Held) -> Iterator[Page]:
    over, installs, installer = held
    with TestClient(build_view(over, build_server(over), static=NOWHERE)) as client:
        yield client, over, installs, installer


async def test_each_install_route_answers_what_its_tool_answers(page: Page) -> None:
    client, over, installs, installer = page
    async with Client(build_server(over)) as tools:
        listed = (await tools.call_tool("list_sources", {})).structured_content
        assert client.get("/api/sources").json() == listed
        posted = client.post("/api/installs", json={"source": "uslci"})
        assert posted.status_code == 200, posted.text
        install_id = posted.json()["value"]["id"]
        assert [str(record.id) for record in await installs.list_installs()] == [install_id]
        assert installer.started[0][0] == uuid.UUID(install_id)
        read = (await tools.call_tool("get_install", {"install_id": install_id})).structured_content
        assert client.get(f"/api/installs/{install_id}").json() == read
        every = (await tools.call_tool("list_installs", {})).structured_content
        assert client.get("/api/installs").json() == every
        stopped = await tools.call_tool("cancel_install", {"install_id": install_id})
        cancelled = client.post(f"/api/installs/{install_id}/cancel")
        assert cancelled.json() == stopped.structured_content
        assert cancelled.json()["value"]["cancel_requested"] is True


async def test_an_uploaded_database_posts_an_openlca_install_with_the_file(page: Page) -> None:
    client, over, installs, installer = page
    posted = client.post(
        "/api/installs/openlca",
        files={"file": ("database.zip", zipped(), "application/zip")},
        data={**OPENLCA, "replace": "true", "drop_unlinked": "false"},
    )
    assert posted.status_code == 200, posted.text
    draft = posted.json()["value"]["draft"]
    assert draft["source"] == "openlca"
    assert draft["name"] == OPENLCA["name"] and draft["version"] == OPENLCA["version"]
    assert draft["system_model"] == OPENLCA["system_model"]
    assert draft["replace"] is True and draft["drop_unlinked"] is False
    upload = Path(draft["package"])
    assert upload.parent == over.uploads_dir and upload.is_file()
    assert installer.started == [(uuid.UUID(posted.json()["value"]["id"]), None)]
    assert [record.id for record in await installs.list_installs()] == [
        uuid.UUID(posted.json()["value"]["id"])
    ]


async def test_an_upload_that_is_not_a_zip_is_refused_and_leaves_no_file(page: Page) -> None:
    client, over, installs, installer = page
    cut = zipped()[:40]
    for body in (b"not a zip at all", cut):
        refused = client.post(
            "/api/installs/openlca",
            files={"file": ("database.zip", body, "application/zip")},
            data=OPENLCA,
        )
        assert refused.status_code == 400, refused.text
        assert refused.json()["error"] == "invalid"
        assert "is not a zip file" in refused.json()["message"]
        assert list(over.uploads_dir.glob("*")) == []
    assert await installs.list_installs() == [] and installer.started == []


async def test_the_licence_route_serves_the_terms_file_of_an_install_stopped_at_its_terms(
    page: Page,
) -> None:
    client, over, installs, _installer = page
    posted = client.post("/api/installs", json={"source": "bafu", "accept_terms": False})
    assert posted.status_code == 200, posted.text
    install_id = uuid.UUID(posted.json()["value"]["id"])
    early = client.get(f"/api/installs/{install_id}/licence")
    assert early.status_code == 404 and early.json()["error"] == "not_found"
    terms = over.data_dir / "installs" / "bafu-terms.txt"
    terms.parent.mkdir(parents=True, exist_ok=True)
    terms.write_text("BAFU release terms\n", encoding="utf-8", newline="\n")
    installs.apply_patch(
        install_id,
        InstallPatch(
            status="terms",
            terms=InstallTerms(licence=str(terms), citation="BAFU 2.2, ecoinvent"),
            finished_at=datetime.now(UTC),
        ),
    )
    served = client.get(f"/api/installs/{install_id}/licence")
    assert served.status_code == 200, served.text
    assert served.text == "BAFU release terms\n"


async def test_an_uploaded_database_the_server_refuses_leaves_no_file(page: Page) -> None:
    client, over, installs, _installer = page
    assert client.post("/api/installs", json={"source": "uslci"}).status_code == 200
    refused = client.post(
        "/api/installs/openlca",
        files={"file": ("database.zip", zipped(), "application/zip")},
        data=OPENLCA,
    )
    assert refused.status_code == 409 and refused.json()["error"] == "conflict"
    assert list(over.uploads_dir.glob("*")) == []
    assert len(await installs.list_installs()) == 1


async def test_a_form_the_route_cannot_read_is_invalid_and_leaves_no_file(page: Page) -> None:
    client, over, _installs, _installer = page
    refused = [
        client.post("/api/installs/openlca", data=OPENLCA),
        client.post(
            "/api/installs/openlca",
            files={"file": ("database.zip", zipped(), "application/zip")},
            data={**OPENLCA, "replace": "maybe"},
        ),
    ]
    assert [(response.status_code, response.json()["error"]) for response in refused] == [
        (400, "invalid")
    ] * 2
    assert list(over.uploads_dir.glob("*")) == []
