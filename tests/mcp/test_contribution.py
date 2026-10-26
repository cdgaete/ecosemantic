from __future__ import annotations

import dataclasses
import inspect
import json
import uuid

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.mcp import calculation
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Exchange, Method, Process, ProductSystem, method_id
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.ports.inventory import InventoryPort
from tests.conftest import NS, fixture_system
from tests.fixture_data import CODES as FIXTURE_CODES
from tests.fixture_data import FIXTURE_DB, FIXTURE_FINGERPRINT, GWP

GWP_ID = method_id(" > ".join(GWP))


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    built = build_server()
    calculation.register(built, context)
    return built


@pytest.fixture(scope="module")
async def widget(fixture_system_stored: ProductSystem) -> uuid.UUID:
    return fixture_system_stored.id


def _sums_to_parent(node: dict[str, object]) -> None:
    children = node["children"]
    if children:
        assert sum(c["score"] for c in children) == pytest.approx(node["score"])
        for child in children:
            _sums_to_parent(child)


async def test_by_process_is_an_exact_partition(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "method_id": GWP_ID, "by": "process"},
            )
        ).structured_content["value"]
    assert out["by"] == "process" and out["root"] is None
    assert out["total"]["value"] == pytest.approx(4.158)
    assert out["database"]["fingerprint"] == FIXTURE_FINGERPRINT
    assert sum(p["score"] for p in out["processes"]) == pytest.approx(4.158)
    names = {p["name"]: p["score"] for p in out["processes"]}
    assert names["electricity production"] == pytest.approx(3.2)


async def test_by_path_nests_and_sums_to_each_parent(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "contribution_analysis",
                {
                    "product_system_id": str(widget),
                    "method_id": GWP_ID,
                    "by": "path",
                    "max_level": 4,
                    "max_nodes": 200,
                    "cutoff": 0.0,
                },
            )
        ).structured_content["value"]
    assert out["by"] == "path" and out["processes"] is None
    assert out["root"]["score"] == pytest.approx(4.158)
    assert out["truncated"] is False
    _sums_to_parent(out["root"])
    kinds = {c["kind"] for c in out["root"]["children"]}
    assert kinds == {"process", "elementary_flow"}


async def test_both_axes_agree_on_the_total(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        args = {"product_system_id": str(widget), "method_id": GWP_ID}
        flat = (
            await client.call_tool("contribution_analysis", {**args, "by": "process"})
        ).structured_content["value"]
        nested = (
            await client.call_tool("contribution_analysis", {**args, "by": "path"})
        ).structured_content["value"]
    assert flat["total"]["value"] == pytest.approx(nested["total"]["value"])


async def test_an_unknown_impact_method_is_not_found(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "impact_method": "nothing", "by": "process"},
            )
        assert json.loads(str(caught.value))["error"] == "not_found"


class _EveryCategory:
    """An inventory that answers every method for any impact method name."""

    def __init__(self, inventory: InventoryPort) -> None:
        self._inventory = inventory

    async def list_methods(self, database: str, impact_method: str | None = None) -> list[Method]:
        return await self._inventory.list_methods(database)


async def test_an_impact_method_with_many_categories_is_invalid(
    context: ServerContext, widget: uuid.UUID
) -> None:
    # the fixture's methods are gwp and water: two categories under one name
    many = build_server()
    calculation.register(
        many, dataclasses.replace(context, inventory=_EveryCategory(context.inventory))
    )
    async with Client(many) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "impact_method": "gwp", "by": "process"},
            )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid" and "2" in payload["message"]


async def test_by_flow_partitions_the_total_over_substances(
    server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "method_id": GWP_ID, "by": "flow"},
            )
        ).structured_content["value"]
    assert out["by"] == "flow" and out["processes"] is None and out["root"] is None
    assert sum(f["score"] for f in out["flows"]) == pytest.approx(out["total"]["value"])
    assert out["flows"][0]["name"] == "Carbon dioxide, fossil"
    assert out["flows"][0]["fraction"] == pytest.approx(3.85 / 4.158)


async def test_inventory_rows_name_their_source(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        listing = (
            await client.call_tool("calculate_inventory", {"product_system_id": str(widget)})
        ).structured_content
    assert listing["has_more"] is False and listing["hint"] is None
    assert listing["dropped"] == 0 and listing["floor"] == pytest.approx(1e-34 * 3.85)
    assert listing["database"]["fingerprint"] == FIXTURE_FINGERPRINT
    rows = listing["items"]
    assert [r["name"] for r in rows] == ["Carbon dioxide, fossil", "Methane, fossil"]
    by_name = {r["name"]: r for r in rows}
    assert by_name["Carbon dioxide, fossil"]["amount"] == pytest.approx(3.85)
    assert by_name["Carbon dioxide, fossil"]["source"]["code"] == "widget"
    assert by_name["Methane, fossil"]["amount"] == pytest.approx(0.011)
    assert {r["side"] for r in rows} == {"output"}
    assert by_name["Carbon dioxide, fossil"]["flow_type"] == "emission"
    assert by_name["Carbon dioxide, fossil"]["sub_compartment"] is None


async def test_inventory_pages_and_filters(server: FastMCP, widget: uuid.UUID) -> None:
    args = {"product_system_id": str(widget)}
    async with Client(server) as client:

        async def rows(**extra: object) -> dict[str, object]:
            return (
                await client.call_tool("calculate_inventory", {**args, **extra})
            ).structured_content

        first = await rows(limit=1)
        assert [r["name"] for r in first["items"]] == ["Carbon dioxide, fossil"]
        assert first["has_more"] is True and first["next_cursor"] in first["hint"]
        second = await rows(limit=1, cursor=first["next_cursor"])
        assert [r["name"] for r in second["items"]] == ["Methane, fossil"]
        assert second["has_more"] is False
        assert len((await rows(compartment="air"))["items"]) == 2
        none = await rows(compartment="water")
        assert none["items"] == [] and "compartment" in none["hint"]
        assert [r["name"] for r in (await rows(query="methane"))["items"]] == ["Methane, fossil"]


async def test_inventory_rows_of_a_water_user_split_by_side(
    server: FastMCP, context: ServerContext
) -> None:
    washer = Process(
        id=uuid.uuid5(NS, "process:washer"),
        code="washer",
        name="washing",
        unit="unit",
        location="CH",
        reference_product="washed item",
        exchanges=[
            Exchange(
                id=uuid.uuid5(NS, "exchange:washer:0"),
                type="production",
                name="washed item",
                amount=1.0,
                unit="unit",
            ),
            Exchange(
                id=uuid.uuid5(NS, "exchange:washer:1"),
                type="product",
                name="tap water",
                amount=5.0,
                unit="kilogram",
                input=BackgroundRef(database=FIXTURE_DB, id=FIXTURE_CODES["water"]),
            ),
        ],
    )
    base = fixture_system().product_system
    assert base is not None
    system = ProductSystem(
        id=uuid.uuid5(NS, "system:washer"),
        name="washer_system",
        database=base.database,
        processes=[washer],
        reference_process="washer",
    )
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(server) as client:
        listing = (
            await client.call_tool("calculate_inventory", {"product_system_id": str(system.id)})
        ).structured_content
    sides = {r["name"]: r["side"] for r in listing["items"]}
    assert sides["Water, river"] == "input"
    assert sides["Carbon dioxide, fossil"] == "output"


async def test_the_tool_the_port_and_the_backend_bound_a_decomposition_alike(
    server: FastMCP,
) -> None:
    from ecosemantic.backends.native.calculation import NativeCalculation
    from ecosemantic.ports.calculation import CalculationPort

    bounds = ("top_n", "max_level", "max_nodes", "cutoff")
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    properties = tools["contribution_analysis"].input_schema["properties"]
    asked = {name: properties[name]["default"] for name in bounds}
    for owner in (CalculationPort, NativeCalculation):
        declared = {
            **inspect.signature(owner.hotspots).parameters,
            **inspect.signature(owner.flow_hotspots).parameters,
            **inspect.signature(owner.contribution_tree).parameters,
        }
        assert {name: declared[name].default for name in bounds} == asked, owner


async def test_a_loop_holding_a_credit_is_named_beside_each_decomposition_and_the_inventory(
    server: FastMCP, widget: uuid.UUID, credited_stored: ProductSystem
) -> None:
    # a loop holding a credit leaves no root, so the demand names the widget
    gwp = method_id(" > ".join(GWP))
    demand = [{"ref": {"kind": "foreground", "code": "widget"}, "amount": 1.0}]
    async with Client(server) as client:
        for system, named in ((widget, []), (credited_stored.id, [["frame", "widget"]])):
            for by in ("process", "path", "flow"):
                out = await client.call_tool(
                    "contribution_analysis",
                    {
                        "product_system_id": str(system),
                        "by": by,
                        "method_id": gwp,
                        "demand": demand,
                    },
                )
                assert out.structured_content["value"]["credit_loops"] == named
            rows = await client.call_tool(
                "calculate_inventory", {"product_system_id": str(system), "demand": demand}
            )
            assert rows.structured_content["credit_loops"] == named
