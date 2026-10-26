from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest
from fastmcp import Client

from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.mcp.context import AGENT, ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.ports.types import DatabaseSource
from tests.fixture_data import CODES, FIXTURE_DB
from tests.memory_activity import MemoryActivity
from tests.memory_background import MemoryInventory, MemorySearch
from tests.memory_installs import MemoryInstaller, MemoryInstalls
from tests.memory_runs import MemoryLauncher, MemoryRuns
from tests.memory_storage import MemoryStorage


@pytest.fixture
def ports_only(native_store: NativeStore, tmp_path: Path) -> ServerContext:
    """Four ports in memory and the calculation backend, so a tool needing more fails here."""
    inventory = MemoryInventory()
    return ServerContext(
        inventory=inventory,
        search=MemorySearch(),
        calculation=NativeCalculation(native_store),
        storage=MemoryStorage(),
        resolver=InventoryResolver(inventory),
        actor=AGENT,
        runs=MemoryRuns(),
        activity=MemoryActivity(),
        launcher=MemoryLauncher(),
        installs=MemoryInstalls(),
        installer=MemoryInstaller(
            [
                DatabaseSource(
                    name="uslci",
                    versions=["2024"],
                    system_models=[],
                    credential=None,
                    terms=False,
                )
            ]
        ),
        systems_dir=tmp_path,
        data_dir=native_store.directory,
        uploads_dir=tmp_path / "uploads",
    )


async def test_a_positive_input_to_a_treatment_is_named_by_the_write_and_every_calculation(
    ports_only: ServerContext,
) -> None:
    treating = dataclasses.replace(ports_only, inventory=MemoryInventory({CODES["steel"]}))
    steel = {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]}
    async with Client(build_server(treating)) as client:
        created = await client.call_tool(
            "create_product_system", {"name": "cup", "database": FIXTURE_DB}
        )
        system_id = created.structured_content["value"]["id"]
        cup = {"code": "cup", "name": "cup", "unit": "kilogram", "reference_product": "cup"}
        await client.call_tool("create_process", {"product_system_id": system_id, **cup})
        await client.call_tool(
            "update_product_system", {"product_system_id": system_id, "reference_process": "cup"}
        )
        sent = await client.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": "cup",
                "type": "product",
                "amount": 0.5,
                "input": steel,
            },
        )
        issues = sent.structured_content["consequences"]["issues"]
        [issue] = [i for i in issues if i["case"] == "treatments_take_waste"]
        assert issue["code"] == "treatment_runs_backwards" and issue["process_codes"] == ["cup"]
        methods = await client.call_tool(
            "search_methods", {"database": FIXTURE_DB, "query": "climate"}
        )
        method_id = methods.structured_content["items"][0]["id"]
        scored = await client.call_tool(
            "calculate_impact", {"product_system_id": system_id, "method_id": method_id}
        )
        [named] = scored.structured_content["value"]["treatments_run_backwards"]
        assert named.startswith("cup · ") and named.endswith(" at 0.5")
        for by in ("process", "path", "flow"):
            decomposed = await client.call_tool(
                "contribution_analysis",
                {"product_system_id": system_id, "by": by, "method_id": method_id},
            )
            assert decomposed.structured_content["value"]["treatments_run_backwards"] == [named]
        listed = await client.call_tool("calculate_inventory", {"product_system_id": system_id})
        assert listed.structured_content["treatments_run_backwards"] == [named]
        exchange_id = sent.structured_content["value"]["id"]
        negated = await client.call_tool(
            "update_exchange",
            {"product_system_id": system_id, "exchange_id": exchange_id, "amount": -0.5},
        )
        cases = {i["case"] for i in negated.structured_content["consequences"]["issues"]}
        assert "treatments_take_waste" not in cases


async def test_every_tool_composes_over_the_ports_alone(
    ports_only: ServerContext, tmp_path: Path
) -> None:
    async with Client(build_server(ports_only)) as client:
        created = await client.call_tool(
            "create_product_system", {"name": "cup", "database": FIXTURE_DB}
        )
        system_id = created.structured_content["value"]["id"]
        await client.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": "cup",
                "name": "cup",
                "unit": "kilogram",
                "reference_product": "cup",
            },
        )
        await client.call_tool(
            "update_product_system", {"product_system_id": system_id, "reference_process": "cup"}
        )
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": "cup",
                "type": "product",
                "amount": 0.5,
                "input": {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]},
            },
        )
        methods = await client.call_tool(
            "search_methods", {"database": FIXTURE_DB, "query": "climate"}
        )
        method_id = methods.structured_content["items"][0]["id"]
        scored = await client.call_tool(
            "calculate_impact", {"product_system_id": system_id, "method_id": method_id}
        )
        assert scored.structured_content["value"]["scores"][0]["value"] == pytest.approx(1.39)
        bundle = tmp_path / "cup.zip"
        await client.call_tool(
            "export_product_system", {"product_system_id": system_id, "path": str(bundle)}
        )
        await client.call_tool("delete_product_system", {"product_system_id": system_id})
        back = await client.call_tool("import_product_system", {"path": str(bundle)})
        assert back.structured_content["value"]["id"] == system_id
        log = await client.call_tool("get_product_system_log", {"product_system_id": system_id})
        assert [e["source"] for e in log.structured_content["items"]] == ["import"]
        runs = await client.call_tool("list_runs", {"product_system_id": system_id})
        assert runs.structured_content["value"] == []


async def test_the_install_tools_run_on_the_doubles(ports_only: ServerContext) -> None:
    async with Client(build_server(ports_only)) as client:
        sources = await client.call_tool("list_sources", {})
        assert [source["name"] for source in sources.structured_content["value"]] == ["uslci"]
        posted = await client.call_tool("install_database", {"source": "uslci"})
        install_id = posted.structured_content["value"]["id"]
        one = await client.call_tool("get_install", {"install_id": install_id})
        assert one.structured_content["value"]["pid"] == 4242
        every = await client.call_tool("list_installs", {})
        assert [i["id"] for i in every.structured_content["value"]] == [install_id]
        stopped = await client.call_tool("cancel_install", {"install_id": install_id})
        assert stopped.structured_content["value"]["cancel_requested"] is True
    for task in ports_only.watchers:
        task.cancel()
    await asyncio.gather(*ports_only.watchers, return_exceptions=True)
