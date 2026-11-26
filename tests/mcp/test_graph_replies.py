from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.exceptions import ToolError
from mcp.types import Implementation, TextContent

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import Answer
from ecosemantic.mcp.graph import Arrangement, LayoutRead
from ecosemantic.mcp.graph_replies import _heaviest, compact_read
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem, method_id
from ecosemantic.ports.types import Layout, Spot, page_start
from ecosemantic.troubles import WEIGHTS
from tests.conftest import uid
from tests.fixture_data import GWP
from tests.layout_fixtures import (
    LONG_VIEW_URL,
    REPLY_BYTES,
    hundred,
    rendered_bytes,
    rendered_size,
    staged_nine,
)
from tests.mcp.test_graph import CountedWrites

GWP_ID = method_id(" > ".join(GWP))


def _refuse(*_: object, **__: object) -> None:
    raise AssertionError("the amounts path ran the drawing code")


def _no_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drawing code replaced by functions that fail the test that calls them."""
    for name in ("arrange", "route", "troubles", "as_text"):
        monkeypatch.setattr(f"ecosemantic.mcp.graph.{name}", _refuse)


async def _store(context: ServerContext, system: ProductSystem) -> ProductSystem:
    await context.storage.put_product_system(system, context.actor, "created")
    return system


async def _every_page(client: Client, arguments: dict[str, str]) -> list[CallToolResult]:
    """Every page of one amounts read, following the cursors it answers."""
    found: list[CallToolResult] = []
    cursor: str | None = None
    while True:
        given = arguments if cursor is None else {**arguments, "cursor": cursor}
        out = await client.call_tool("graph_layout", given)
        found.append(out)
        cursor = out.structured_content["value"]["next_cursor"]
        if cursor is None:
            return found


def _values(pages: list[CallToolResult]) -> list[dict]:
    return [out.structured_content["value"] for out in pages]


async def _first_pages(
    client: Client, arguments: dict[str, str], count: int
) -> list[CallToolResult]:
    """That many pages of one read, from the first, following the cursors it answers."""
    found: list[CallToolResult] = []
    cursor: str | None = None
    while len(found) < count:
        given = arguments if cursor is None else {**arguments, "cursor": cursor}
        out = await client.call_tool("graph_layout", given)
        found.append(out)
        cursor = out.structured_content["value"]["next_cursor"]
        if cursor is None:
            return found
    return found


def _text(out: CallToolResult) -> str:
    return "".join(block.text for block in out.content if isinstance(block, TextContent))


def _row(card: dict) -> dict:
    """The fields a compact reply gives one card, from the card an arrangement carries."""
    return {key: card[key] for key in ("code", "x", "y", "width", "height", "held", "placed_by")}


def _issue(trouble: dict) -> dict:
    """The fields a compact reply gives one issue, from the trouble an arrangement carries."""
    return {key: trouble[key] for key in ("kind", "codes", "exchange_ids")}


def _counted(kinds: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for kind in kinds:
        counts[kind] = counts.get(kind, 0) + 1
    return counts


async def _delete(context: ServerContext, *systems: ProductSystem) -> None:
    for system in systems:
        await context.storage.delete_product_system(system.id, context.actor)


@pytest.mark.parametrize("variant", [None, "heavy"])
async def test_amounts_equal_what_full_carries_for_the_base_and_a_variant(
    full_server: FastMCP, context: ServerContext, variant: str | None
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    if variant is not None:
        arguments["variant"] = variant
    try:
        async with Client(full_server) as client:
            full = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            activity_pages = _values(await _every_page(client, {**arguments, "detail": "amounts"}))
            row_pages = {
                card["code"]: _values(
                    await _every_page(
                        client, {**arguments, "detail": "amounts", "card": card["code"]}
                    )
                )
                for card in full["cards"]
            }
    finally:
        await _delete(context, system)
    activities = [item for page in activity_pages for item in page["activities"]["items"]]
    assert {item["code"]: item["activity"] for item in activities} == {
        card["code"]: card["activity"] for card in full["cards"]
    }
    assert [page["activities"]["total"] for page in activity_pages] == [len(full["cards"])]
    exchanges = {str(e.id): e for p in system.processes for e in p.exchanges}
    for card in full["cards"]:
        rows = [row for page in row_pages[card["code"]] for row in page["card"]["rows"]["items"]]
        assert {row["exchange_id"]: row["amount"] for row in rows} == card["scaled"]
        assert [page["card"]["rows"]["total"] for page in row_pages[card["code"]]] == [
            len(card["scaled"])
        ]
        for row in rows:
            assert (row["name"], row["unit"]) == (
                exchanges[row["exchange_id"]].name,
                exchanges[row["exchange_id"]].unit,
            )


async def test_amounts_run_no_drawing_code(
    full_server: FastMCP, context: ServerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_drawing(monkeypatch)
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id), "detail": "amounts"}
    try:
        async with Client(full_server) as client:
            activities = (await client.call_tool("graph_layout", arguments)).structured_content[
                "value"
            ]
            card = (
                await client.call_tool("graph_layout", {**arguments, "card": "refinery"})
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    assert activities["activities"]["items"]
    assert card["card"]["rows"]["items"]


async def test_what_drives_this_impact_reads_no_drawing(
    context: ServerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_drawing(monkeypatch)
    systems = [await _store(context, staged_nine()), await _store(context, hundred())]
    counted = CountedWrites(context.storage)
    try:
        async with Client(build_server(dataclasses.replace(context, storage=counted))) as client:
            for system in systems:
                arguments = {"product_system_id": str(system.id)}
                contribution = await client.call_tool(
                    "contribution_analysis",
                    {**arguments, "method_id": GWP_ID, "by": "process"},
                )
                assert rendered_bytes(contribution) <= REPLY_BYTES
                top = next(
                    entry["ref"]["code"]
                    for entry in contribution.structured_content["value"]["processes"]
                    if entry["ref"]["kind"] == "foreground"
                )
                activities = await client.call_tool(
                    "graph_layout", {**arguments, "detail": "amounts"}
                )
                assert rendered_bytes(activities) <= REPLY_BYTES
                card = await client.call_tool(
                    "graph_layout", {**arguments, "detail": "amounts", "card": top}
                )
                assert rendered_bytes(card) <= REPLY_BYTES
                assert card.structured_content["value"]["card"]["rows"]["items"]
        assert counted.layouts == []
    finally:
        await _delete(context, *systems)


async def test_amounts_of_an_unsolvable_system_answer_the_reason_and_no_amount(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = staged_nine()
    system.reference_process = None
    await _store(context, system)
    arguments = {"product_system_id": str(system.id), "detail": "amounts"}
    try:
        async with Client(full_server) as client:
            value = (await client.call_tool("graph_layout", arguments)).structured_content["value"]
            with pytest.raises(ToolError) as caught:
                await client.call_tool("graph_layout", {**arguments, "card": "nope"})
    finally:
        await _delete(context, system)
    assert "names no reference process" in value["scaling"]
    assert (value["activities"], value["card"], value["next_cursor"]) == (None, None, None)
    assert json.loads(str(caught.value))["error"] == "not_found"


async def test_a_linked_card_s_amounts_name_its_system_s_production(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    card = f"system:{frame.id}"
    arguments = {"product_system_id": str(widget.id)}
    async with Client(full_server) as client:
        full = (
            await client.call_tool("graph_layout", {**arguments, "detail": "full"})
        ).structured_content["value"]
        amounts = (
            await client.call_tool("graph_layout", {**arguments, "detail": "amounts", "card": card})
        ).structured_content["value"]
    production = next(e for e in frame.processes[0].exchanges if e.type == "production")
    rows = amounts["card"]["rows"]["items"]
    assert [(row["exchange_id"], row["name"], row["unit"]) for row in rows] == [
        (str(production.id), production.name, production.unit)
    ]
    scaled = next(entry for entry in full["cards"] if entry["code"] == card)["scaled"]
    assert rows[0]["amount"] == pytest.approx(scaled[str(production.id)])


async def test_amounts_stay_within_8_kib_and_cursors_return_every_item_once(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, hundred())
    variant = system.cases[0].name
    arguments = {"product_system_id": str(system.id), "variant": variant, "detail": "amounts"}
    reference = system.reference_process
    try:
        async with Client(full_server) as client:
            activity_pages = await _every_page(client, arguments)
            row_pages = await _every_page(client, {**arguments, "card": reference})
            beyond = (
                await client.call_tool("graph_layout", {**arguments, "cursor": "4"})
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    assert all(rendered_bytes(out) <= REPLY_BYTES for out in activity_pages + row_pages)
    activities = _values(activity_pages)
    listed = [item for page in activities for item in page["activities"]["items"]]
    assert len(listed) == len({item["code"] for item in listed}) == len(system.processes)
    assert [page["activities"]["total"] for page in activities] == [100] * len(activities)
    assert [len(page["activities"]["items"]) for page in activities] == [30, 30, 30, 10]
    assert [page["activities"]["omitted"] for page in activities] == [70, 40, 10, 0]
    assert [page["next_cursor"] for page in activities] == ["1", "2", "3", None]
    rows = [row for page in _values(row_pages) for row in page["card"]["rows"]["items"]]
    exchanges = system.process(reference).exchanges
    assert [row["exchange_id"] for row in rows] == [str(e.id) for e in exchanges]
    pages = _values(row_pages)
    assert [page["card"]["rows"]["total"] for page in pages] == [len(exchanges)] * len(pages)
    assert [len(page["card"]["rows"]["items"]) for page in pages] == [15, len(exchanges) - 15]
    assert [page["card"]["rows"]["omitted"] for page in pages] == [
        len(exchanges) - 15,
        0,
    ]
    assert [page["next_cursor"] for page in pages] == ["1", None]
    assert beyond["activities"] == {"items": [], "total": 100, "omitted": 0}
    assert beyond["next_cursor"] is None


async def test_a_compact_read_states_what_the_drawing_holds(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    await context.storage.put_layout(
        system.id,
        Layout(
            held={
                "smelter": Spot(x=40.0, y=60.0, placed_by="person"),
                "gone": Spot(x=1.0, y=2.0),
            }
        ),
        expected=None,
    )
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            full = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            pages = await _every_page(client, arguments)
    finally:
        await _delete(context, system)
    compact = _values(pages)[0]
    assert (compact["kind"], compact["variant"]) == ("compact", None)
    assert (compact["score"], compact["scaling"], compact["bounds"]) == (
        full["score"],
        full["scaling"],
        full["bounds"],
    )
    assert compact["troubles"] == _counted([trouble["kind"] for trouble in full["troubles"]])
    assert compact["holds"] == {"person": 1, "agent": 0, "service": 0, "unrecorded": 0}
    assert compact["cards"]["items"] == [_row(card) for card in full["cards"][:10]]
    assert compact["cards"]["total"] == len(full["cards"])
    heaviest = sorted(full["troubles"], key=lambda trouble: -WEIGHTS[trouble["kind"]])
    listed = [issue for page in _values(pages) for issue in page["issues"]["items"]]
    assert listed == [_issue(trouble) for trouble in heaviest]
    assert [page["issues"]["total"] for page in _values(pages)] == [len(heaviest)] * len(pages)
    assert compact["next_cursor"] == ("1" if compact["issues"]["omitted"] else None)
    assert [page["next_cursor"] for page in _values(pages)][-1] is None


def _walk(arrangement: Arrangement, variant: str | None) -> list[dict]:
    """Every page of one compact read of `arrangement`, as the tool sends it, following the
    cursors until none continues."""
    found: list[dict] = []
    cursor: str | None = None
    while True:
        read = compact_read(arrangement, variant, page_start(cursor, 1))
        found.append(Answer[LayoutRead](value=read).model_dump(mode="json"))
        cursor = read.next_cursor
        if cursor is None:
            return found


async def test_compact_replies_stay_within_8_kib_and_cursors_return_every_item_once(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, hundred())
    small = await _store(context, staged_nine())
    variant = system.cases[0].name
    await context.storage.put_layout(
        system.id,
        Layout(
            held={
                process.code: Spot(x=907.0512249443207, y=100.0 + index, placed_by="person")
                for index, process in enumerate(system.processes[:10])
            }
        ),
        expected=None,
    )
    served = dataclasses.replace(context, view_url=LONG_VIEW_URL)
    arguments = {"product_system_id": str(system.id), "variant": variant}
    reference = system.reference_process
    try:
        async with Client(build_server(served)) as client:
            walked = await _first_pages(client, arguments, 11)
            focused = await _every_page(client, {**arguments, "card": reference})
            drawing = (
                await client.call_tool("graph_layout", {**arguments, "detail": "drawing"})
            ).structured_content["value"]
            ground = (
                await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(small.id), "detail": "full"},
                )
            ).structured_content["value"]
            paged = await _every_page(client, {"product_system_id": str(small.id)})
    finally:
        await _delete(context, system, small)
    arrangement = Arrangement.model_validate(drawing)
    pages = _walk(arrangement, variant)
    reads = [page["value"] for page in pages]
    for index, out in enumerate(walked):
        assert out.structured_content == pages[index], index
        assert rendered_size(out.structured_content) == rendered_bytes(out), index
    assert all(rendered_size(page) <= REPLY_BYTES for page in pages)
    codes = [row["code"] for read in reads for row in read["cards"]["items"]]
    assert len(codes) == len(set(codes)) == len(system.processes)
    assert [read["cards"]["total"] for read in reads] == [len(system.processes)] * len(reads)
    assert [read["cards"]["omitted"] for read in reads] == [
        max(0, len(system.processes) - 10 * (index + 1)) for index in range(len(reads))
    ]
    issues = [issue for read in reads for issue in read["issues"]["items"]]
    heaviest = _heaviest(arrangement.troubles)
    assert issues == [issue.model_dump(mode="json") for issue in heaviest]
    assert [read["issues"]["total"] for read in reads] == [len(heaviest)] * len(reads)
    assert [read["issues"]["omitted"] for read in reads] == [
        max(0, len(heaviest) - 3 * (index + 1)) for index in range(len(reads))
    ]
    assert [read["next_cursor"] for read in reads][-1] is None
    assert [read["next_cursor"] for read in reads][:-1] == [
        str(index + 1) for index in range(len(reads) - 1)
    ]
    for page in pages:
        assert '"map"' not in json.dumps(page) and '"points"' not in json.dumps(page)
        assert page["view_url"] is None
    incidents = [
        edge for edge in drawing["edges"] if reference in (edge["provider"], edge["consumer"])
    ]
    routes = [route for page in _values(focused) for route in page["routes"]["items"]]
    assert len(routes) == len(incidents) > 5
    assert [route["exchange_id"] for route in routes] == [edge["exchange_id"] for edge in incidents]
    naming = [issue.model_dump(mode="json") for issue in heaviest if reference in issue.codes]
    assert [issue for page in _values(focused) for issue in page["issues"]["items"]] == naming
    assert [page["issues"]["total"] for page in _values(focused)] == [len(naming)] * len(focused)
    assert [page["next_cursor"] for page in _values(focused)][-1] is None
    complete = [issue for page in _values(paged) for issue in page["issues"]["items"]]
    assert complete == [
        _issue(trouble)
        for trouble in sorted(ground["troubles"], key=lambda trouble: -WEIGHTS[trouble["kind"]])
    ]
    assert [page["next_cursor"] for page in _values(paged)][-1] is None
    assert all(rendered_bytes(out) <= REPLY_BYTES for out in walked + focused + paged)
    for out in walked + focused + paged:
        text = _text(out)
        assert '"map"' not in text and '"points"' not in text and "token=" not in text
        assert out.structured_content["view_url"] is None


async def test_a_focus_tells_parallel_exchanges_apart_and_misses_no_route(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    parallel = [uid("layout-ex", "refinery", n) for n in ("2", "3")]
    try:
        async with Client(full_server) as client:
            full = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            focused = {
                exchange: (
                    await client.call_tool(
                        "graph_layout", {**arguments, "exchange_id": str(exchange)}
                    )
                ).structured_content["value"]
                for exchange in parallel
            }
            card = (
                await client.call_tool("graph_layout", {**arguments, "card": "refinery"})
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    edges = {edge["exchange_id"]: edge for edge in full["edges"]}
    for exchange, answer in focused.items():
        edge = edges[str(exchange)]
        assert [route["exchange_id"] for route in answer["routes"]["items"]] == [str(exchange)]
        assert answer["routes"]["total"] == 1
        assert [row["code"] for row in answer["cards"]] == [edge["provider"], edge["consumer"]]
        route = answer["routes"]["items"][0]
        assert (route["provider"], route["consumer"]) == (edge["provider"], edge["consumer"])
        assert (route["first"], route["last"]) == (edge["points"][0], edge["points"][-1])
        assert route["label"] == edge["label"]["scaled"]
        assert all(str(exchange) in issue["exchange_ids"] for issue in answer["issues"]["items"])
    incident = [
        edge for edge in full["edges"] if "refinery" in (edge["provider"], edge["consumer"])
    ]
    assert card["routes"]["total"] == len(incident)
    assert [route["exchange_id"] for route in card["routes"]["items"]] == [
        edge["exchange_id"] for edge in incident
    ]
    assert all("refinery" in issue["codes"] for issue in card["issues"]["items"])


async def test_a_focus_on_a_card_or_exchange_the_drawing_lacks_is_not_found(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    background = uid("layout-ex", "concentrator", "2")
    try:
        async with Client(full_server) as client:
            for given in ({"card": "nope"}, {"exchange_id": str(background)}):
                with pytest.raises(ToolError) as caught:
                    await client.call_tool("graph_layout", {**arguments, **given})
                assert json.loads(str(caught.value))["error"] == "not_found"
    finally:
        await _delete(context, system)


@pytest.mark.parametrize(
    "detail, given, named",
    [
        ("drawing", {"card": "mine"}, ["card"]),
        ("drawing", {"cursor": "0"}, ["cursor"]),
        ("full", {"card": "mine"}, ["card"]),
        ("full", {"cursor": "0"}, ["cursor"]),
        ("amounts", {"exchange_id": "8d1f7c2e-0000-4000-8000-000000000000"}, ["exchange_id"]),
        ("drawing", {"exchange_id": "8d1f7c2e-0000-4000-8000-000000000000"}, ["exchange_id"]),
        ("full", {"exchange_id": "8d1f7c2e-0000-4000-8000-000000000000"}, ["exchange_id"]),
        (
            "compact",
            {
                "card": "mine",
                "exchange_id": "8d1f7c2e-0000-4000-8000-000000000000",
            },
            ["card", "exchange_id"],
        ),
    ],
)
async def test_an_argument_without_meaning_under_its_detail_is_refused(
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
    detail: str,
    given: dict[str, str],
    named: list[str],
) -> None:
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "graph_layout",
                {"product_system_id": str(fixture_system_stored.id), "detail": detail, **given},
            )
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid", payload
    assert f'detail="{detail}"' in payload["message"]
    assert all(name in payload["message"] for name in named)


async def test_positions_a_compact_read_gives_are_the_stored_ones(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    before = Layout(
        held={
            process.code: Spot(
                x=907.0512249443207 + index,
                y=120.0 + index,
                placed_by="person" if index % 2 == 0 else "agent",
            )
            for index, process in enumerate(system.processes)
        }
    )
    await context.storage.put_layout(system.id, before, expected=None)
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            pages = await _every_page(client, arguments)
            rows = [row for page in _values(pages) for row in page["cards"]["items"]]
            await client.call_tool(
                "arrange_graph",
                {
                    **arguments,
                    "placements": [
                        {"code": row["code"], "x": row["x"], "y": row["y"]} for row in rows
                    ],
                },
            )
            after = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
        stored = await context.storage.get_layout(system.id)
    finally:
        await _delete(context, system)
    assert len(rows) == len(system.processes)
    assert stored == before
    assert {row["code"]: (row["x"], row["y"]) for row in rows} == {
        code: (spot.x, spot.y) for code, spot in before.held.items()
    }
    assert {card["code"]: (card["x"], card["y"], card["placed_by"]) for card in after["cards"]} == {
        code: (spot.x, spot.y, spot.placed_by) for code, spot in before.held.items()
    }


async def test_a_compact_read_of_an_unsolvable_system_answers_its_reason(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = staged_nine()
    system.reference_process = None
    await _store(context, system)
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            compact = (await client.call_tool("graph_layout", arguments)).structured_content[
                "value"
            ]
            focused = (
                await client.call_tool("graph_layout", {**arguments, "card": "mine"})
            ).structured_content["value"]
            full = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    assert "names no reference process" in compact["scaling"]
    assert (compact["score"], compact["bounds"]) == (full["score"], full["bounds"])
    assert compact["cards"]["items"]
    assert all(edge["label"]["scaled"] is None for edge in full["edges"])
    edges = {edge["exchange_id"]: edge for edge in full["edges"]}
    assert focused["cards"]
    assert focused["routes"]["items"]
    for route in focused["routes"]["items"]:
        assert route["label"] == edges[route["exchange_id"]]["label"]["per_unit"]


async def test_a_cursor_past_the_last_page_answers_empty_lists(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            first = (await client.call_tool("graph_layout", arguments)).structured_content["value"]
            first_focus = (
                await client.call_tool("graph_layout", {**arguments, "card": "mine"})
            ).structured_content["value"]
            beyond = (
                await client.call_tool("graph_layout", {**arguments, "cursor": "99"})
            ).structured_content["value"]
            focused = (
                await client.call_tool(
                    "graph_layout", {**arguments, "card": "mine", "cursor": "99"}
                )
            ).structured_content["value"]
            refused = {}
            for cursor in ("x", "-1"):
                with pytest.raises(ToolError) as caught:
                    await client.call_tool("graph_layout", {**arguments, "cursor": cursor})
                refused[cursor] = json.loads(str(caught.value))["error"]
    finally:
        await _delete(context, system)
    assert beyond["cards"] == {"items": [], "total": len(system.processes), "omitted": 0}
    assert beyond["issues"] == {
        "items": [],
        "total": first["issues"]["total"],
        "omitted": 0,
    }
    assert beyond["next_cursor"] is None
    assert focused["routes"] == {
        "items": [],
        "total": first_focus["routes"]["total"],
        "omitted": 0,
    }
    assert focused["issues"] == {
        "items": [],
        "total": first_focus["issues"]["total"],
        "omitted": 0,
    }
    assert focused["next_cursor"] is None
    assert refused == {"x": "invalid", "-1": "invalid"}


async def test_a_linked_card_is_a_row_and_a_focus(
    full_server: FastMCP, linked_stored: tuple[ProductSystem, ProductSystem]
) -> None:
    widget, frame = linked_stored
    card = f"system:{frame.id}"
    arguments = {"product_system_id": str(widget.id)}
    async with Client(full_server) as client:
        compact = (await client.call_tool("graph_layout", arguments)).structured_content["value"]
        focused = (
            await client.call_tool("graph_layout", {**arguments, "card": card})
        ).structured_content["value"]
    assert card in [row["code"] for row in compact["cards"]["items"]]
    assert focused["cards"] == [row for row in compact["cards"]["items"] if row["code"] == card]
    assert [route["provider"] for route in focused["routes"]["items"]] == [card]
    assert [route["consumer"] for route in focused["routes"]["items"]] == [
        process.code for process in widget.processes
    ]


async def test_every_detail_records_the_held_cards(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    await context.storage.put_layout(
        system.id,
        Layout(held={"smelter": Spot(x=40.0, y=60.0, placed_by="person")}),
        expected=None,
    )
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(
            full_server, client_info=Implementation(name="drawer", version="1")
        ) as client:
            for given in (
                {},
                {"card": "smelter"},
                {"card": "mine"},
                {"detail": "amounts"},
                {"detail": "drawing"},
                {"detail": "full"},
            ):
                await client.call_tool("graph_layout", {**arguments, **given})
        calls = await context.activity.list_calls(agent="drawer")
    finally:
        await _delete(context, system)
    assert len(calls) == 6
    summaries = [call.summary.model_dump(mode="json") for call in calls if call.summary]
    assert len(summaries) == 6
    assert len({json.dumps(summary, sort_keys=True) for summary in summaries}) == 1
    assert summaries[0]["count"] == 1
    assert summaries[0]["noun"] == "cards placed"
    assert [item["label"] for item in summaries[0]["items"]] == ["smelter"]


async def test_an_amounts_argument_without_meaning_is_refused(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored
    async with Client(full_server) as client:
        for detail, argument in (
            ("drawing", "card"),
            ("drawing", "cursor"),
            ("full", "card"),
            ("full", "cursor"),
        ):
            given = "widget" if argument == "card" else "0"
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(system.id), "detail": detail, argument: given},
                )
            payload = json.loads(str(caught.value))
            assert payload["error"] == "invalid"
            assert argument in payload["message"]
            assert f'detail="{detail}"' in payload["message"]
        for given, error in (({"card": "nope"}, "not_found"), ({"cursor": "x"}, "invalid")):
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "graph_layout",
                    {"product_system_id": str(system.id), "detail": "amounts", **given},
                )
            assert json.loads(str(caught.value))["error"] == error


def _state(card: dict) -> dict:
    """Where a compact write puts one card, from the card an arrangement carries."""
    return {key: card[key] for key in ("x", "y", "held", "placed_by")}


def _beyond(mine: list[dict], theirs: list[dict]) -> list[dict]:
    """The issues `mine` carries beyond `theirs`, counted with multiplicity, the heaviest first."""
    left = [(t["kind"], tuple(t["codes"]), tuple(t["exchange_ids"])) for t in theirs]
    found = []
    for trouble in mine:
        key = (trouble["kind"], tuple(trouble["codes"]), tuple(trouble["exchange_ids"]))
        if key in left:
            left.remove(key)
        else:
            found.append(_issue(trouble))
    return sorted(found, key=lambda issue: -WEIGHTS[issue["kind"]])


async def test_a_compact_write_states_what_changed(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            before = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            spots = {card["code"]: (card["x"], card["y"]) for card in before["cards"]}
            x, y = spots["refinery"]
            written = (
                await client.call_tool(
                    "arrange_graph",
                    {**arguments, "placements": [{"code": "mine", "x": x + 1.0, "y": y + 1.0}]},
                )
            ).structured_content["value"]
            after = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    states = {card["code"]: _state(card) for card in before["cards"]}
    later = {card["code"]: _state(card) for card in after["cards"]}
    moved = [
        card["code"]
        for card in after["cards"]
        if card["code"] != "mine" and states[card["code"]] != later[card["code"]]
    ]
    assert moved, "the arrangement displaced no card; place a card over a neighbour's place"
    assert written["kind"] == "write"
    assert written["changed"]["items"] == [
        {"code": code, "before": states[code], "after": later[code]} for code in ["mine", *moved]
    ]
    assert (written["changed"]["total"], written["changed"]["omitted"]) == (len(moved) + 1, 0)
    assert (written["score_before"], written["score_after"]) == (before["score"], after["score"])
    assert written["troubles"] == _counted([trouble["kind"] for trouble in after["troubles"]])
    added = _beyond(after["troubles"], before["troubles"])
    resolved = _beyond(before["troubles"], after["troubles"])
    assert written["added"] == {
        "items": added[:2],
        "total": len(added),
        "omitted": max(0, len(added) - 2),
    }
    assert written["resolved"] == {
        "items": resolved[:2],
        "total": len(resolved),
        "omitted": max(0, len(resolved) - 2),
    }


async def test_ten_consecutive_moves_deliver_no_drawing(context: ServerContext) -> None:
    system = await _store(context, hundred())
    served = dataclasses.replace(context, view_url=LONG_VIEW_URL)
    code = system.processes[0].code
    try:
        async with Client(build_server(served)) as client:
            answers = [
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [{"code": code, "x": 100.0 * (turn + 1), "y": 50.0}],
                    },
                )
                for turn in range(10)
            ]
    finally:
        await _delete(context, system)
    assert [out.structured_content["value"]["saved"] for out in answers] == [True] * 10
    for out in answers:
        assert rendered_bytes(out) <= REPLY_BYTES
        text = _text(out)
        body = json.dumps(out.structured_content)
        for key in ('"map"', '"points"', '"edges"', '"cards"'):
            assert key not in text and key not in body, key


async def test_release_all_answers_null_for_what_came_before(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    await context.storage.put_layout(
        system.id,
        Layout(held={"mine": Spot(x=1000.0, y=40.0, placed_by="person")}),
        expected=None,
    )
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            written = (
                await client.call_tool(
                    "arrange_graph", {**arguments, "placements": [], "release_all": True}
                )
            ).structured_content["value"]
    finally:
        await _delete(context, system)
    assert written["saved"] is True
    assert written["score_before"] is None
    assert (written["changed"], written["added"], written["resolved"]) == (None, None, None)
    assert isinstance(written["score_after"], int)


async def test_a_placement_that_worsens_the_score_is_saved(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            before = (
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            ).structured_content["value"]
            written = (
                await client.call_tool(
                    "arrange_graph",
                    {
                        **arguments,
                        "placements": [
                            {"code": "mine", "x": 100.0, "y": 100.0},
                            {"code": "refinery", "x": 100.0, "y": 100.0},
                        ],
                    },
                )
            ).structured_content["value"]
        held = (await context.storage.get_layout(system.id)).held
    finally:
        await _delete(context, system)
    assert written["saved"] is True
    assert written["score_after"] > written["score_before"] == before["score"]
    assert {code: (spot.x, spot.y) for code, spot in held.items()} == {
        "mine": (100.0, 100.0),
        "refinery": (100.0, 100.0),
    }


async def test_a_compact_write_that_changes_nothing_saved_nothing(
    full_server: FastMCP, context: ServerContext
) -> None:
    system = await _store(context, staged_nine())
    await context.storage.put_layout(
        system.id, Layout(held={"smelter": Spot(x=40.0, y=60.0, placed_by="person")}), expected=None
    )
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(full_server) as client:
            written = (
                await client.call_tool(
                    "arrange_graph",
                    {**arguments, "placements": [{"code": "smelter", "x": 40.0, "y": 60.0}]},
                )
            ).structured_content["value"]
        stored = await context.storage.get_layout(system.id)
    finally:
        await _delete(context, system)
    assert written["saved"] is False
    assert written["changed"] == {"items": [], "total": 0, "omitted": 0}
    assert written["score_before"] == written["score_after"]
    assert stored.held["smelter"].placed_by == "person"


async def test_a_compact_write_far_out_saves_and_a_full_read_names_drawing(
    full_server: FastMCP, context: ServerContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    system = await _store(context, staged_nine())
    code = system.processes[0].code
    arguments = {"product_system_id": str(system.id)}
    far = {"code": code, "x": 90000.0, "y": 90000.0}
    monkeypatch.setattr("ecosemantic.textmap.MAX_MAP_CELLS", 5000)
    try:
        async with Client(full_server) as client:
            written = (
                await client.call_tool("arrange_graph", {**arguments, "placements": [far]})
            ).structured_content["value"]
            with pytest.raises(ToolError) as caught:
                await client.call_tool("graph_layout", {**arguments, "detail": "full"})
            drawn = (
                await client.call_tool("graph_layout", {**arguments, "detail": "drawing"})
            ).structured_content["value"]
        held = (await context.storage.get_layout(system.id)).held
    finally:
        await _delete(context, system)
    assert written["saved"] is True
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert 'detail="drawing"' in payload["message"]
    assert drawn["map"] is None and len(drawn["cards"]) == len(system.processes)
    assert (held[code].x, held[code].y) == (90000.0, 90000.0)


async def test_a_compact_write_carries_the_system_s_page_link(context: ServerContext) -> None:
    system = await _store(context, staged_nine())
    served = dataclasses.replace(context, view_url=LONG_VIEW_URL)
    try:
        async with Client(build_server(served)) as client:
            out = await client.call_tool(
                "arrange_graph", {"product_system_id": str(system.id), "placements": []}
            )
    finally:
        await _delete(context, system)
    assert out.structured_content["view_url"] == served.deep_link(system.id)
    assert str(system.id) in out.structured_content["view_url"]


async def test_a_write_s_lists_state_their_totals_within_8_kib(
    context: ServerContext,
) -> None:
    system = await _store(context, hundred())
    served = dataclasses.replace(context, view_url=LONG_VIEW_URL)
    code = system.processes[0].code
    arguments = {"product_system_id": str(system.id)}
    try:
        async with Client(build_server(served)) as client:
            drawing = (
                await client.call_tool("graph_layout", {**arguments, "detail": "drawing"})
            ).structured_content["value"]
            spot = next(card for card in drawing["cards"] if card["code"] == code)
            out = await client.call_tool(
                "arrange_graph",
                {
                    **arguments,
                    "placements": [{"code": code, "x": spot["x"] + 900.0, "y": spot["y"] + 10.0}],
                },
            )
    finally:
        await _delete(context, system)
    changed = out.structured_content["value"]["changed"]
    assert rendered_bytes(out) <= REPLY_BYTES
    assert changed["total"] > 6
    assert len(changed["items"]) == 6
    assert changed["omitted"] == changed["total"] - 6


async def _drawing(client: Client, system: ProductSystem) -> dict:
    """The arrangement the page draws, from which the tidy cases take their free places."""
    out = await client.call_tool(
        "graph_layout", {"product_system_id": str(system.id), "detail": "drawing"}
    )
    return out.structured_content["value"]


def _held_at(
    free: dict[str, dict], code: str, placed_by: str | None = None, dy: float = 0.0
) -> Spot:
    """Where the free drawing puts `code`, moved down by `dy`, held by `placed_by`."""
    card = free[code]
    return Spot(x=card["x"], y=card["y"] + dy, placed_by=placed_by)


def _staged_nine_holds(free: dict[str, dict], system: ProductSystem) -> dict[str, dict[str, Spot]]:
    """The tidy cases on the nine-card cathode: an agent's card at the foot of the refinery's
    column misplaces it, a card just below its own place draws almost as well, and one case also
    holds a service's card and one that records no placer."""
    person = _held_at(free, "concentrator", "person")
    misplaced = {
        "concentrator": person,
        "desal": _held_at(free, "refinery", "agent", dy=free["refinery"]["height"] + 60.0),
    }
    return {
        "misplaced": misplaced,
        "useful": {"concentrator": person, "desal": Spot(x=1000.0, y=238.0, placed_by="agent")},
        "misplaced_with_others": {
            **misplaced,
            "grid": _held_at(free, "grid", "service"),
            "mine": _held_at(free, "mine"),
        },
    }


def _hundred_holds(free: dict[str, dict], system: ProductSystem) -> dict[str, dict[str, Spot]]:
    """The tidy cases on the hundred-card system: an agent's card at the foot of the reference's
    column, five agent cards where the free drawing puts them, and the first case also holding a
    service's card and one that records no placer."""
    reference = system.reference_process
    assert reference is not None
    codes = [code for code in free if code != reference and not code.startswith("system:")]
    person, mover, *others = codes
    misplaced = {
        person: _held_at(free, person, "person"),
        mover: _held_at(free, reference, "agent", dy=free[reference]["height"] + 60.0),
    }
    return {
        "misplaced": misplaced,
        "useful": {
            person: _held_at(free, person, "person"),
            **{code: _held_at(free, code, "agent") for code in codes[1:6]},
        },
        "misplaced_with_others": {
            **misplaced,
            others[0]: _held_at(free, others[0], "service"),
            others[1]: _held_at(free, others[1]),
        },
    }


TIDY_CASES = [
    pytest.param(staged_nine, _staged_nine_holds, "misplaced", 15, 3, id="staged_nine-misplaced"),
    pytest.param(staged_nine, _staged_nine_holds, "useful", 1, 3, id="staged_nine-useful"),
    pytest.param(
        staged_nine,
        _staged_nine_holds,
        "misplaced_with_others",
        13,
        8,
        id="staged_nine-misplaced-with-others",
    ),
    pytest.param(hundred, _hundred_holds, "misplaced", 799, 722, id="hundred-misplaced"),
    pytest.param(hundred, _hundred_holds, "useful", 722, 722, id="hundred-useful"),
    pytest.param(
        hundred,
        _hundred_holds,
        "misplaced_with_others",
        801,
        722,
        id="hundred-misplaced-with-others",
    ),
]


async def _unaltered(context: ServerContext, client: Client, system: ProductSystem) -> dict:
    """What a layout call leaves alone: the content hash, the processes with the stages and
    exchanges they carry, and one fixed method's impact."""
    stored = await context.storage.get_product_system(system.id)
    impact = await client.call_tool(
        "calculate_impact", {"product_system_id": str(system.id), "method_id": GWP_ID}
    )
    return {
        "hash": content_hash(stored),
        "processes": [process.model_dump(mode="json") for process in stored.processes],
        "impact": impact.structured_content["value"],
    }


@pytest.mark.parametrize(("build", "holds", "case", "held_score", "released_score"), TIDY_CASES)
async def test_a_tidy_request_saves_a_release_only_when_it_lowers_the_score(
    context: ServerContext,
    build: Callable[[], ProductSystem],
    holds: Callable[[dict[str, dict], ProductSystem], dict[str, dict[str, Spot]]],
    case: str,
    held_score: int,
    released_score: int,
) -> None:
    system = await _store(context, build())
    served = dataclasses.replace(context, view_url=LONG_VIEW_URL)
    counted = CountedWrites(context.storage)
    watched = dataclasses.replace(served, storage=counted)
    try:
        async with Client(build_server(served)) as client:
            free = {card["code"]: card for card in (await _drawing(client, system))["cards"]}
            carried = holds(free, system)[case]
            await context.storage.put_layout(system.id, Layout(held=carried), expected=None)
            before = await _unaltered(context, client, system)
            entries = await context.storage.log(system.id)
        async with Client(build_server(watched)) as client:
            out = await client.call_tool(
                "arrange_graph",
                {
                    "product_system_id": str(system.id),
                    "placements": [],
                    "release_agent_holds": True,
                    "only_if_better": True,
                },
            )
            stored = await context.storage.get_layout(system.id)
            after = await _unaltered(context, client, system)
            drawn = await _drawing(client, system)
            log = await context.storage.log(system.id)
    finally:
        await _delete(context, system)
    written = out.structured_content["value"]
    saved = released_score < held_score
    assert rendered_bytes(out) <= REPLY_BYTES
    assert written["saved"] is saved
    assert written["score_before"] == held_score
    assert written["score_after"] == (released_score if saved else held_score)
    assert drawn["score"] == written["score_after"]
    assert written["troubles"] == _counted([trouble["kind"] for trouble in drawn["troubles"]])
    assert out.structured_content["view_url"] == served.deep_link(system.id)
    kept = {code: spot for code, spot in carried.items() if spot.placed_by != "agent"}
    displaced = [code for code, spot in carried.items() if spot.placed_by == "agent"]
    if saved:
        assert counted.layouts == [Layout(held=kept)]
        assert stored.held == kept
        assert displaced[0] in [item["code"] for item in written["changed"]["items"]]
    else:
        assert counted.layouts == []
        assert stored.held == carried
        assert log == entries
        assert written["changed"] == {"items": [], "total": 0, "omitted": 0}
        assert written["added"] == {"items": [], "total": 0, "omitted": 0}
        assert written["resolved"] == {"items": [], "total": 0, "omitted": 0}
    text, body = _text(out), json.dumps(out.structured_content)
    for key in ('"map"', '"points"', '"edges"', '"cards"', '"amount"'):
        assert key not in text and key not in body, key
    assert after == before


@pytest.mark.parametrize(
    ("given", "reason"),
    [
        ({"placements": [{"code": "mine", "x": 10.0, "y": 20.0}]}, "beside placements"),
        ({"release_all": True}, "beside release_all, which is a reset"),
        ({}, "needs release or release_agent_holds"),
    ],
)
async def test_only_if_better_is_refused_where_it_cannot_judge(
    context: ServerContext, given: dict[str, object], reason: str
) -> None:
    system = await _store(context, staged_nine())
    await context.storage.put_layout(
        system.id, Layout(held={"mine": Spot(x=40.0, y=60.0, placed_by="person")}), expected=None
    )
    held = await context.storage.get_layout(system.id)
    counted = CountedWrites(context.storage)
    try:
        async with Client(build_server(dataclasses.replace(context, storage=counted))) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "arrange_graph",
                    {
                        "product_system_id": str(system.id),
                        "placements": [],
                        **given,
                        "only_if_better": True,
                    },
                )
    finally:
        await _delete(context, system)
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid"
    assert reason in payload["message"]
    assert counted.layouts == []
    assert held.held == {"mine": Spot(x=40.0, y=60.0, placed_by="person")}
