from __future__ import annotations

import dataclasses
import inspect
import json
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.compute.results import InventoryResult
from ecosemantic.mcp import calculation
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import (
    Exchange,
    ExchangeOverride,
    Method,
    Process,
    ProductSystem,
    Scenario,
    method_id,
)
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.types import InventoryOrder, Side
from tests.conftest import NS, fixture_system
from tests.fixture_data import CODES as FIXTURE_CODES
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DB, FIXTURE_FINGERPRINT, GWP
from tests.fixture_data import FLOW_IDS as FIXTURE_FLOW_IDS
from tests.fixture_data import FLOWS as FIXTURE_FLOWS
from tests.registered import registered

GWP_ID = method_id(" > ".join(GWP))


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    return registered(context, calculation)


@pytest.fixture(scope="module")
async def widget(fixture_system_stored: ProductSystem) -> uuid.UUID:
    return fixture_system_stored.id


@pytest.fixture(scope="module")
def page_server(context: ServerContext) -> FastMCP:
    """The calculation tools over a context that serves the page, so each answer links to it."""
    served = dataclasses.replace(context, view_url="http://127.0.0.1:1?token=abc")
    return registered(served, calculation)


def _staged(system: ProductSystem, name: str) -> ProductSystem:
    """A copy of the system whose widget is `assembly` and whose frame is `materials`."""
    staged = system.model_copy(deep=True, update={"hash": None})
    staged.id = uuid.uuid5(system.id, name)
    staged.name = name
    staged.process("widget").metadata["life_cycle_stage"] = "assembly"
    staged.process("frame").metadata["life_cycle_stage"] = "materials"
    return staged


@pytest.fixture(scope="module")
async def staged(context: ServerContext, fixture_system_stored: ProductSystem) -> uuid.UUID:
    system = _staged(fixture_system_stored, "widget_staged")
    await context.storage.put_product_system(system, context.actor, "created")
    return system.id


@pytest.fixture(scope="module")
async def staged_varied(context: ServerContext, varied: uuid.UUID) -> uuid.UUID:
    system = _staged(await context.storage.get_product_system(varied), "widget_varied_staged")
    await context.storage.put_product_system(system, context.actor, "created")
    return system.id


@pytest.fixture(scope="module")
async def split_system(context: ServerContext) -> ProductSystem:
    """A process drawing 0.4 m3 of river water and emitting three flows, whose names and amounts
    order differently: by name carbon dioxide, methane, particulate matter; by amount methane,
    carbon dioxide, particulate matter."""
    base = fixture_system().product_system
    assert base is not None

    def elementary(n: int, key: str, amount: float) -> Exchange:
        return Exchange(
            id=uuid.uuid5(NS, f"exchange:split:{n}"),
            type="elementary",
            name=FIXTURE_FLOWS[key][0],
            amount=amount,
            unit=FIXTURE_FLOWS[key][2],
            input=ElementaryFlowRef(database=FIXTURE_BIO, id=FIXTURE_FLOW_IDS[key]),
        )

    splitter = Process(
        id=uuid.uuid5(NS, "process:split"),
        code="split",
        name="splitting",
        unit="unit",
        location="CH",
        reference_product="split item",
        exchanges=[
            Exchange(
                id=uuid.uuid5(NS, "exchange:split:production"),
                type="production",
                name="split item",
                amount=1.0,
                unit="unit",
            ),
            elementary(1, "water_in", 0.4),
            elementary(2, "ch4", 0.5),
            elementary(3, "co2", 0.2),
            elementary(4, "pm", 0.01),
        ],
    )
    system = ProductSystem(
        id=uuid.uuid5(NS, "system:split"),
        name="split_system",
        database=base.database,
        processes=[splitter],
        reference_process="split",
    )
    await context.storage.put_product_system(system, context.actor, "created")
    return system


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
    assert out["method"]["id"] == out["total"]["method_id"] == GWP_ID
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
    many = registered(
        dataclasses.replace(context, inventory=_EveryCategory(context.inventory)), calculation
    )
    async with Client(many) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "impact_method": "gwp", "by": "process"},
            )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid"
        assert payload["message"] == "a decomposition takes one method; 'gwp' names 2"


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


async def test_a_list_by_process_or_by_flow_drops_what_is_under_the_cutoff_and_says_what_it_cut(
    server: FastMCP, widget: uuid.UUID
) -> None:
    args = {"product_system_id": str(widget), "method_id": GWP_ID, "cutoff": 0.1}
    async with Client(server) as client:
        processes = (
            await client.call_tool("contribution_analysis", {**args, "by": "process"})
        ).structured_content["value"]
        flows = (
            await client.call_tool("contribution_analysis", {**args, "by": "flow"})
        ).structured_content["value"]
        path = (
            await client.call_tool("contribution_analysis", {**args, "by": "path"})
        ).structured_content["value"]
    assert [p["name"] for p in processes["processes"]] == [
        "electricity production",
        "steel production",
    ]
    assert processes["cut"]["cutoff"] == 0.1
    assert processes["cut"]["below"] == 1
    assert processes["cut"]["share"] == pytest.approx(0.1 / 4.158)
    assert [f["name"] for f in flows["flows"]] == ["Carbon dioxide, fossil"]
    assert flows["cut"]["below"] == 1
    assert flows["cut"]["share"] == pytest.approx(0.308 / 4.158)
    assert path["cut"] is None


async def test_a_list_top_n_cuts_short_says_what_it_leaves_unlisted(
    server: FastMCP, widget: uuid.UUID
) -> None:
    args = {
        "product_system_id": str(widget),
        "method_id": GWP_ID,
        "by": "process",
        "top_n": 1,
        "cutoff": 0.0,
    }
    async with Client(server) as client:
        out = (await client.call_tool("contribution_analysis", args)).structured_content["value"]
    assert [p["name"] for p in out["processes"]] == ["electricity production"]
    assert (out["cut"]["below"], out["cut"]["unlisted"]) == (0, 2)
    assert out["cut"]["unlisted_share"] == pytest.approx(1 - out["processes"][0]["fraction"])


async def test_the_rows_a_list_shows_and_the_two_scores_it_leaves_out_make_the_total(
    server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(server) as client:
        for by in ("process", "flow"):
            for asked in ({"cutoff": 0.1}, {"top_n": 1, "cutoff": 0.0}):
                args = {"product_system_id": str(widget), "method_id": GWP_ID, "by": by, **asked}
                out = (await client.call_tool("contribution_analysis", args)).structured_content[
                    "value"
                ]
                rows = out["processes"] if by == "process" else out["flows"]
                cut = out["cut"]
                assert cut["below"] > 0 or cut["unlisted"] > 0, (by, asked)
                shown = sum(row["score"] for row in rows)
                assert shown + cut["below_score"] + cut["unlisted_score"] == pytest.approx(
                    out["total"]["value"]
                ), (by, asked)


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


async def test_the_inventory_pages_each_side_on_its_own(
    server: FastMCP, split_system: ProductSystem
) -> None:
    async def walked(side: Side) -> list[dict[str, object]]:
        walked_rows: list[dict[str, object]] = []
        cursor = None
        async with Client(server) as client:
            while True:
                args: dict[str, object] = {
                    "product_system_id": str(split_system.id),
                    "side": side,
                    "limit": 1,
                }
                if cursor is not None:
                    args["cursor"] = cursor
                page = (await client.call_tool("calculate_inventory", args)).structured_content
                walked_rows.extend(page["items"])
                if not page["has_more"]:
                    return walked_rows
                cursor = page["next_cursor"]

    assert [r["name"] for r in await walked("input")] == ["Water, river"]
    outputs = await walked("output")
    assert [r["side"] for r in outputs] == ["output", "output", "output"]
    assert [r["name"] for r in outputs] == [
        "Carbon dioxide, fossil",
        "Methane, fossil",
        "Particulate matter",
    ]


async def test_the_inventory_orders_by_falling_amount(
    server: FastMCP, split_system: ProductSystem
) -> None:
    async def ordered(order: InventoryOrder) -> list[str]:
        async with Client(server) as client:
            listing = (
                await client.call_tool(
                    "calculate_inventory",
                    {"product_system_id": str(split_system.id), "order": order},
                )
            ).structured_content
        return [r["name"] for r in listing["items"]]

    assert await ordered("amount") == [
        "Water, river",
        "Methane, fossil",
        "Carbon dioxide, fossil",
        "Particulate matter",
    ]
    assert await ordered("compartment") == [
        "Water, river",
        "Carbon dioxide, fossil",
        "Methane, fossil",
        "Particulate matter",
    ]


async def test_without_a_side_inputs_come_first(
    server: FastMCP, split_system: ProductSystem
) -> None:
    async def sides(order: InventoryOrder) -> list[str]:
        async with Client(server) as client:
            listing = (
                await client.call_tool(
                    "calculate_inventory",
                    {"product_system_id": str(split_system.id), "order": order},
                )
            ).structured_content
        return [r["side"] for r in listing["items"]]

    for order in ("compartment", "amount"):
        assert await sides(order) == ["input", "output", "output", "output"]


def test_the_inventory_listing_holds_every_field_of_the_inventory_result_alike() -> None:
    listing = calculation.InventoryListing.model_fields
    for name, field in InventoryResult.model_fields.items():
        assert name in listing, name
        held = listing[name]
        assert (held.annotation, held.default, held.default_factory) == (
            field.annotation,
            field.default,
            field.default_factory,
        ), name


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


async def test_a_case_is_decomposed_in_place_of_the_base(
    server: FastMCP, varied: uuid.UUID
) -> None:
    args = {"product_system_id": str(varied), "method_id": GWP_ID, "by": "process"}
    async with Client(server) as client:

        async def decomposed(**extra: object) -> dict[str, object]:
            out = await client.call_tool("contribution_analysis", {**args, **extra})
            return out.structured_content["value"]

        base = await decomposed()
        case = await decomposed(variant="half")
        scenario = await decomposed(variant="double_steel")
    assert base["variant"] is None and base["total"]["value"] == pytest.approx(4.158)
    assert case["variant"] == "half" and case["total"]["value"] == pytest.approx(3.658)
    assert scenario["variant"] == "double_steel"
    assert scenario["total"]["value"] == pytest.approx(5.548)


async def test_a_decomposition_links_to_its_page(page_server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(page_server) as client:
        for by, page in (("stage", "stages"), ("process", "processes"), ("path", "tree")):
            out = await client.call_tool(
                "contribution_analysis",
                {"product_system_id": str(widget), "method_id": GWP_ID, "by": by},
            )
            link = out.structured_content["view_url"]
            assert urlsplit(link).path.endswith(f"/results/{page}"), by


async def test_the_split_by_stage_through_the_tool_sums_to_calculate_impact(
    page_server: FastMCP, staged: uuid.UUID
) -> None:
    args = {"product_system_id": str(staged), "method_id": GWP_ID}
    async with Client(page_server) as client:
        split = (
            await client.call_tool("contribution_analysis", {**args, "by": "stage"})
        ).structured_content
        scored = (await client.call_tool("calculate_impact", args)).structured_content["value"]
    out = split["value"]
    assert out["by"] == "stage" and out["variant"] is None
    assert [s["stage"] for s in out["stages"]] == ["assembly", "materials"]
    assert [s["score"] for s in out["stages"]] == pytest.approx([2.49, 1.668])
    assert [s["fraction"] for s in out["stages"]] == pytest.approx([2.49 / 4.158, 1.668 / 4.158])
    assert out["total"]["value"] == pytest.approx(4.158)
    assert out["total"]["value"] == pytest.approx(scored["scores"][0]["value"])
    assert "variant" not in parse_qs(urlsplit(split["view_url"]).query)


async def test_a_case_split_by_stage(page_server: FastMCP, staged_varied: uuid.UUID) -> None:
    args = {
        "product_system_id": str(staged_varied),
        "method_id": GWP_ID,
        "by": "stage",
        "variant": "half",
    }
    async with Client(page_server) as client:
        split = (await client.call_tool("contribution_analysis", args)).structured_content
    out = split["value"]
    assert out["variant"] == "half"
    assert [s["stage"] for s in out["stages"]] == ["assembly", "materials"]
    assert [s["score"] for s in out["stages"]] == pytest.approx([1.99, 1.668])
    assert out["total"]["value"] == pytest.approx(3.658)
    assert parse_qs(urlsplit(split["view_url"]).query)["variant"] == ["half"]


async def test_a_case_s_inventory_is_listed_in_place_of_the_base(
    server: FastMCP, varied: uuid.UUID
) -> None:
    args = {"product_system_id": str(varied)}
    async with Client(server) as client:

        async def listed(**extra: object) -> dict[str, object]:
            out = await client.call_tool("calculate_inventory", {**args, **extra})
            return out.structured_content

        base = await listed()
        case = await listed(variant="half")
    assert base["variant"] is None and case["variant"] == "half"
    amounts = {r["name"]: r["amount"] for r in base["items"]}
    varied_amounts = {r["name"]: r["amount"] for r in case["items"]}
    # the case halves the widget's kilowatt hour, which emits one kilogram of carbon dioxide
    assert varied_amounts["Carbon dioxide, fossil"] == pytest.approx(
        amounts["Carbon dioxide, fossil"] - 0.5
    )


async def test_a_stale_scenario_is_refused_by_the_contributions(
    context: ServerContext, server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "unpinned_contributions")
    system.name = "widget_unpinned_contributions"
    steel = system.process("widget").exchanges[1]
    system.scenarios = [
        Scenario(name="more", overrides=[ExchangeOverride(exchange_id=steel.id, multiplier=2.0)])
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "contribution_analysis",
                {
                    "product_system_id": str(system.id),
                    "method_id": GWP_ID,
                    "by": "process",
                    "variant": "more",
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid" and "rebase_scenario" in payload["message"]
