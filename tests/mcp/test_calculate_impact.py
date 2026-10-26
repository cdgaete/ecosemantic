from __future__ import annotations

import json
import statistics
import uuid

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.compute.parameters import materialize
from ecosemantic.mcp import calculation
from ecosemantic.mcp.calculation import impact_of
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import (
    Case,
    DemandItem,
    Exchange,
    ExchangeOverride,
    Parameter,
    Process,
    ProductSystem,
    Scenario,
    method_id,
)
from ecosemantic.model.refs import BackgroundRef, ForegroundRef
from ecosemantic.ports.types import System
from tests.fixture_data import CODES, FIXTURE_DB, FIXTURE_FINGERPRINT, GWP

GWP_ID = method_id(" > ".join(GWP))
WIDGET_DEMAND = [{"ref": {"kind": "foreground", "code": "widget"}, "amount": 1.0}]


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    built = build_server()
    calculation.register(built, context)
    return built


@pytest.fixture(scope="module")
async def widget(fixture_system_stored: ProductSystem) -> uuid.UUID:
    return fixture_system_stored.id


@pytest.fixture(scope="module")
async def varied(context: ServerContext, fixture_system_stored: ProductSystem) -> uuid.UUID:
    """The widget with electricity on a parameter, a case halving it, a scenario doubling steel."""
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "varied")
    system.name = "widget_varied"
    assembly = system.process("widget")
    steel, electricity = assembly.exchanges[1], assembly.exchanges[2]
    electricity.formula = "elec_kwh"
    system.parameters = [Parameter(name="elec_kwh", value=1.0)]
    system.cases = [Case(name="half", values={"elec_kwh": 0.5})]
    system.scenarios = [
        Scenario(
            name="double_steel",
            overrides=[ExchangeOverride(exchange_id=steel.id, multiplier=2.0)],
        )
    ]
    system.scenarios[0].base_hash = base_pin(system)
    await context.storage.put_product_system(system, context.actor, "created")
    return system.id


async def test_score_of_the_stored_system(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(widget), "method_id": GWP_ID},
            )
        ).structured_content["value"]
        assert out["scores"][0]["value"] == pytest.approx(4.158)
        assert out["scores"][0]["unit"] == "kg CO2-Eq"
        assert out["database"]["fingerprint"] == FIXTURE_FINGERPRINT


async def test_a_specification_resolves_and_hints_the_id(
    server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(widget), "method_id": " > ".join(GWP)},
            )
        ).structured_content
        assert out["value"]["scores"][0]["value"] == pytest.approx(4.158)
        assert GWP_ID in out["hint"]


async def test_a_wrong_specification_returns_suggestions(
    server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(widget),
                    "method_id": "fixture > gwp > Climate Change > GWP 100",
                },
            )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "method_not_found"
        assert GWP_ID in [s["id"] for s in payload["details"]["suggestions"]]


async def test_an_impact_method_scores_every_category(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(widget), "impact_method": "gwp"},
            )
        ).structured_content["value"]
        assert [s["method"]["impact_method"] for s in out["scores"]] == ["gwp"]


async def test_naming_neither_method_is_invalid(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("calculate_impact", {"product_system_id": str(widget)})
        assert json.loads(str(caught.value))["error"] == "invalid"


async def test_monte_carlo_is_reproducible(server: FastMCP, widget: uuid.UUID) -> None:
    args = {
        "product_system_id": str(widget),
        "method_id": GWP_ID,
        "monte_carlo": {"n": 5, "seed": 3},
    }
    async with Client(server) as client:
        first = (await client.call_tool("calculate_impact", args)).structured_content["value"]
        second = (await client.call_tool("calculate_impact", args)).structured_content["value"]
    a = first["uncertainty"]["categories"][0]["samples"]
    assert a == second["uncertainty"]["categories"][0]["samples"] and len(a) == 5
    assert first["uncertainty"]["database"]["fingerprint"] == FIXTURE_FINGERPRINT


async def test_a_count_above_the_ceiling_is_refused_at_the_arguments(
    full_server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(full_server) as client:
        for above in ({"n": 300}, {"n_max": 300}):
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "calculate_impact",
                    {
                        "product_system_id": str(widget),
                        "method_id": GWP_ID,
                        "monte_carlo": above,
                    },
                )
            assert json.loads(str(caught.value))["error"] == "invalid"


async def test_calculate_impact_s_schema_states_its_ceiling(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    def bounded(name: str, ceiling: int) -> None:
        block = tools[name].input_schema["properties"]["monte_carlo"]["anyOf"][0]
        for field in ("n", "n_min", "n_max"):
            stated = block["properties"][field]
            assert stated["description"]
            limit = stated if "maximum" in stated else stated["anyOf"][0]
            assert limit["maximum"] == ceiling

    bounded("calculate_impact", 200)
    bounded("start_monte_carlo", 1000)


async def test_variants_are_scored_against_the_base(server: FastMCP, varied: uuid.UUID) -> None:
    # electricity 1 kWh at 1.0 kg CO2-Eq; steel 0.5 kg at 2.78 kg CO2-Eq per kg
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(varied),
                    "method_id": GWP_ID,
                    "variants": ["half", "double_steel"],
                },
            )
        ).structured_content["value"]
    assert out["scores"][0]["value"] == pytest.approx(4.158)
    by_name = {v["name"]: v for v in out["variants"]}
    assert by_name["half"]["scores"][0]["value"] == pytest.approx(3.658)
    assert by_name["half"]["deltas"] == [pytest.approx(-0.5)]
    assert by_name["double_steel"]["scores"][0]["value"] == pytest.approx(5.548)
    assert by_name["double_steel"]["deltas"] == [pytest.approx(1.39)]


async def test_under_monte_carlo_each_variant_carries_its_samples_and_its_paired_delta(
    server: FastMCP, varied: uuid.UUID
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(varied),
                    "method_id": GWP_ID,
                    "variants": ["half", "double_steel"],
                    "monte_carlo": {"n": 8, "seed": 3},
                },
            )
        ).structured_content["value"]
    base = out["uncertainty"]["categories"][0]["samples"]
    for variant in out["variants"]:
        [category] = variant["uncertainty"]["categories"]
        assert len(category["samples"]) == 8
        assert category["summary"]["median"] == pytest.approx(
            statistics.median(category["samples"])
        )
        differences = [v - b for b, v in zip(base, category["samples"], strict=True)]
        [paired] = variant["paired_deltas"]
        assert paired["delta_abs"] == pytest.approx(statistics.median(differences))
        assert variant["deltas"] == [
            pytest.approx(score["value"] - point["value"])
            for score, point in zip(variant["scores"], out["scores"], strict=True)
        ]
        # eight pairs give an interval, which needs six
        low, high = paired["delta_ci95"]
        assert low <= paired["delta_abs"] <= high
        assert paired["delta_pct"] == pytest.approx(
            paired["delta_abs"] / statistics.median(base) * 100.0
        )


async def test_under_monte_carlo_a_variant_s_deltas_are_its_scores_less_the_base_s(
    server: FastMCP, varied: uuid.UUID
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(varied),
                    "method_id": GWP_ID,
                    "variants": ["half", "double_steel"],
                    "monte_carlo": {"n": 8, "seed": 3},
                },
            )
        ).structured_content["value"]
    for variant in out["variants"]:
        assert variant["deltas"] == [
            pytest.approx(score["value"] - base["value"])
            for score, base in zip(variant["scores"], out["scores"], strict=True)
        ]
        assert variant["paired_deltas"] is not None


async def test_a_scenario_swapping_an_input_to_an_ordinary_foreground_process_calculates(
    context: ServerContext, server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "light")
    system.name = "widget_light"
    frame = system.process("frame")
    light = frame.model_copy(deep=True, update={"id": uuid.uuid5(system.id, "frame_light")})
    light.code = "frame_light"
    for n, exchange in enumerate(light.exchanges):
        exchange.id = uuid.uuid5(system.id, f"frame_light_{n}")
    light.exchanges[1].amount = 1.2
    system.processes.append(light)
    assembly = system.process("widget")
    assembly.exchanges.append(
        Exchange(
            id=uuid.uuid5(system.id, "light_use"),
            type="product",
            name="frame",
            amount=0.0,
            unit="kilogram",
            input=ForegroundRef(code="frame_light"),
        )
    )
    system.scenarios = [
        Scenario(
            name="light",
            overrides=[
                ExchangeOverride(
                    exchange_id=assembly.exchanges[3].id, input=ForegroundRef(code="frame_light")
                )
            ],
        )
    ]
    system.scenarios[0].base_hash = base_pin(system)
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(system.id), "method_id": GWP_ID, "variants": ["light"]},
            )
        ).structured_content["value"]
    # the frame's 0.25 kg at 6.672 gives way to the light frame's 0.25 kg at 3.336
    assert out["scores"][0]["value"] == pytest.approx(4.158)
    assert out["variants"][0]["scores"][0]["value"] == pytest.approx(3.324)


async def test_an_unknown_variant_is_not_found(server: FastMCP, varied: uuid.UUID) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(varied), "method_id": GWP_ID, "variants": ["big"]},
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "not_found" and "half" in payload["message"]


async def test_an_unpinned_scenario_is_stale(
    context: ServerContext, server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "unpinned")
    system.name = "widget_unpinned"
    steel = system.process("widget").exchanges[1]
    system.scenarios = [
        Scenario(name="more", overrides=[ExchangeOverride(exchange_id=steel.id, multiplier=2.0)])
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": str(system.id), "method_id": GWP_ID, "variants": ["more"]},
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid" and "rebase_scenario" in payload["message"]


async def test_without_a_demand_the_system_needs_a_reference_process(
    server: FastMCP, bottle: str
) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact", {"product_system_id": bottle, "method_id": GWP_ID}
            )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid" and "has no reference process" in payload["message"]


async def test_an_explicit_demand_names_its_reference(server: FastMCP, widget: uuid.UUID) -> None:
    async with Client(server) as client:
        foreground = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(widget),
                    "method_id": GWP_ID,
                    "demand": [{"ref": {"kind": "foreground", "code": "widget"}, "amount": 1.0}],
                },
            )
        ).structured_content["value"]
        background = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(widget),
                    "method_id": GWP_ID,
                    "demand": [
                        {
                            "ref": {
                                "kind": "background",
                                "database": FIXTURE_DB,
                                "id": CODES["steel"],
                            },
                            "amount": 1.0,
                        }
                    ],
                },
            )
        ).structured_content["value"]
    assert foreground["scores"][0]["value"] == pytest.approx(4.158)
    assert background["scores"][0]["value"] == pytest.approx(2.78)


async def test_a_background_demand_on_an_empty_system_is_scored(
    server: FastMCP, context: ServerContext, bottle: str
) -> None:
    demand = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)
    method = await context.inventory.resolve_method(FIXTURE_DB, GWP_ID)
    own = await context.calculation.score(System(database=FIXTURE_DB), [demand], method)
    async with Client(server) as client:
        scored = (
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": bottle,
                    "method_id": GWP_ID,
                    "demand": [
                        {
                            "ref": {
                                "kind": "background",
                                "database": FIXTURE_DB,
                                "id": CODES["steel"],
                            },
                            "amount": 1.0,
                        }
                    ],
                },
            )
        ).structured_content["value"]
    assert scored["scores"][0]["value"] == pytest.approx(own.value)


async def test_a_demand_naming_a_product_system_is_refused(
    server: FastMCP, widget: uuid.UUID
) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError, match="product_system_id"):
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": str(widget),
                    "method_id": GWP_ID,
                    "demand": [
                        {
                            "ref": {
                                "kind": "foreground",
                                "code": "widget",
                                "product_system_id": str(uuid.uuid4()),
                            },
                            "amount": 1.0,
                        }
                    ],
                },
            )


async def test_impact_of_scores_a_system_and_each_variant(
    context: ServerContext, varied: uuid.UUID
) -> None:
    stored = await context.storage.get_product_system(varied)
    methods = [await context.inventory.resolve_method(stored.database.name, GWP_ID)]
    result = await impact_of(
        context.calculation, materialize(stored), methods, variants=["half", "double_steel"]
    )
    assert result.product_system == "widget_varied"
    assert result.scores[0].value == pytest.approx(4.158)
    assert [v.name for v in result.variants] == ["half", "double_steel"]
    assert result.variants[0].deltas == [pytest.approx(-0.5)]
    assert result.variants[1].deltas == [pytest.approx(1.39)]
    assert result.uncertainty is None
    assert result.treatments_run_backwards == []
    assert all(v.treatments_run_backwards == [] for v in result.variants)
    assert all(v.uncertainty is None and v.paired_deltas is None for v in result.variants)


async def test_impact_of_names_a_positive_input_to_a_treatment_in_the_base_and_each_variant(
    context: ServerContext, varied: uuid.UUID
) -> None:
    stored = await context.storage.get_product_system(varied)
    methods = [await context.inventory.resolve_method(stored.database.name, GWP_ID)]
    steel = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])
    result = await impact_of(
        context.calculation,
        materialize(stored),
        methods,
        variants=["half", "double_steel"],
        treatments=frozenset({steel}),
    )
    # the frame and the widget both take steel
    base = ["frame · steel at 2.4", "widget · steel at 0.5"]
    assert result.treatments_run_backwards == base
    # the scenario doubles the widget's steel, so its variant names the doubled amount
    assert [v.treatments_run_backwards for v in result.variants] == [
        base,
        ["frame · steel at 2.4", "widget · steel at 1"],
    ]


async def test_a_loop_holding_a_credit_is_named_beside_the_scores(
    server: FastMCP, widget: uuid.UUID, credited_stored: ProductSystem
) -> None:
    async with Client(server) as client:
        plain = await client.call_tool(
            "calculate_impact", {"product_system_id": str(widget), "method_id": GWP_ID}
        )
        named = await client.call_tool(
            "calculate_impact",
            {
                "product_system_id": str(credited_stored.id),
                "method_id": GWP_ID,
                "demand": WIDGET_DEMAND,
                "variants": ["used"],
            },
        )
    assert plain.structured_content["value"]["credit_loops"] == []
    value = named.structured_content["value"]
    assert value["credit_loops"] == [["frame", "widget"]]
    # the scenario turns the credit into a use of two widgets
    assert value["variants"][0]["credit_loops"] == []


async def test_a_system_that_fails_validation_still_calculates(
    full_server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "island")
    system.name = "widget_island"
    system.processes.append(
        Process(
            id=uuid.uuid5(system.id, "loose"),
            code="loose",
            name="loose",
            unit="unit",
            location="GLO",
            reference_product="loose",
            exchanges=[
                Exchange(
                    id=uuid.uuid5(system.id, "loose:production"),
                    type="production",
                    name="loose",
                    amount=1.0,
                    unit="unit",
                )
            ],
        )
    )
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        report = await client.call_tool(
            "validate_product_system", {"product_system_id": str(system.id)}
        )
        scored = await client.call_tool(
            "calculate_impact", {"product_system_id": str(system.id), "method_id": GWP_ID}
        )
    assert [e["code"] for e in report.structured_content["value"]["errors"]] == [
        "island_activities_detected"
    ]
    # nothing uses the loose process, so the widget scores what it scores alone
    assert scored.structured_content["value"]["scores"][0]["value"] == pytest.approx(4.158)


async def test_a_stale_scenario_refusal_names_the_entry_that_moved_the_base(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        made = await client.call_tool(
            "create_product_system", {"name": "moved", "database": FIXTURE_DB}
        )
        system = made.structured_content["value"]["id"]
        await client.call_tool(
            "create_process",
            {
                "product_system_id": system,
                "code": "p",
                "name": "p",
                "unit": "unit",
                "reference_product": "p",
            },
        )
        steel = await client.call_tool(
            "create_exchange",
            {
                "product_system_id": system,
                "code": "p",
                "type": "product",
                "amount": 1.0,
                "input": {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]},
            },
        )
        exchange = steel.structured_content["value"]["id"]
        await client.call_tool(
            "create_scenario",
            {
                "product_system_id": system,
                "name": "double",
                "overrides": [{"kind": "exchange", "exchange_id": exchange, "multiplier": 2}],
            },
        )
        await client.call_tool(
            "update_product_system", {"product_system_id": system, "notes": "no move"}
        )
        moved = await client.call_tool(
            "update_exchange",
            {"product_system_id": system, "exchange_id": exchange, "amount": 3.0},
        )
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact",
                {
                    "product_system_id": system,
                    "method_id": GWP_ID,
                    "demand": [{"ref": {"kind": "foreground", "code": "p"}, "amount": 1.0}],
                    "variants": ["double"],
                },
            )
    seq = moved.structured_content["entry"]["seq"]
    message = json.loads(str(caught.value))["message"]
    assert f"entry {seq}" in message and moved.structured_content["entry"]["message"] in message


async def test_a_system_on_another_build_is_refused_with_its_remedy(
    server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "another build")
    system.name = "widget_elsewhere"
    system.database = system.database.model_copy(update={"fingerprint": "0" * 64})
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact", {"product_system_id": str(system.id), "method_id": GWP_ID}
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "conflict"
    assert payload["details"] == {
        "database": FIXTURE_DB,
        "named": "0" * 64,
        "installed": FIXTURE_FINGERPRINT,
    }
    assert payload["message"].endswith(
        "install the build the system names, or run rebase_database to move it onto the "
        "installed build"
    )
