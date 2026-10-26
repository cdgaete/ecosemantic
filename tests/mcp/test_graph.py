from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.graph import Arrangement
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
from ecosemantic.model.refs import ForegroundRef
from ecosemantic.ports.types import Layout
from ecosemantic.troubles import score, troubles
from tests.conftest import frame_system, widget_linking


async def test_the_map_names_every_card_and_says_what_is_wrong(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "graph_layout", {"product_system_id": str(fixture_system_stored.id)}
        )
    answer = out.structured_content["value"]
    assert all(p.code in answer["map"] for p in fixture_system_stored.processes)
    assert {row["code"] for row in answer["cards"]} == {
        p.code for p in fixture_system_stored.processes
    }
    assert set(answer) == {"map", "cards", "edges", "troubles", "score", "bounds", "scaling"}
    assert all(t["kind"] != "cards_overlap" for t in answer["troubles"])
    assert all(len(e["points"]) >= 2 for e in answer["edges"])
    assert answer["bounds"]["width"] > 0


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
                "graph_layout", {"product_system_id": str(fixture_system_stored.id)}
            )
        cards = {row["code"]: row for row in out.structured_content["value"]["cards"]}
        assert (cards[code]["x"], cards[code]["y"], cards[code]["held"]) == (5.0, 6.0, True)
    finally:
        # fixture_system_stored is session-scoped, so what this holds is released again
        await context.storage.put_layout(fixture_system_stored.id, Layout())


async def test_a_released_card_returns_to_the_automatic_layout(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    await context.storage.put_layout(system.id, Layout())
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
        await context.storage.put_layout(system.id, Layout())


async def test_a_card_placed_and_released_at_once_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    code = system.processes[0].code
    await context.storage.put_layout(system.id, Layout())
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
        await context.storage.put_layout(system.id, Layout())


async def test_releasing_a_card_that_is_not_held_changes_nothing(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    await context.storage.put_layout(system.id, Layout())
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
                            "release": [system.processes[0].code],
                        },
                    )
                ).structured_content["value"]
            )
        assert answer.cards == before.cards
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout())


async def test_a_release_takes_a_code_that_names_no_card_as_a_placement_does(
    full_server: FastMCP, fixture_system_stored: ProductSystem, context: ServerContext
) -> None:
    system = fixture_system_stored
    await context.storage.put_layout(system.id, Layout())
    try:
        async with Client(full_server) as client:
            automatic = await _layout(client, system)
            placed = Arrangement.model_validate(
                (
                    await client.call_tool(
                        "arrange_graph",
                        {
                            "product_system_id": str(system.id),
                            "placements": [{"code": "ghost", "x": 1.0, "y": 2.0}],
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
                            "release": ["ghost"],
                        },
                    )
                ).structured_content["value"]
            )
        assert placed.cards == automatic.cards
        assert released.cards == automatic.cards
        assert (await context.storage.get_layout(system.id)).held == {}
    finally:
        await context.storage.put_layout(system.id, Layout())


async def test_the_layout_draws_a_linked_system_and_answers_every_edge(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    async with Client(full_server) as client:
        answer = (
            await client.call_tool("graph_layout", {"product_system_id": str(widget.id)})
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
                "graph_layout", {"product_system_id": str(fixture_system_stored.id)}
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
            await client.call_tool("graph_layout", {"product_system_id": str(widget.id)})
        ).structured_content["value"]
    card = next(c for c in answer["cards"] if c["code"] == f"system:{frame.id}")
    production = next(e for e in frame.processes[0].exchanges if e.type == "production")
    assert card["activity"] == pytest.approx(0.25)
    assert card["scaled"] == {str(production.id): pytest.approx(0.25)}


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
            await client.call_tool("graph_layout", {"product_system_id": str(unsolvable.id)})
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
            await client.call_tool("graph_layout", {"product_system_id": str(widget.id)})
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
            await client.call_tool("graph_layout", {"product_system_id": str(system.id)})
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
            await client.call_tool("graph_layout", {"product_system_id": str(system.id)})
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
                "graph_layout", {"product_system_id": str(fixture_system_stored.id)}
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
    arguments: dict[str, str] = {"product_system_id": str(system.id)}
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
