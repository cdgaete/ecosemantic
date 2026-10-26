from __future__ import annotations

import io
import json
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import ProductSystem
from ecosemantic.view import handling
from ecosemantic.view.app import build_view
from tests.conftest import frame_system


@pytest.fixture(scope="module")
def client(context: ServerContext, full_server: FastMCP) -> Iterator[TestClient]:
    with TestClient(build_view(context, full_server, static=Path("/nonexistent-static"))) as c:
        yield c


def test_the_package_downloads_and_returns(
    client: TestClient, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    downloaded = client.get(f"{base}/package.zip")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    zipped = zipfile.ZipFile(io.BytesIO(downloaded.content))
    names = zipped.namelist()
    process_name = next(n for n in names if n.startswith("processes/"))
    document = json.loads(zipped.read(process_name))
    document["description"] = "checked in openLCA"
    returned = io.BytesIO()
    with zipfile.ZipFile(returned, "w") as out:
        for name in names:
            out.writestr(name, json.dumps(document) if name == process_name else zipped.read(name))
    log_before = len(client.get(f"{base}/log").json()["value"])
    response = client.post(
        f"{base}/return",
        files={"package": ("export.zip", returned.getvalue(), "application/zip")},
        data={"actor": "Carlos"},
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["source"] == "openlca" and entry["actor"]["name"] == "Carlos"
    assert len(client.get(f"{base}/log").json()["value"]) == log_before + 1
    assert any(c["after"] == "checked in openLCA" for c in entry["changes"])


def test_a_failed_export_leaves_no_temp_directory(
    context: ServerContext,
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("ecosemantic.view.olca.export_model_package", _boom)
    app = build_view(context, full_server, static=Path("/nonexistent-static"))
    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get(f"/api/product-systems/{fixture_system_stored.id}/package.zip")
    assert response.status_code == 500
    assert list(tmp_path.iterdir()) == []


def _zipped(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, body in entries.items():
            out.writestr(name, body)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("limit", "value", "upload", "message"),
    [
        (
            "UPLOAD_BYTES",
            100,
            b"x" * 101,
            "the exported zip is 101 bytes; an upload holds at most 100",
        ),
        ("UPLOAD_BYTES", 10**8, b"not a zip", "the exported zip is not a zip file"),
        (
            "UNPACKED_BYTES",
            1000,
            _zipped({"a.json": b"0" * 600, "b.json": b"0" * 600}),
            "the exported zip unpacks to 1200 bytes; an upload unpacks to at most 1000",
        ),
        (
            "UNPACKED_ENTRIES",
            2,
            _zipped({"a.json": b"{}", "b.json": b"{}", "c.json": b"{}"}),
            "the exported zip holds 3 entries; an upload holds at most 2",
        ),
    ],
    ids=["uploaded", "not-a-zip", "unpacked", "entries"],
)
def test_an_upload_past_a_limit_is_refused_before_it_is_unpacked(
    client: TestClient,
    fixture_system_stored: ProductSystem,
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
    value: int,
    upload: bytes,
    message: str,
) -> None:
    unpacked: list[Path] = []
    monkeypatch.setattr(handling, limit, value)
    monkeypatch.setattr(handling, "unzip_package", lambda zipped, root: unpacked.append(root))
    response = client.post(
        f"/api/product-systems/{fixture_system_stored.id}/return",
        files={"package": ("export.zip", upload, "application/zip")},
        data={"actor": "Carlos"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid"
    assert response.json()["message"] == message
    assert unpacked == []


def test_an_upload_at_each_limit_returns(
    client: TestClient, fixture_system_stored: ProductSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    downloaded = client.get(f"{base}/package.zip").content
    entries = zipfile.ZipFile(io.BytesIO(downloaded)).infolist()
    monkeypatch.setattr(handling, "UPLOAD_BYTES", len(downloaded))
    monkeypatch.setattr(handling, "UNPACKED_BYTES", sum(e.file_size for e in entries))
    monkeypatch.setattr(handling, "UNPACKED_ENTRIES", len(entries))
    response = client.post(
        f"{base}/return",
        files={"package": ("export.zip", downloaded, "application/zip")},
        data={"actor": "Carlos"},
    )
    assert response.status_code == 201, response.text


def test_the_limits_are_100_mb_uploaded_1_gb_unpacked_and_100000_entries() -> None:
    assert (handling.UPLOAD_BYTES, handling.UNPACKED_BYTES, handling.UNPACKED_ENTRIES) == (
        100_000_000,
        1_000_000_000,
        100_000,
    )


async def test_a_return_after_a_later_write_is_refused_until_a_state_is_stated(
    client: TestClient, context: ServerContext
) -> None:
    frame = frame_system().model_copy(update={"id": uuid.uuid4()})
    await context.storage.put_product_system(frame, context.actor, "created")
    base = f"/api/product-systems/{frame.id}"
    downloaded = client.get(f"{base}/package.zip").content
    stored = await context.storage.get_product_system(frame.id)
    heavier = stored.model_copy(deep=True)
    heavier.processes[0].exchanges[1].amount *= 2
    await context.storage.put_product_system(heavier, context.actor, "heavier frame")
    package = {"package": ("export.zip", downloaded, "application/zip")}
    refused = client.post(f"{base}/return", files=package, data={"actor": "Carlos"})
    assert refused.status_code == 409
    assert "#2 heavier frame" in refused.json()["message"]
    unstated = client.post(
        f"{base}/return", files=package, data={"actor": "Carlos", "at_entry": ""}
    )
    assert unstated.status_code == 409
    worded = client.post(
        f"{base}/return", files=package, data={"actor": "Carlos", "at_entry": "two"}
    )
    assert worded.status_code == 400 and "at_entry" in worded.json()["message"]
    superscript = client.post(
        f"{base}/return", files=package, data={"actor": "Carlos", "at_entry": "²"}
    )
    assert superscript.status_code == 400 and "at_entry" in superscript.json()["message"]
    returned = client.post(
        f"{base}/return", files=package, data={"actor": "Carlos", "at_entry": "2"}
    )
    assert returned.status_code == 201 and returned.json()["seq"] == 3
