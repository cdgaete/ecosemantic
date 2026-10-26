from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.compute.parameters import materialize
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.tables import apply_tables, result_key
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, ProductSystem
from tests.fixture_data import FIXTURE_DB


@pytest_asyncio.fixture
async def spaced_bottle(full_server: FastMCP, bottle: str) -> str:
    """A stored product system carrying two literal parameters and one case."""
    async with Client(full_server) as client:
        await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [
                    {"name": "transport_km", "value": 120.0, "unit": "km"},
                    {"name": "waste_rate", "value": 0.1},
                ],
                "cases": [{"name": "lean", "values": {"transport_km": 80.0}}],
            },
        )
    return bottle


async def test_export_tables_writes_the_folder_and_names_it(
    full_server: FastMCP, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "export_tables", {"product_system_id": spaced_bottle, "path": str(tmp_path)}
        )
    folder = Path(out.structured_content["value"]["path"])
    assert folder.name == f"bottle-{spaced_bottle[:8]}"
    assert (folder / "model.yaml").is_file()
    assert (folder / "inputs" / "cases.csv").is_file()


async def test_import_tables_writes_the_edited_space_and_names_the_channel(
    full_server: FastMCP, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "export_tables", {"product_system_id": spaced_bottle, "path": str(tmp_path)}
        )
        folder = Path(out.structured_content["value"]["path"])
        path = folder / "inputs" / "input_parameters.csv"
        path.write_text(
            path.read_text(encoding="utf-8").replace("transport_km,120.0", "transport_km,150.0"),
            encoding="utf-8",
        )
        written = await client.call_tool("import_tables", {"path": str(folder)})
        log = await client.call_tool("get_product_system_log", {"product_system_id": spaced_bottle})
    values = {p["name"]: p["value"] for p in written.structured_content["value"]["parameters"]}
    assert values["transport_km"] == 150.0
    assert log.structured_content["items"][-1]["source"] == "tables"


async def test_import_tables_refuses_a_system_the_store_does_not_hold(
    full_server: FastMCP, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "export_tables", {"product_system_id": spaced_bottle, "path": str(tmp_path)}
        )
        folder = Path(out.structured_content["value"]["path"])
        model = folder / "model.yaml"
        model.write_text(
            model.read_text(encoding="utf-8").replace(spaced_bottle, str(uuid.UUID(int=7))),
            encoding="utf-8",
        )
        with pytest.raises(ToolError, match="not_found"):
            await client.call_tool("import_tables", {"path": str(folder)})


async def test_export_tables_refuses_a_directory_that_does_not_exist(
    full_server: FastMCP, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        with pytest.raises(ToolError, match="invalid"):
            await client.call_tool(
                "export_tables",
                {"product_system_id": spaced_bottle, "path": str(tmp_path / "absent")},
            )


async def test_apply_tables_stores_the_space_for_the_actor_and_message_given(
    full_server: FastMCP, context: ServerContext, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "export_tables", {"product_system_id": spaced_bottle, "path": str(tmp_path)}
        )
    folder = Path(out.structured_content["value"]["path"])
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("transport_km,120.0", "transport_km,150.0"),
        encoding="utf-8",
    )
    person = Actor(kind="person", name="Ana")
    _, changed, entry = await apply_tables(
        context, uuid.UUID(spaced_bottle), folder, person, "returned tables"
    )
    assert changed.parameter("transport_km").value == 150.0
    assert entry.source == "tables" and entry.actor == person
    assert entry.message == "returned tables"


async def test_import_tables_refuses_to_drop_a_case_a_link_names(
    full_server: FastMCP, spaced_bottle: str, tmp_path: Path
) -> None:
    async with Client(full_server) as client:
        await client.call_tool(
            "create_process",
            {
                "product_system_id": spaced_bottle,
                "code": "bottle",
                "name": "bottle",
                "unit": "unit",
                "reference_product": "bottle",
            },
        )
        await client.call_tool(
            "update_product_system",
            {"product_system_id": spaced_bottle, "reference_process": "bottle"},
        )
        made = await client.call_tool(
            "create_product_system", {"name": "crate", "database": FIXTURE_DB}
        )
        crate = made.structured_content["value"]["id"]
        await client.call_tool(
            "create_process",
            {
                "product_system_id": crate,
                "code": "crate",
                "name": "crate",
                "unit": "unit",
                "reference_product": "crate",
            },
        )
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": crate,
                "code": "crate",
                "type": "product",
                "amount": 1.0,
                "input": {"kind": "system", "product_system_id": spaced_bottle, "case": "lean"},
            },
        )
        out = await client.call_tool(
            "export_tables", {"product_system_id": spaced_bottle, "path": str(tmp_path)}
        )
        folder = Path(out.structured_content["value"]["path"])
        (folder / "inputs" / "cases.csv").write_text("parameter\n", encoding="utf-8")
        with pytest.raises(ToolError, match="crate"):
            await client.call_tool("import_tables", {"path": str(folder)})


def test_a_result_key_records_the_state_read_and_the_demand_resolved(
    fixture_system_stored: ProductSystem,
) -> None:
    unread = fixture_system_stored.model_copy(update={"hash": None})
    assert result_key(unread, "m", None, None, []).hash == content_hash(unread)
    read = materialize(fixture_system_stored.model_copy(update={"hash": "a" * 64}))
    key = result_key(read, None, "IPCC", None, ["lean"])
    assert (key.hash, key.method, key.variants) == ("a" * 64, "IPCC", ["lean"])
    assert [(item.ref.code, item.amount) for item in key.demand] == [("widget", 1.0)]
