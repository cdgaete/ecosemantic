"""The page's installs, accounts and downloads for a context that names a person."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Person, ProductSystem
from ecosemantic.ports.types import Account
from ecosemantic.view.app import build_view
from tests.conftest import fixture_system
from tests.mcp.test_host import hosted
from tests.view.test_installs import OPENLCA, zipped

NOWHERE = Path("/nonexistent-static")
LOOPBACK = ("127.0.0.1", 50000)
ANA = Person(id="a", name="Ana")
ACCOUNT = Account(username="me", password=SecretStr("hunter2"))
CREDENTIAL = {"username": "me", "password": "hunter2"}


@pytest.fixture
def store(bundle_dir: Path, tmp_path: Path) -> Iterator[ServerContext]:
    """A store of this test's own over the fixture database, the installs held in memory."""
    (tmp_path / "systems").mkdir()
    built = hosted(build_context(bundle_dir, tmp_path / "systems"), tmp_path)
    yield built
    built.close()


@pytest.fixture
async def stored(store: ServerContext) -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    await store.storage.put_product_system(system, store.actor, "created")
    return system


def test_an_openlca_upload_is_refused_before_a_byte_is_stored(store: ServerContext) -> None:
    person = store.for_person(ANA)
    with TestClient(build_view(person, build_server(store), static=NOWHERE)) as client:
        posted = client.post(
            "/api/installs/openlca",
            files={"file": ("database.zip", zipped(), "application/zip")},
            data=OPENLCA,
        )
    assert posted.status_code == 501, posted.text
    assert posted.json()["error"] == "not_supported"
    assert not person.uploads_dir.exists()


def test_a_person_reads_enters_and_clears_no_account(store: ServerContext) -> None:
    over = dataclasses.replace(store, credentials={"ecoinvent": ACCOUNT})
    view = build_view(over.for_person(ANA), build_server(over), static=NOWHERE)
    with TestClient(view, client=LOOPBACK) as client:
        answered = [
            client.get("/api/credentials"),
            client.put("/api/credentials/ecoinvent", json=CREDENTIAL),
            client.delete("/api/credentials/ecoinvent"),
        ]
    assert [response.status_code for response in answered] == [501] * 3
    assert [response.json()["error"] for response in answered] == ["not_supported"] * 3
    assert over.credentials == {"ecoinvent": ACCOUNT}


def test_the_page_s_downloads_serve_a_person(store: ServerContext, stored: ProductSystem) -> None:
    base = f"/api/product-systems/{stored.id}"
    view = build_view(store.for_person(ANA), build_server(store), static=NOWHERE)
    with TestClient(view) as client:
        assert client.get(f"{base}/tables.zip").status_code == 200
        assert client.get(f"{base}/package.zip").status_code == 200
