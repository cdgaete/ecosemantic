from __future__ import annotations

import dataclasses
import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastmcp import FastMCP
from starlette.testclient import TestClient

from ecosemantic.cli import main
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Method, ProductSystem, method_id
from ecosemantic.view.app import build_view
from tests.fixture_data import CODES, GWP
from tests.memory_background import MemoryInventory

GWP_ID = method_id(" > ".join(GWP))


@pytest.fixture(scope="module")
def client(context: ServerContext, full_server: FastMCP) -> Iterator[TestClient]:
    with TestClient(build_view(context, full_server, static=Path("/nonexistent-static"))) as c:
        yield c


def rezipped(downloaded: bytes, member: str, body: bytes) -> bytes:
    """The downloaded zip with one member's bytes replaced."""
    source = zipfile.ZipFile(io.BytesIO(downloaded))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name in source.namelist():
            out.writestr(name, body if name == member else source.read(name))
    return buffer.getvalue()


def test_the_folder_downloads_as_a_zip(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.get(f"/api/product-systems/{fixture_system_stored.id}/tables.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert "model.yaml" in names
    assert "inputs/schema.yaml" in names
    assert "inputs/cases.csv" in names


def test_an_added_parameter_posts_back_and_the_log_names_the_channel(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    downloaded = client.get(f"{base}/tables.zip").content
    grown = zipfile.ZipFile(io.BytesIO(downloaded)).read("inputs/input_parameters.csv")
    response = client.post(
        f"{base}/tables",
        files={
            "tables": (
                "tables.zip",
                rezipped(downloaded, "inputs/input_parameters.csv", grown + b"load_factor,0.8,,\n"),
                "application/zip",
            )
        },
        data={"actor": "a person"},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "tables"


def test_a_post_without_the_form_field_is_refused(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.post(f"/api/product-systems/{fixture_system_stored.id}/tables", data={})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid"


def test_an_impact_run_folder_downloads_as_a_zip(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.post(
        f"/api/product-systems/{fixture_system_stored.id}/impact.zip",
        json={"method_id": GWP_ID},
    )
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert any(name.endswith("schema.yaml") for name in names)
    assert any(name.endswith("scores.csv") for name in names)


def test_contributions_answer_a_run_folder(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.post(
        f"/api/product-systems/{fixture_system_stored.id}/contributions.zip",
        json={"method_id": GWP_ID},
    )
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert any(name.endswith("contributions.csv") for name in names)


def test_the_inventory_answers_a_run_folder(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.post(
        f"/api/product-systems/{fixture_system_stored.id}/inventory.zip", json={}
    )
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert any(name.endswith("inventory.csv") for name in names)


def test_each_run_folder_names_a_positive_input_to_a_treatment(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    # the fixture background holds no treatment, so steel stands for one
    treating = dataclasses.replace(context, inventory=MemoryInventory({CODES["steel"]}))
    view = build_view(treating, build_server(treating), static=Path("/nonexistent-static"))
    base = f"/api/product-systems/{fixture_system_stored.id}"
    named = ["frame · steel at 2.4", "widget · steel at 0.5"]
    with TestClient(view) as client:
        for table, body in (
            ("impact", {"method_id": GWP_ID}),
            ("contributions", {"method_id": GWP_ID}),
            ("inventory", {}),
        ):
            response = client.post(f"{base}/{table}.zip", json=body)
            assert response.status_code == 200
            zipped = zipfile.ZipFile(io.BytesIO(response.content))
            [schema] = [n for n in zipped.namelist() if n.endswith("schema.yaml")]
            assert yaml.safe_load(zipped.read(schema))["treatments_run_backwards"] == named


def test_an_impact_call_naming_no_method_arrives_as_the_envelope(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    response = client.post(f"/api/product-systems/{fixture_system_stored.id}/impact.zip", json={})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid"


def test_a_zip_route_answers_a_tool_failing_its_own_validation_as_an_envelope(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    probe = FastMCP("probe")

    @probe.tool(name="calculate_impact")
    def broken(product_system_id: str) -> str:
        Method.model_validate({})
        return "unreachable"

    app = build_view(context, probe, static=Path("/nonexistent-static"))
    with TestClient(app, raise_server_exceptions=False) as probing:
        base = f"/api/product-systems/{fixture_system_stored.id}"
        plain = probing.post(f"{base}/impact", json={})
        zipped = probing.post(f"{base}/impact.zip", json={})
    assert plain.status_code == 400 and plain.json()["error"] == "invalid"
    assert zipped.status_code == 400 and zipped.json()["error"] == "invalid"


def test_the_page_and_the_command_record_one_key_for_one_calculation(
    client: TestClient,
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = client.post(
        f"/api/product-systems/{fixture_system_stored.id}/impact.zip",
        json={"method_id": GWP_ID},
    )
    zipped = zipfile.ZipFile(io.BytesIO(response.content))
    schema = next(name for name in zipped.namelist() if name.endswith("schema.yaml"))
    from_the_page = yaml.safe_load(zipped.read(schema))["key"]
    tables = client.get(f"/api/product-systems/{fixture_system_stored.id}/tables.zip")
    zipfile.ZipFile(io.BytesIO(tables.content)).extractall(tmp_path)
    folder = next(path.parent for path in tmp_path.rglob("model.yaml"))
    argv = [
        "compute",
        "--data-dir",
        str(bundle_dir),
        "--folder",
        str(folder),
        "--method",
        GWP_ID,
        "--json",
    ]
    assert main(argv) == 0
    run = Path(json.loads(capsys.readouterr().out)["folder"])
    from_the_command = yaml.safe_load((run / "schema.yaml").read_text())["key"]
    assert from_the_page == from_the_command
    # the demand a calculation defaulted to is the demand its key records
    assert from_the_page["demand"] == [
        {"ref": {"kind": "foreground", "code": "widget"}, "amount": 1.0}
    ]
