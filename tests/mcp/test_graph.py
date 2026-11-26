from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import Implementation
from starlette.testclient import TestClient

from ecosemantic import workspace as python_api
from ecosemantic.errors import NotFound
from ecosemantic.geometry import LINKED_HEIGHT, ROW_HEIGHT
from ecosemantic.layout import arrange
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.direct import run_tool
from ecosemantic.mcp.graph import Arrangement, CardSpot, arrange_graph, graph_layout
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import (
    Case,
    Exchange,
    ExchangeOverride,
    Parameter,
    Process,
    ProductSystem,
    Scenario,
)
from ecosemantic.model.refs import ElementaryFlowRef, ForegroundRef
from ecosemantic.package.sidecar import LAYOUT_FILE, SIDECAR_DIR
from ecosemantic.ports.inventory import InventoryPort, no_flow
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import ElementaryFlow, Layout, Spot
from ecosemantic.troubles import score, troubles
from ecosemantic.view.app import build_view
from tests.conftest import fixture_system, frame_system, widget_linking
from tests.fixture_data import FIXTURE_BIO, FLOW_IDS
from tests.layout_fixtures import staged_nine


async def test_the_map_names_every_card_and_says_what_is_wrong(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "graph_layout", {"product_system_id": str(fixture_system_stored.id), "detail": "full"}
        )
    answer = out.structured_content["value"]
    assert all(p.code in answer["map"] for p in fixture_system_stored.processes)
    assert {row["code"] for row in answer["cards"]} == {
        p.code for p in fixture_system_stored.processes
    }
    assert set(answer) == {
        "kind",
        "map",
        "cards",
        "edges",
        "troubles",
        "score",
        "bounds",
        "scaling",
        "stages",
        "shared_suppliers",
        "card",
    }
    assert all(t["kind"] != "cards_overlap" for t in answer["troubles"])
    assert all(len(e["points"]) >= 2 for e in answer["edges"])
    assert answer["bounds"]["width"] > 0


async def test_graph_layout_answers_the_stages_and_their_regions(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    system.process("widget").metadata["life_cycle_stage"] = "assembly"
    system.process("frame").metadata["life_cycle_stage"] = "materials"
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        staged = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
            )
        ).structured_content["value"]
        plain = (
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        ).structured_content["value"]
    assert [entry["stage"] for entry in staged["stages"]] == ["assembly", "materials"]
    assert [entry["codes"] for entry in staged["stages"]] == [["widget"], ["frame"]]
    assert all(len(entry["regions"]) == 1 for entry in staged["stages"])
    assert staged["shared_suppliers"] == []
    assert plain["stages"] == []
    assert plain["shared_suppliers"] == []


async def test_arranging_holds_the_cards_it_names(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    code = fixture_system_stored.processes[0].code
    try:
        async with Client(full_server) as client:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(fixture_system_stored.id),
                    "placements": [{"code": code, "x": 5.0, "y": 6.0}],
                },
            )
            out = await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        cards = {row["code"]: row for row in out.structured_content["value"]["cards"]}
        assert (cards[code]["x"], cards[code]["y"], cards[code]["held"]) == (5.0, 6.0, True)
    finally:
        # fixture_system_stored is session-scoped, so what this holds is released again
        await context.storage.put_layout(fixture_system_stored.id, Layout(), expected=None)


async def test_a_released_card_returns_to_the_automatic_layout(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    await context.storage.put_layout(system.id, Layout(), expected=None)
    try:
        async with Client(full_server) as client:
            automatic = await _layout(client, system)
            held = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": code, "x": 5.0, "y": 6.0}],
                            "detail": "full",
                        },
                    )
                ).structured_content["value"]
            )
            released = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [],
                            "detail": "full",
                            "release": [code],
                        },
                    )
                ).structured_content["value"]
            )
        pinned = next(c for c in held.cards if c.code == code)
        assert (pinned.x, pinned.y, pinned.held) == (5.0, 6.0, True)
        assert released.cards == automatic.cards
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_a_card_placed_and_released_at_once_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    await context.storage.put_layout(system.id, Layout(), expected=None)
    try:
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [{"code": code, "x": 1.0, "y": 2.0}],
                        "release": [code],
                    },
                )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid" and code in payload["message"]
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_releasing_a_card_that_is_not_held_changes_nothing(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    await context.storage.put_layout(system.id, Layout(), expected=None)
    try:
        async with Client(full_server) as client:
            before = await _layout(client, system)
            answer = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [],
                            "detail": "full",
                            "release": [system.processes[0].code],
                        },
                    )
                ).structured_content["value"]
            )
        assert answer.cards == before.cards
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_release_all_lets_every_held_code_go_before_the_placements_apply(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    widget, frame = (p.code for p in system.processes)
    await context.storage.put_layout(
        system.id,
        Layout(held={widget: Spot(x=1.0, y=2.0), "gone": Spot(x=3.0, y=4.0)}),
        expected=None,
    )
    try:
        async with Client(full_server) as client:
            answer = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": frame, "x": 5.0, "y": 6.0}],
                            "detail": "full",
                            "release_all": True,
                        },
                    )
                ).structured_content["value"]
            )
        assert (await context.storage.get_layout(system.id)).held == {
            frame: Spot(x=5.0, y=6.0, placed_by="agent")
        }
        assert [c.code for c in answer.cards if c.held] == [frame]
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_release_all_beside_release_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    held = Layout(held={code: Spot(x=1.0, y=2.0)})
    await context.storage.put_layout(system.id, held, expected=None)
    try:
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [],
                        "release": [code],
                        "release_all": True,
                    },
                )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid"
        assert payload["message"] == "release and release_all both let cards go; pass one of them"
        assert await context.storage.get_layout(system.id) == held
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_release_agent_holds_lets_an_agents_hold_go_and_keeps_every_other(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    widget, frame = (p.code for p in system.processes)
    held = Layout(
        held={
            widget: Spot(x=1.0, y=2.0, placed_by="agent"),
            frame: Spot(x=3.0, y=4.0, placed_by="person"),
            "service-held": Spot(x=5.0, y=6.0, placed_by="service"),
            "no-placer": Spot(x=7.0, y=8.0),
        }
    )
    await context.storage.put_layout(system.id, held, expected=None)
    try:
        async with Client(full_server) as client:
            answer = await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [],
                    "release_agent_holds": True,
                },
            )
        written = await context.storage.get_layout(system.id)
        assert written.held == {
            frame: Spot(x=3.0, y=4.0, placed_by="person"),
            "service-held": Spot(x=5.0, y=6.0, placed_by="service"),
            "no-placer": Spot(x=7.0, y=8.0),
        }
        assert answer.structured_content["value"]["saved"] is True
        assert answer.structured_content["value"]["score_before"] is not None
        assert answer.structured_content["value"]["score_after"] is not None
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_release_agent_holds_saves_the_better_drawing_it_leaves(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _stored_nine(context)
    try:
        async with Client(full_server) as client:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": "refinery", "x": 0.0, "y": 0.0}],
                },
            )
            released = (
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [],
                        "release_agent_holds": True,
                    },
                )
            ).structured_content["value"]
        assert released["saved"] is True
        assert released["score_after"] < released["score_before"]
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.delete_product_system(system.id, context.actor)


async def test_release_agent_holds_beside_release_all_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    held = Layout(held={code: Spot(x=1.0, y=2.0, placed_by="agent")})
    await context.storage.put_layout(system.id, held, expected=None)
    try:
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [],
                        "release_agent_holds": True,
                        "release_all": True,
                    },
                )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid"
        assert payload["message"] == (
            "release_agent_holds and release_all both let cards go; pass one of them"
        )
        assert await context.storage.get_layout(system.id) == held
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_the_layout_draws_a_linked_system_and_answers_every_edge(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(widget.id), "detail": "full"}
            )
        ).structured_content["value"]
    card = f"system:{frame.id}"
    assert card in {c["code"] for c in answer["cards"]}
    assert any(e["provider"] == card and e["consumer"] == "widget" for e in answer["edges"])
    widget_card = next(c for c in answer["cards"] if c["code"] == "widget")
    # steel, electricity and the frame link are inputs; the CO2 emission sits among the outputs
    assert widget_card["shown_inputs"] == 3


async def test_every_card_is_scaled_to_the_functional_unit(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        ).structured_content["value"]
    assert answer["scaling"] is None
    cards = {c["code"]: c for c in answer["cards"]}
    assert cards["widget"]["activity"] == pytest.approx(1.0)
    assert cards["frame"]["activity"] == pytest.approx(0.25)
    frame = fixture_system_stored.process("frame")
    steel = next(e for e in frame.exchanges if e.type == "product")
    assert cards["frame"]["scaled"][str(steel.id)] == pytest.approx(0.25 * 2.4)


async def test_a_linked_card_holds_its_reference_processs_production_at_its_level(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(widget.id), "detail": "full"}
            )
        ).structured_content["value"]
    card = next(c for c in answer["cards"] if c["code"] == f"system:{frame.id}")
    production = next(e for e in frame.processes[0].exchanges if e.type == "production")
    assert card["activity"] == pytest.approx(0.25)
    assert card["scaled"] == {str(production.id): pytest.approx(0.25)}


class CountedFlows:
    """The inventory it wraps, counting the flow reads a tool makes of it."""

    def __init__(self, inventory: InventoryPort) -> None:
        self.inventory = inventory
        self.many: list[tuple[str, list[str]]] = []
        self.single: list[ElementaryFlowRef] = []

    async def get_elementary_flow(self, ref: ElementaryFlowRef) -> ElementaryFlow:
        self.single.append(ref)
        return await self.inventory.get_elementary_flow(ref)

    async def get_elementary_flows(self, database: str, ids: Sequence[str]) -> list[ElementaryFlow]:
        self.many.append((database, list(ids)))
        return await self.inventory.get_elementary_flows(database, ids)

    def __getattr__(self, name: str) -> object:
        return getattr(self.inventory, name)


def _with_an_extra_emission(system: ProductSystem) -> ProductSystem:
    """The fixture's widget with a second elementary input on the same flows database."""
    varied = system.model_copy(deep=True, update={"id": uuid.uuid4()})
    varied.process("widget").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="elementary",
            name="Methane, fossil",
            amount=0.02,
            unit="kilogram",
            input=ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["ch4"]),
        )
    )
    return varied


async def test_a_layout_reads_its_flows_in_one_call_per_database(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = _with_an_extra_emission(fixture_system_stored)
    await context.storage.put_product_system(system, context.actor, "created")
    counted = CountedFlows(context.inventory)
    wrapped = dataclasses.replace(context, inventory=counted)
    one_read = await graph_layout(wrapped, str(system.id), detail="full")
    assert [database for database, _ in counted.many] == [FIXTURE_BIO]
    assert {FLOW_IDS["co2"], FLOW_IDS["ch4"]} == set(counted.many[0][1])
    assert counted.single == []
    assert one_read == await graph_layout(context, str(system.id), detail="full")


async def test_a_layout_names_the_flow_its_database_lacks(ports_only: ServerContext) -> None:
    system = _with_an_extra_emission(fixture_system().product_system)
    absent = ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["ch4"][:-1] + "0")
    system.process("widget").exchanges[-1].input = absent
    await ports_only.storage.put_product_system(system, ports_only.actor, "created")
    counted = CountedFlows(ports_only.inventory)
    wrapped = dataclasses.replace(ports_only, inventory=counted)
    with pytest.raises(NotFound) as raised:
        await graph_layout(wrapped, str(system.id))
    assert str(raised.value) == str(no_flow(absent))
    assert [database for database, _ in counted.many] == [FIXTURE_BIO]
    assert counted.single == []


def _without_reference(system: ProductSystem) -> None:
    system.reference_process = None


@pytest.mark.parametrize(
    ("break_it", "named"),
    [(_without_reference, "names no reference process")],
)
async def test_a_system_the_engine_cannot_solve_says_why_and_scales_nothing(
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
    context: ServerContext,
    break_it: Callable[[ProductSystem], None],
    named: str,
) -> None:
    unsolvable = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    break_it(unsolvable)
    await context.storage.put_product_system(unsolvable, context.actor, "created")
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(unsolvable.id), "detail": "full"}
            )
        ).structured_content["value"]
    assert named in answer["scaling"]
    assert all(c["scaled"] is None and c["activity"] is None for c in answer["cards"])


async def test_a_stale_pin_does_not_withhold_the_scaled_view(
    full_server: FastMCP, context: ServerContext
) -> None:
    frame = frame_system().model_copy(update={"id": uuid.uuid4()})
    await context.storage.put_product_system(frame, context.actor, "created")
    widget = widget_linking(frame).model_copy(update={"id": uuid.uuid4()})
    await context.storage.put_product_system(widget, context.actor, "created")
    moved = await context.storage.get_product_system(frame.id)
    moved.processes[0].exchanges[1].amount = 5.0
    await context.storage.put_product_system(moved, context.actor, "edited")
    async with Client(full_server) as client:
        report = (
            await client.call_tool("validate_product_system", {"product_system_id": str(widget.id)})
        ).structured_content["value"]
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(widget.id), "detail": "full"}
            )
        ).structured_content["value"]
    assert {c["id"] for c in report["cases"] if not c["passed"]} == {"links_current"}
    assert answer["scaling"] is None
    assert all(c["scaled"] is not None for c in answer["cards"])


async def test_a_stale_scenario_does_not_withhold_the_scaled_view(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    exchange = system.process("frame").exchanges[1]
    system.scenarios = [
        Scenario(
            name="old",
            overrides=[ExchangeOverride(exchange_id=exchange.id, multiplier=2.0)],
            base_hash="behind",
        )
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
            )
        ).structured_content["value"]
    assert answer["scaling"] is None
    assert all(c["scaled"] is not None for c in answer["cards"])


async def test_a_stale_scenario_named_as_the_variant_is_refused_as_a_calculation_refuses_it(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    exchange = system.process("frame").exchanges[1]
    system.scenarios = [
        Scenario(
            name="old",
            overrides=[ExchangeOverride(exchange_id=exchange.id, multiplier=2.0)],
            base_hash="behind",
        )
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "graph_layout", {"product_system_id": str(system.id), "variant": "old"}
            )
    payload = json.loads(str(caught.value))
    assert payload["details"]["scenario"] == "old" and "rebase_scenario" in payload["message"]


async def test_a_scenario_named_as_the_variant_scales_its_overridden_amounts(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    frame = next(e for e in system.process("widget").exchanges if e.name == "frame")
    system.scenarios = [
        Scenario(
            name="double frame",
            overrides=[ExchangeOverride(exchange_id=frame.id, multiplier=2.0)],
            base_hash=base_pin(system),
        )
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        answer = await _layout(client, system, "double frame")
    assert next(c for c in answer.cards if c.code == "frame").activity == pytest.approx(0.5)
    [edge] = answer.edges
    assert edge.label.per_unit == "0.5 kg"


async def test_an_island_runs_at_level_zero_and_is_still_scaled(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    frame = system.process("frame")
    production = frame.exchanges[0].model_copy(update={"id": uuid.uuid4()})
    system.processes.append(
        Process(
            id=uuid.uuid4(),
            code="island",
            name="island",
            unit="kilogram",
            location="GLO",
            reference_product="island",
            exchanges=[production],
        )
    )
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
            )
        ).structured_content["value"]
    island = next(c for c in answer["cards"] if c["code"] == "island")
    assert answer["scaling"] is None
    assert island["activity"] == 0.0
    assert island["scaled"] == {str(production.id): 0.0}


async def test_the_reported_score_is_measured_on_the_labels_the_answer_carries(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        ).structured_content["value"]
    arrangement = Arrangement.model_validate(answer)
    assert all(e.label.scaled is not None for e in arrangement.edges)
    assert arrangement.score == score(troubles(arrangement.cards, arrangement.edges))


def _with_a_heavy_case(system: ProductSystem) -> ProductSystem:
    """The fixture with the widget's frame set by a parameter, and a case doubling it."""
    varied = system.model_copy(deep=True, update={"id": uuid.uuid4()})
    varied.parameters = [Parameter(name="frame_mass", value=0.25, unit="kilogram")]
    varied.cases = [Case(name="heavy frame", values={"frame_mass": 0.5})]
    frame = next(e for e in varied.process("widget").exchanges if e.name == "frame")
    frame.formula = "frame_mass"
    return varied


async def _layout(client: Client, system: ProductSystem, variant: str | None = None) -> Arrangement:
    arguments: dict[str, str] = {"product_system_id": str(system.id), "detail": "full"}
    if variant is not None:
        arguments["variant"] = variant
    out = await client.call_tool("graph_layout", arguments)
    return Arrangement.model_validate(out.structured_content["value"])


async def test_the_arrangement_is_drawn_under_the_case_it_names(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = _with_a_heavy_case(fixture_system_stored)
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        base = await _layout(client, system)
        heavy = await _layout(client, system, "heavy frame")
    steel = next(e for e in system.process("frame").exchanges if e.type == "product")
    cards = {c.code: c for c in base.cards}
    varied = {c.code: c for c in heavy.cards}
    assert cards["frame"].activity == pytest.approx(0.25)
    assert varied["frame"].activity == pytest.approx(0.5)
    assert varied["frame"].scaled == {
        next(e.id for e in system.process("frame").exchanges if e.type == "production"): (
            pytest.approx(0.5)
        ),
        steel.id: pytest.approx(0.5 * 2.4),
    }
    [edge] = base.edges
    [varied_edge] = heavy.edges
    assert (edge.label.per_unit, edge.label.scaled) == ("0.25 kg", "0.25 kg")
    assert (varied_edge.label.per_unit, varied_edge.label.scaled) == ("0.5 kg", "0.5 kg")
    assert "frame · 0.5 kg" in heavy.map and "frame · 0.25 kg" in base.map


async def test_arranging_under_a_case_answers_the_drawing_under_it(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = _with_a_heavy_case(fixture_system_stored)
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        out = await client.call_tool(
            "arrange_graph",
            {
                "product_system_id": str(system.id),
                "placements": [{"code": "frame", "x": 0.0, "y": 0.0}],
                "detail": "full",
                "variant": "heavy frame",
            },
        )
    answer = Arrangement.model_validate(out.structured_content["value"])
    assert next(c for c in answer.cards if c.code == "frame").activity == pytest.approx(0.5)


async def test_an_unknown_variant_is_refused_by_name(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "variant": "ghost"},
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "not_found" and "ghost" in payload["message"]


async def test_a_loop_that_delivers_nothing_draws_every_card_and_names_the_loop(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"id": uuid.uuid4()})
    frame = system.process("frame")
    frame.exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="frame",
            amount=2.0,
            unit="kilogram",
            input=ForegroundRef(code="frame"),
        )
    )
    await context.storage.put_product_system(system, context.actor, "created")
    async with Client(full_server) as client:
        answer = await _layout(client, system)
    assert {c.code for c in answer.cards} == {"widget", "frame"}
    assert answer.scaling == "frame uses 2 of its own product and makes 1; it delivers none"
    assert all(c.scaled is None and c.activity is None for c in answer.cards)
    assert all(e.label.scaled is None for e in answer.edges)


async def test_arranging_records_a_call_that_names_the_cards_it_placed(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    widget, frame = (p.code for p in system.processes)
    await context.storage.put_layout(system.id, Layout(), expected=None)
    try:
        async with Client(
            full_server, client_info=Implementation(name="arranger", version="1")
        ) as client:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": widget, "x": 5.0, "y": 6.0}],
                },
            )
        (call,) = await context.activity.list_calls(agent="arranger")
        assert call.tool == "arrange_graph"
        assert call.summary is not None
        assert call.summary.count == 1
        assert call.summary.noun == "cards placed"
        assert [item.label for item in call.summary.items] == [widget]
        assert frame not in [item.label for item in call.summary.items]
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


class CountedWrites:
    """The storage it wraps, counting the layouts put into it and keeping nothing of its own."""

    def __init__(self, storage: StoragePort) -> None:
        self.storage = storage
        self.layouts: list[Layout] = []

    async def put_layout(
        self, product_system_id: uuid.UUID, layout: Layout, *, expected: Layout | None
    ) -> Layout:
        self.layouts.append(layout)
        return await self.storage.put_layout(product_system_id, layout, expected=expected)

    def __getattr__(self, name: str) -> object:
        return getattr(self.storage, name)


@pytest.mark.parametrize("x", ["inf", "nan", 1e200, 100000.5, -100000.5])
async def test_a_placement_outside_the_canvas_is_refused_and_nothing_is_saved(
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
    context: ServerContext,
    x: float | str,
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    before = await context.storage.get_layout(system.id)
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": code, "x": x, "y": 0.0}],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert await context.storage.get_layout(system.id) == before


async def test_a_placement_at_the_edge_of_the_canvas_is_held(
    full_server: FastMCP, context: ServerContext
) -> None:
    frame = frame_system().model_copy(deep=True, update={"id": uuid.uuid4()})
    await context.storage.put_product_system(frame, context.actor, "created")
    code = frame.processes[0].code
    arguments = {"product_system_id": str(frame.id)}
    try:
        async with Client(full_server) as client:
            edge = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            **arguments,
                            "placements": [{"code": code, "x": 100000.0, "y": -100000.0}],
                            "detail": "full",
                        },
                    )
                ).structured_content["value"]
            )
            centred = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            **arguments,
                            "placements": [{"code": code, "x": 0.0, "y": 0.0}],
                            "detail": "full",
                        },
                    )
                ).structured_content["value"]
            )
        card = next(c for c in edge.cards if c.code == code)
        assert (card.x, card.y, card.held) == (100000.0, -100000.0, True)
        assert edge.map == centred.map
    finally:
        await context.storage.put_layout(frame.id, Layout(), expected=None)


async def test_an_oversized_map_saves_no_placement(
    fixture_system_stored: ProductSystem,
    context: ServerContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = fixture_system_stored
    widget, frame = (p.code for p in system.processes)
    held = Layout(held={widget: Spot(x=5.0, y=6.0)})
    await context.storage.put_layout(system.id, held, expected=None)
    monkeypatch.setattr("ecosemantic.textmap.MAX_MAP_CELLS", 5000)
    counted = CountedWrites(context.storage)
    try:
        async with Client(build_server(dataclasses.replace(context, storage=counted))) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [{"code": frame, "x": 90000.0, "y": 90000.0}],
                        "detail": "full",
                    },
                )
        payload = json.loads(str(caught.value))
        assert payload["error"] == "invalid"
        assert "5000" in payload["message"] and "\n" not in payload["message"]
        assert counted.layouts == []
        assert await context.storage.get_layout(system.id) == held
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_a_code_the_drawing_lacks_is_refused_and_nothing_is_saved(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    before = await context.storage.get_layout(system.id)
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": "nope", "x": 1.0, "y": 2.0}],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid" and "'nope'" in payload["message"]
    assert await context.storage.get_layout(system.id) == before


async def test_a_code_named_twice_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    before = await context.storage.get_layout(system.id)
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [
                        {"code": code, "x": 1.0, "y": 2.0},
                        {"code": code, "x": 3.0, "y": 4.0},
                    ],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid" and code in payload["message"]
    assert await context.storage.get_layout(system.id) == before


async def test_a_refusal_names_five_codes_and_counts_the_rest(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    codes = [f"x{number}" for number in range(1, 8)]
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(fixture_system_stored.id),
                    "placements": [{"code": code, "x": 1.0, "y": 2.0} for code in codes],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert "'x1', 'x2', 'x3', 'x4', 'x5' and 2 more" in payload["message"]
    assert "x6" not in payload["message"]


async def test_a_held_code_no_card_draws_is_released_by_name(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    await context.storage.put_layout(
        system.id, Layout(held={"gone": Spot(x=1.0, y=2.0)}), expected=None
    )
    try:
        async with Client(full_server) as client:
            answer = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [],
                            "detail": "full",
                            "release": ["gone"],
                        },
                    )
                ).structured_content["value"]
            )
        assert answer.cards
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_a_release_of_a_code_neither_drawn_nor_held_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    before = await context.storage.get_layout(system.id)
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [],
                    "release": ["nope"],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid" and "'nope'" in payload["message"]
    assert await context.storage.get_layout(system.id) == before


async def test_a_variant_the_system_lacks_saves_nothing(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    before = await context.storage.get_layout(system.id)
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": code, "x": 1.0, "y": 2.0}],
                    "variant": "no such",
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "not_found"
    assert await context.storage.get_layout(system.id) == before


async def test_a_linked_system_s_card_can_be_placed(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem], context: ServerContext
) -> None:
    widget, frame = linked_stored
    card = f"system:{frame.id}"
    try:
        async with Client(full_server) as client:
            answer = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(widget.id),
                            "placements": [{"code": card, "x": 5.0, "y": 6.0}],
                            "detail": "full",
                        },
                    )
                ).structured_content["value"]
            )
        placed = next(c for c in answer.cards if c.code == card)
        assert (placed.x, placed.y, placed.held) == (5.0, 6.0, True)
        assert (await context.storage.get_layout(widget.id)).held == {
            card: Spot(x=5.0, y=6.0, placed_by="agent")
        }
    finally:
        await context.storage.put_layout(widget.id, Layout(), expected=None)


async def test_a_layout_the_store_holds_already_is_not_written(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    await context.storage.put_layout(
        system.id, Layout(held={code: Spot(x=5.0, y=6.0)}), expected=None
    )
    counted = CountedWrites(context.storage)
    queue = context.events.subscribe(system.id)
    try:
        answer = await arrange_graph(
            dataclasses.replace(context, storage=counted),
            str(system.id),
            [CardSpot(code=code, x=5.0, y=6.0)],
            detail="full",
        )
        assert counted.layouts == []
        assert queue.empty()
        assert next(c for c in answer.value.cards if c.code == code).held
    finally:
        context.events.unsubscribe(system.id, queue)
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_a_hold_keeps_its_placer_where_it_stands_and_takes_the_mover_s_when_moved(
    full_server: FastMCP, context: ServerContext
) -> None:
    whole = fixture_system().product_system
    assert whole is not None
    system = whole.model_copy(deep=True, update={"id": uuid.uuid4()})
    await context.storage.put_product_system(system, context.actor, "created")
    one, other = (p.code for p in system.processes)
    counted = CountedWrites(context.storage)
    writing = dataclasses.replace(context, storage=counted)
    try:
        async with Client(full_server) as client:
            first = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": one, "x": 5.0, "y": 6.0}],
                            "detail": "full",
                        },
                    )
                ).structured_content["value"]
            )
            await run_tool(
                full_server,
                context,
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": other, "x": 9.0, "y": 10.0}],
                },
            )
        placed = (await context.storage.get_layout(system.id)).held
        assert (placed[one].placed_by, placed[other].placed_by) == ("agent", "person")
        assert {card.code: card.placed_by for card in first.cards} == {one: "agent", other: None}
        again = await arrange_graph(
            writing,
            str(system.id),
            [CardSpot(code=one, x=5.0, y=6.0), CardSpot(code=other, x=9.0, y=10.0)],
            detail="full",
        )
        assert counted.layouts == []
        assert (await context.storage.get_layout(system.id)).held == placed
        assert {card.code: card.placed_by for card in again.value.cards if card.held} == {
            one: "agent",
            other: "person",
        }
        moved = await arrange_graph(
            writing, str(system.id), [CardSpot(code=other, x=1.0, y=2.0)], detail="full"
        )
        assert (await context.storage.get_layout(system.id)).held == {
            one: placed[one],
            other: Spot(x=1.0, y=2.0, placed_by="agent"),
        }
        assert next(card for card in moved.value.cards if card.code == other).placed_by == "agent"
    finally:
        await context.storage.delete_product_system(system.id, context.actor)


async def test_simultaneous_moves_of_two_cards_keep_both(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    widget, frame = (p.code for p in system.processes)
    await context.storage.put_layout(system.id, Layout(), expected=None)
    try:
        async with Client(full_server) as client:
            for turn in range(5):
                x = 10.0 + turn
                await asyncio.gather(
                    client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": widget, "x": x, "y": 1.0}],
                        },
                    ),
                    client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": frame, "x": x, "y": 2.0}],
                        },
                    ),
                )
                assert await context.storage.get_layout(system.id) == Layout(
                    held={
                        widget: Spot(x=x, y=1.0, placed_by="agent"),
                        frame: Spot(x=x, y=2.0, placed_by="agent"),
                    }
                )
    finally:
        await context.storage.put_layout(system.id, Layout(), expected=None)


async def test_a_slow_arrangement_leaves_the_event_loop_free(
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drawn = arrange

    def delayed(*args, **kwargs):
        time.sleep(1.0)
        return drawn(*args, **kwargs)

    monkeypatch.setattr("ecosemantic.mcp.graph.arrange", delayed)
    gaps: list[float] = []
    answered = asyncio.Event()

    async def sample() -> None:
        last = time.perf_counter()
        while not answered.is_set():
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    sampler = asyncio.create_task(sample())
    try:
        async with Client(full_server) as client:
            out = await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": "full"},
            )
        assert out.structured_content["value"]["map"]
    finally:
        answered.set()
        await sampler
    assert max(gaps) < 0.25


async def test_an_unreadable_layout_names_release_all_and_no_path(
    full_server: FastMCP, context: ServerContext
) -> None:
    whole = fixture_system().product_system
    assert whole is not None
    system = whole.model_copy(deep=True, update={"id": uuid.uuid4()})
    await context.storage.put_product_system(system, context.actor, "created")
    code = system.processes[0].code
    layout_file = context.systems_dir / str(system.id) / SIDECAR_DIR / LAYOUT_FILE
    layout_file.write_text(json.dumps({"held": {code: {"x": None, "y": 0}}}), encoding="utf-8")
    try:
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
                )
            payload = json.loads(str(caught.value))
            assert payload["error"] == "unavailable"
            assert "release_all" in payload["message"]
            assert str(context.systems_dir) not in json.dumps(payload)
            assert "hint" not in json.dumps(payload)
            released = await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [],
                    "detail": "full",
                    "release_all": True,
                },
            )
            assert {c["code"] for c in released.structured_content["value"]["cards"]} == {
                p.code for p in system.processes
            }
            again = await client.call_tool(
                "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
            )
            assert not any(c["held"] for c in again.structured_content["value"]["cards"])
    finally:
        await context.storage.delete_product_system(system.id, context.actor)


NOWHERE = Path("/nonexistent-static")


async def _stored_nine(context: ServerContext) -> ProductSystem:
    system = staged_nine()
    await context.storage.put_product_system(system, context.actor, "created")
    return system


async def test_full_carries_the_map_and_drawing_does_not(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _stored_nine(context)
    try:
        async with Client(full_server) as client:
            full = (
                await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(system.id), "detail": "full"},
                )
            ).structured_content["value"]
            drawing = (
                await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(system.id), "detail": "drawing"},
                )
            ).structured_content["value"]
    finally:
        await context.storage.delete_product_system(system.id, context.actor)
    assert isinstance(full["map"], str) and full["map"]
    assert (full["kind"], drawing["kind"]) == ("arrangement", "arrangement")
    assert drawing["map"] is None
    assert {**drawing, "map": full["map"]} == full


async def test_a_map_over_the_cell_limit_names_the_drawing_detail(
    full_server: FastMCP, context: ServerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = await _stored_nine(context)
    code = system.processes[0].code
    far = {"code": code, "x": 90000.0, "y": 90000.0}
    try:
        monkeypatch.setattr("ecosemantic.textmap.MAX_MAP_CELLS", 5000)
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "graph_layout", {"product_system_id": str(system.id), "detail": "full"}
                )
            payload = json.loads(str(caught.value))
            assert payload["error"] == "invalid"
            assert 'detail="drawing"' in payload["message"]
            drawn = (
                await client.call_tool(
                    "graph_layout", {"product_system_id": str(system.id), "detail": "drawing"}
                )
            ).structured_content["value"]
            assert drawn["map"] is None and len(drawn["cards"]) == len(system.processes)
            with pytest.raises(ToolError):
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [far],
                        "detail": "full",
                    },
                )
        assert await context.storage.get_layout(system.id) == Layout()
        async with Client(full_server) as client:
            saved = (
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [far],
                        "detail": "drawing",
                    },
                )
            ).structured_content["value"]
        assert saved["map"] is None
        assert (await context.storage.get_layout(system.id)).held[code].x == 90000.0
    finally:
        await context.storage.delete_product_system(system.id, context.actor)


def _cards(answer: dict) -> dict[str, tuple[float, float, bool, str | None]]:
    return {
        card["code"]: (card["x"], card["y"], card["held"], card["placed_by"])
        for card in answer["cards"]
    }


def _edges(answer: dict) -> dict[str, list[list[float]]]:
    return {edge["exchange_id"]: edge["points"] for edge in answer["edges"]}


@pytest.mark.parametrize("variant", [None, "heavy"])
async def test_drawing_full_the_page_and_the_python_api_agree(
    bundle_dir: Path, tmp_path: Path, variant: str | None
) -> None:
    systems = tmp_path / "agreeing"
    systems.mkdir()
    context = build_context(bundle_dir, systems)
    server = build_server(context)
    workspace = python_api.open(bundle_dir, systems)
    system = staged_nine()
    await context.storage.put_product_system(system, context.actor, "created")
    held_by_person = 907.0512249443207
    params = {} if variant is None else {"variant": variant}
    arguments = {"product_system_id": str(system.id), **params}
    base = f"/api/product-systems/{system.id}/layout"
    try:
        async with Client(server) as client:
            await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [{"code": "smelter", "x": 40.0, "y": 60.0}],
                },
            )
        await run_tool(
            server,
            context,
            "arrange_graph",
            {
                "product_system_id": str(system.id),
                "placements": [{"code": "transport", "x": held_by_person, "y": 120.0}],
            },
        )
        async with Client(server) as client:
            full = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            drawing = (
                await client.call_tool("graph_layout", {**arguments, "detail": "drawing"})
            ).structured_content["value"]
        api = workspace.product_system(system.id).graph_layout(variant=variant).value
        with TestClient(build_view(context, server, static=NOWHERE)) as page:
            read = page.get(base, params=params).json()["value"]
            posted = page.post(
                base,
                json={
                    "placements": [{"code": "mine", "x": 12.5, "y": 34.5}],
                    "variant": variant,
                },
            )
        assert posted.status_code == 200
        posted_value = posted.json()["value"]
        async with Client(server) as client:
            after_post = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
        with TestClient(build_view(context, server, static=NOWHERE)) as page:
            released = page.delete(base, params=params)
        assert released.status_code == 200
        async with Client(server) as client:
            after_release = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
        assert _cards(full)["transport"] == (held_by_person, 120.0, True, "person")
        assert _cards(full)["smelter"] == (40.0, 60.0, True, "agent")
        for answer in (drawing, read, api.model_dump(mode="json")):
            assert _cards(answer) == _cards(full)
            assert _edges(answer) == _edges(full)
            assert answer["score"] == full["score"]
            assert {**answer, "map": full["map"]} == full
        assert drawing["map"] is None and read["map"] is None
        assert _cards(posted_value) == _cards(after_post)
        assert _edges(posted_value) == _edges(after_post)
        assert posted_value["score"] == after_post["score"]
        assert {**posted_value, "map": after_post["map"]} == after_post
        assert _cards(after_post)["mine"] == (12.5, 34.5, True, "person")
        assert not any(card["held"] for card in after_release["cards"])
        released_value = released.json()["value"]
        assert {**released_value, "map": after_release["map"]} == after_release
    finally:
        workspace.close()
        await context.storage.delete_product_system(system.id, context.actor)
        context.close()


def _by_code(answer: dict) -> dict[str, dict]:
    return {card["code"]: card for card in answer["cards"]}


async def _staged_answers(
    bundle_dir: Path, tmp_path: Path, *arguments: dict[str, object]
) -> tuple[ProductSystem, list[dict]]:
    """`staged_nine` stored in a context of its own, and the drawing each set of arguments
    answers, in the order they are given."""
    systems = tmp_path / "expanding"
    systems.mkdir()
    context = build_context(bundle_dir, systems)
    system = staged_nine()
    await context.storage.put_product_system(system, context.actor, "created")
    stored = await context.storage.get_product_system(system.id)
    found: list[dict] = []
    try:
        async with Client(build_server(context)) as client:
            for given in arguments:
                out = await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(system.id), "detail": "full", **given},
                )
                found.append(out.structured_content["value"])
        assert (await context.storage.get_layout(system.id)).held == {}
        assert await context.storage.get_product_system(system.id) == stored
    finally:
        context.close()
    return system, found


async def test_the_drawing_expands_the_rows_the_page_names(
    bundle_dir: Path, tmp_path: Path
) -> None:
    _, [plain, expanded] = await _staged_answers(
        bundle_dir, tmp_path, {}, {"expanded": ["concentrator"]}
    )
    folded = _by_code(plain)["concentrator"]
    drawn = _by_code(expanded)["concentrator"]
    # the concentrator takes eight inputs and one elementary output
    assert folded["shown_inputs"] == 6 and folded["folded_inputs"] == 2
    assert drawn["shown_inputs"] == len(drawn["inputs"]) == 8
    assert drawn["folded_inputs"] == 2
    # two more input rows replace the one fold row
    assert drawn["height"] - folded["height"] == ROW_HEIGHT
    assert len({port["y"] for port in drawn["inputs"]}) == 8
    assert len({port["y"] for port in folded["inputs"]}) == 7
    assert _by_code(plain)["mine"]["height"] == _by_code(expanded)["mine"]["height"]
    assert "more inputs" in plain["map"] and "more inputs" not in expanded["map"]


async def test_an_expanded_drawing_routes_and_bounds_its_stages_over_the_rows_it_shows(
    bundle_dir: Path, tmp_path: Path
) -> None:
    _, [plain, expanded] = await _staged_answers(
        bundle_dir, tmp_path, {}, {"expanded": ["concentrator"]}
    )
    card = _by_code(expanded)["concentrator"]
    ends = {
        edge["exchange_id"]: edge["points"][-1]
        for edge in expanded["edges"]
        if edge["consumer"] == "concentrator"
    }
    assert ends
    for port in card["inputs"]:
        if str(port["exchange_id"]) in ends:
            assert ends[str(port["exchange_id"])] == [card["x"], card["y"] + port["y"]]
    stage = next(one for one in expanded["stages"] if "concentrator" in one["codes"])
    assert any(
        region["y"] <= card["y"] and card["y"] + card["height"] <= region["y"] + region["height"]
        for region in stage["regions"]
    )
    assert len(expanded["map"].splitlines()) > len(plain["map"].splitlines())


async def test_the_arrangement_refuses_to_expand_a_card_it_does_not_draw(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "expanded": ["nowhere"]},
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert payload["message"] == "this system draws no card 'nowhere': expand a code it draws"


async def test_nothing_is_expanded_under_amounts(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    code = fixture_system_stored.processes[0].code
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "graph_layout",
                {
                    "product_system_id": str(fixture_system_stored.id),
                    "detail": "amounts",
                    "expanded": [code],
                },
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert payload["message"] == 'expanded has no meaning under detail="amounts"'


async def test_a_write_answers_the_expansion_the_page_displays_and_saves_no_row(
    bundle_dir: Path, tmp_path: Path
) -> None:
    _, [read] = await _staged_answers(bundle_dir, tmp_path, {"expanded": ["concentrator"]})
    systems = tmp_path / "writing"
    systems.mkdir()
    context = build_context(bundle_dir, systems)
    system = staged_nine()
    await context.storage.put_product_system(system, context.actor, "created")
    try:
        async with Client(build_server(context)) as client:
            out = await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [],
                    "expanded": ["concentrator"],
                    "detail": "drawing",
                },
            )
        written = out.structured_content["value"]
        assert _cards(written) == _cards(read)
        assert (
            _by_code(written)["concentrator"]["height"] == _by_code(read)["concentrator"]["height"]
        )
        assert {edge["exchange_id"]: edge["points"] for edge in written["edges"]} == _edges(read)
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        context.close()


async def test_the_drawing_expands_the_same_rows_under_a_variant(
    bundle_dir: Path, tmp_path: Path
) -> None:
    _, [plain, varied] = await _staged_answers(
        bundle_dir,
        tmp_path,
        {"expanded": ["concentrator"]},
        {"expanded": ["concentrator"], "variant": "heavy"},
    )
    folded = _by_code(plain)["concentrator"]
    drawn = _by_code(varied)["concentrator"]
    assert folded["shown_inputs"] == drawn["shown_inputs"] == 8
    assert folded["height"] == drawn["height"]
    assert (
        _by_code(varied)["concentrator"]["shown_outputs"]
        == _by_code(plain)["concentrator"]["shown_outputs"]
    )


async def test_a_linked_card_keeps_its_one_row_however_the_page_expands_it(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    code = f"system:{frame.id}"
    async with Client(full_server) as client:
        answer = (
            await client.call_tool(
                "graph_layout",
                {
                    "product_system_id": str(widget.id),
                    "detail": "drawing",
                    "expanded": [code, "widget"],
                },
            )
        ).structured_content["value"]
    card = _by_code(answer)[code]
    assert card["shown_inputs"] == 0 and card["shown_outputs"] == 0
    assert card["height"] == LINKED_HEIGHT
    assert card["inputs"] == [] and card["outputs"] == []
