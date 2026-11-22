from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Person, ProductSystem
from ecosemantic.view.app import build_view
from tests.conftest import fixture_system
from tests.view.test_tables import rezipped

ANA = Person(id="a", name="Ana")

STORED = {"kind": "person", "id": "a", "name": "Ana"}


@pytest.fixture(scope="module")
def store(bundle_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[ServerContext]:
    built = build_context(bundle_dir, tmp_path_factory.mktemp("person-systems"))
    yield built
    built.close()


@pytest.fixture(scope="module")
async def stored(store: ServerContext) -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    system.id = uuid.uuid5(system.id, "person")
    system.name = "widget_person"
    await store.storage.put_product_system(system, store.actor, "created")
    return system


@pytest.fixture(scope="module")
def client(store: ServerContext) -> Iterator[TestClient]:
    view = build_view(
        store.for_person(ANA), build_server(store), static=Path("/nonexistent-static")
    )
    with TestClient(view) as served:
        yield served


def test_a_request_names_the_signed_in_person(client: TestClient, stored: ProductSystem) -> None:
    base = f"/api/product-systems/{stored.id}"
    current = client.get(base).json()["value"]["hash"]
    posted = client.post(
        f"{base}/requests",
        json={"actor": "Mallory", "kind": "return", "at_hash": current, "message": "too heavy"},
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["actor"] == STORED


def test_returned_tables_name_the_signed_in_person(
    client: TestClient, stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{stored.id}"
    downloaded = client.get(f"{base}/tables.zip").content
    grown = zipfile.ZipFile(io.BytesIO(downloaded)).read("inputs/input_parameters.csv")
    response = client.post(
        f"{base}/tables",
        files={
            "tables": (
                "tables.zip",
                rezipped(
                    downloaded,
                    "inputs/input_parameters.csv",
                    grown + b"person_marker,0.8,,\n",
                ),
                "application/zip",
            )
        },
        data={"actor": "Mallory"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["actor"] == STORED


def test_a_returned_package_names_the_signed_in_person(
    client: TestClient, stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{stored.id}"
    downloaded = client.get(f"{base}/package.zip").content
    zipped = zipfile.ZipFile(io.BytesIO(downloaded))
    process = next(name for name in zipped.namelist() if name.startswith("processes/"))
    document = json.loads(zipped.read(process))
    document["description"] = "returned by a person"
    returned = io.BytesIO()
    with zipfile.ZipFile(returned, "w") as out:
        for name in zipped.namelist():
            out.writestr(name, json.dumps(document) if name == process else zipped.read(name))
    response = client.post(
        f"{base}/return",
        files={"package": ("export.zip", returned.getvalue(), "application/zip")},
        data={"actor": "Mallory"},
    )
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["actor"] == STORED
    assert any(change["after"] == "returned by a person" for change in entry["changes"])
