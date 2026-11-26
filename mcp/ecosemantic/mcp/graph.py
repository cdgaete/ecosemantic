"""The graph tools: read where the cards are drawn, and put them somewhere else."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ecosemantic.compute.links import held_pins, linked_documents
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.geometry import (
    CardGeometry,
    Placement,
    SharedSupplier,
    StageRegions,
    card_geometry,
    link_texts,
    links,
)
from ecosemantic.layout import arrange, bounds, nodes, shared_suppliers, stage_regions
from ecosemantic.mcp.calculation import demand_of, variant_of
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ, WRITE
from ecosemantic.mcp.envelopes import Answer, as_uuid, bound, boundary, serialised
from ecosemantic.mcp.graph_replies import (
    AMOUNT_ACTIVITIES,
    AMOUNT_ROWS,
    Amounts,
    CardActivity,
    CardAmounts,
    CompactRead,
    CompactWrite,
    Focus,
    bounded,
    compact_read,
    compact_write,
    cursor_after,
    focus,
    placed_summary,
)
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import ElementaryFlowRef
from ecosemantic.model.summary import SUMMARY_ITEMS, Summary
from ecosemantic.model.validation import SOLVABLE, anchors, validate
from ecosemantic.ports.inventory import no_flow
from ecosemantic.ports.types import Layout, Side, Spot, System, page_start
from ecosemantic.routes import Route, route
from ecosemantic.scaling import Scaled, scale, scaled_rows
from ecosemantic.textmap import as_text
from ecosemantic.troubles import Trouble, score, troubles

Detail = Literal["compact", "amounts", "drawing", "full"]
WriteDetail = Literal["compact", "drawing", "full"]


class Arrangement(BaseModel):
    """Where every card of a product system is drawn and how every arrow runs: the map an agent
    reads where the answer asked for it, the numbers the page draws, what is wrong with the
    drawing and its score. `card` is the geometry every card is drawn at."""

    kind: Literal["arrangement"] = "arrangement"
    map: str | None
    cards: list[Placement]
    edges: list[Route]
    troubles: list[Trouble]
    score: int
    bounds: dict[str, float]
    scaling: str | None
    stages: list[StageRegions]
    shared_suppliers: list[SharedSupplier]
    card: CardGeometry

    def summarise(self) -> Summary | None:
        """The cards someone placed and their codes; nothing while a person has placed none."""
        return placed_summary([card.code for card in self.cards if card.held])


LayoutRead = Annotated[CompactRead | Focus | Amounts | Arrangement, Field(discriminator="kind")]
LayoutWrite = Annotated[CompactWrite | Arrangement, Field(discriminator="kind")]


PLACEMENT_LIMIT = 100_000.0


class CardSpot(BaseModel):
    """One card put somewhere."""

    code: str
    x: float = Field(ge=-PLACEMENT_LIMIT, le=PLACEMENT_LIMIT)
    y: float = Field(ge=-PLACEMENT_LIMIT, le=PLACEMENT_LIMIT)


def _named(codes: Sequence[str]) -> str:
    """Codes as a refusal names them: the first `SUMMARY_ITEMS` with each quoted, and how many
    more there are."""
    first = [repr(code) for code in codes[:SUMMARY_ITEMS]]
    rest = len(codes) - len(first)
    named = ", ".join(first)
    return f"{named} and {rest} more" if rest else named


def _draw(
    system: ProductSystem,
    layout: Layout,
    sides: dict[str, Side],
    scaled: dict[str, Scaled] | None,
    reason: str | None,
    *,
    mapped: bool,
    expanded: Sequence[str] = (),
) -> Arrangement:
    """`system` drawn with `layout`'s cards held, its elementary flows on `sides` and its amounts
    scaled from `scaled`, with `reason` naming why nothing is scaled, the cards `expanded` showing
    every row, and the text map built when `mapped`. Awaits nothing, so a caller runs it off the
    event loop."""
    held = {code: (spot.x, spot.y) for code, spot in layout.held.items()}
    amounts = None if scaled is None else {c: s.amounts for c, s in scaled.items()}
    placements = arrange(system, anchors(system), held, sides, amounts, expanded)
    if scaled is not None:
        placements = [
            p.model_copy(
                update={"activity": scaled[p.code].activity, "scaled": scaled[p.code].amounts}
            )
            for p in placements
        ]
    placer_of = {code: spot.placed_by for code, spot in layout.held.items()}
    placements = [
        card.model_copy(update={"placed_by": placer_of[card.code] if card.held else None})
        for card in placements
    ]
    routes = route(placements, links(system), link_texts(system, amounts))
    found = troubles(placements, routes)
    stages = stage_regions(system, placements)
    return Arrangement(
        map=as_text(system, placements, routes, stages) if mapped else None,
        cards=placements,
        edges=routes,
        troubles=found,
        score=score(found),
        bounds=bounds(placements),
        scaling=reason,
        stages=stages,
        shared_suppliers=shared_suppliers(system),
        card=card_geometry(),
    )


async def _arrangements(
    context: ServerContext,
    system: ProductSystem,
    variant: str | None,
    layouts: Sequence[Layout],
    *,
    mapped: bool,
    expanded: Sequence[str] = (),
) -> list[Arrangement]:
    """`system` arranged under `variant` once per layout, each with that layout's cards held where
    it puts them and its map built when `mapped`; the ports are asked once for all of them."""
    scaling = await _scaling(context, system, variant)
    return [
        await asyncio.to_thread(
            _draw,
            scaling.system,
            layout,
            scaling.sides,
            scaling.scaled,
            scaling.reason,
            mapped=mapped,
            expanded=expanded,
        )
        for layout in layouts
    ]


@dataclass(frozen=True)
class _Scaling:
    """What a call reads once for the drawing it answers: the system under its variant, the systems
    it links, each card's activity and amounts, the side each elementary flow sits on, and the
    reason nothing is scaled."""

    system: ProductSystem
    linked: dict[uuid.UUID, ProductSystem]
    scaled: dict[str, Scaled] | None
    reason: str | None
    sides: dict[str, Side]


async def _sides(context: ServerContext, system: ProductSystem) -> dict[str, Side]:
    """The side of its process each elementary flow of `system` sits on, read once per database;
    NotFound names a flow its database does not hold."""
    flows = {
        e.input.id: e.input
        for p in system.processes
        for e in p.exchanges
        if isinstance(e.input, ElementaryFlowRef)
    }
    by_database: dict[str, list[ElementaryFlowRef]] = {}
    for ref in flows.values():
        by_database.setdefault(ref.database, []).append(ref)
    sides: dict[str, Side] = {}
    for database, refs in by_database.items():
        answered = {
            flow.ref.id: flow
            for flow in await context.inventory.get_elementary_flows(
                database, [ref.id for ref in refs]
            )
        }
        for ref in refs:
            found = answered.get(ref.id)
            if found is None:
                raise no_flow(ref)
            sides[ref.id] = found.side
    return sides


async def _scaling(context: ServerContext, system: ProductSystem, variant: str | None) -> _Scaling:
    """`system` under `variant`, validated and solved once: every card's activity and amounts, the
    side each elementary flow sits on, or the reason the engine cannot solve it and nothing
    scaled."""
    if variant is not None:
        system = await variant_of(context, system, variant)
    sides = await _sides(context, system)
    report = validate(system, system.reference_process, await held_pins(system, context.storage))
    blocking = [i for i in report.errors if i.case in SOLVABLE]
    reason = blocking[0].message if blocking else None
    if reason is not None:
        return _Scaling(system=system, linked={}, scaled=None, reason=reason, sides=sides)
    linked = await linked_documents(system, context.storage.get_version)
    base = system if variant is not None else materialize(system)
    activities = await context.calculation.supply(System.of(base, linked), demand_of(base, None))
    return _Scaling(
        system=system,
        linked=linked,
        scaled=scale(base, linked, activities),
        reason=None,
        sides=sides,
    )


def _amounts_page(
    scaling: _Scaling,
    variant: str | None,
    page: int,
    card: str | None,
    held: Sequence[str],
) -> Amounts:
    """One page of the cards' activities, or of `card`'s rows, with `held` as the cards someone
    placed."""
    if scaling.scaled is None:
        return Amounts(variant=variant, scaling=scaling.reason, next_cursor=None).placing(held)
    if card is None:
        activities = bounded(
            [
                CardActivity(code=code, activity=scaling.scaled[code].activity)
                for code in nodes(scaling.system)
            ],
            page,
            AMOUNT_ACTIVITIES,
        )
        return Amounts(
            variant=variant,
            activities=activities,
            next_cursor=cursor_after(page, activities),
        ).placing(held)
    rows = bounded(
        scaled_rows(scaling.system, scaling.linked, scaling.scaled, card), page, AMOUNT_ROWS
    )
    return Amounts(
        variant=variant,
        card=CardAmounts(code=card, activity=scaling.scaled[card].activity, rows=rows),
        next_cursor=cursor_after(page, rows),
    ).placing(held)


def _expansion(expanded: Sequence[str] | None, drawn: Collection[str]) -> list[str]:
    """The cards a drawing shows every row of; Invalid naming a card this system does not draw."""
    named = list(expanded or ())
    unknown = sorted({code for code in named if code not in drawn})
    if unknown:
        raise Invalid(f"this system draws no card {_named(unknown)}: expand a code it draws")
    return named


def _placed(layout: Layout, drawn: Collection[str]) -> list[str]:
    """The codes of the cards someone holds that the drawing draws."""
    return [code for code in layout.held if code in drawn]


async def _amounts(
    context: ServerContext,
    system: ProductSystem,
    variant: str | None,
    layout: Layout,
    card: str | None,
    cursor: str | None,
) -> Amounts:
    """The cards' activities, or one card's scaled rows, without placing, routing or scoring a
    card: the drawing is read for the summary alone."""
    drawn = nodes(system)
    if card is not None and card not in drawn:
        raise NotFound(f"this system draws no card {_named([card])}: name a code it draws")
    page = page_start(cursor, 1)
    scaling = await _scaling(context, system, variant)
    return _amounts_page(scaling, variant, page, card, _placed(layout, drawn))


async def graph_layout(
    context: ServerContext,
    product_system_id: str,
    variant: str | None = None,
    detail: Detail = "compact",
    card: str | None = None,
    exchange_id: str | None = None,
    cursor: str | None = None,
    expanded: list[str] | None = None,
) -> Answer[LayoutRead]:
    system_id = as_uuid(product_system_id)
    for name, value in (("card", card), ("cursor", cursor)):
        if detail not in ("amounts", "compact") and value is not None:
            raise Invalid(f'{name} has no meaning under detail="{detail}"')
    if expanded and detail == "amounts":
        raise Invalid('expanded has no meaning under detail="amounts"')
    if exchange_id is not None and detail != "compact":
        raise Invalid(f'exchange_id has no meaning under detail="{detail}"')
    if exchange_id is not None and card is not None:
        raise Invalid(
            f'card and exchange_id both name what detail="{detail}" focuses on; pass one of them'
        )
    named = None if exchange_id is None else as_uuid(exchange_id)
    system = await context.storage.get_product_system(system_id)
    layout = await context.storage.get_layout(system_id)
    if detail == "amounts":
        value = await _amounts(context, system, variant, layout, card, cursor)
        return Answer[LayoutRead](value=value)
    rows = _expansion(expanded, nodes(system))
    [arrangement] = await _arrangements(
        context, system, variant, [layout], mapped=detail == "full", expanded=rows
    )
    if detail != "compact":
        return Answer[LayoutRead](value=arrangement)
    page = page_start(cursor, 1)
    read: CompactRead | Focus
    if card is None and named is None:
        read = compact_read(arrangement, variant, page)
    else:
        read = focus(arrangement, variant, page, card=card, exchange_id=named)
    return Answer[LayoutRead](value=read.placing(_placed(layout, nodes(system))))


async def arrange_graph(
    context: ServerContext,
    product_system_id: str,
    placements: list[CardSpot],
    release: list[str] | None = None,
    release_all: bool = False,
    release_agent_holds: bool = False,
    only_if_better: bool = False,
    variant: str | None = None,
    detail: WriteDetail = "compact",
    expanded: list[str] | None = None,
) -> Answer[LayoutWrite]:
    """Move `placements`' cards to their places, let `release`'s cards and, under `release_all`,
    every held card go, and under `release_agent_holds` every hold an agent placed, write the
    layout the call ends at and answer what changed: whether it saved, the score before and after,
    the troubles the drawing now carries, the changed cards and the issues added and resolved,
    each in one page, under `detail="compact"`; the drawing itself, its map under `full` alone,
    otherwise. Under `only_if_better` both drawings are compared and the release is written only
    when it scores lower, the answer then being the drawing that stands."""
    system_id = as_uuid(product_system_id)
    if release and release_all:
        raise Invalid("release and release_all both let cards go; pass one of them")
    if release_agent_holds and release_all:
        raise Invalid("release_agent_holds and release_all both let cards go; pass one of them")
    if only_if_better and release_all:
        raise Invalid("only_if_better has no meaning beside release_all, which is a reset")
    if only_if_better and placements:
        raise Invalid("only_if_better has no meaning beside placements, which are always saved")
    if only_if_better and not release and not release_agent_holds:
        raise Invalid("only_if_better needs release or release_agent_holds: nothing lets a card go")
    released = set(release or [])
    placed = [placement.code for placement in placements]
    both = sorted(set(placed) & released)
    if both:
        raise Invalid(f"placements and release both name {_named(both)}")
    twice = sorted({code for code in placed if placed.count(code) > 1})
    if twice:
        raise Invalid(f"placements name {_named(twice)} more than once")
    system = await context.storage.get_product_system(system_id)
    drawn = nodes(system)
    stranger = sorted({code for code in placed if code not in drawn})
    if stranger:
        raise Invalid(f"this system draws no card {_named(stranger)}: place a code it draws")
    rows = _expansion(expanded, drawn)
    stored = Layout()
    if not release_all:
        stored = await context.storage.get_layout(system_id)
        unknown = sorted(code for code in released if code not in drawn and code not in stored.held)
        if unknown:
            raise Invalid(
                f"release names {_named(unknown)}, which this system neither draws nor holds"
            )
    held = {code: spot for code, spot in stored.held.items() if code not in released}
    if release_agent_holds:
        held = {code: spot for code, spot in held.items() if spot.placed_by != "agent"}
    placer = context.placing()
    for placement in placements:
        at = held.get(placement.code)
        if at is not None and (at.x, at.y) == (placement.x, placement.y):
            held[placement.code] = at
        else:
            held[placement.code] = Spot(x=placement.x, y=placement.y, placed_by=placer)
    candidate = Layout(held=held)
    changed = release_all or candidate != stored
    judged = only_if_better and changed
    compared = judged or (detail == "compact" and not release_all and changed)
    drawn = await _arrangements(
        context,
        system,
        variant,
        [stored, candidate] if compared else [candidate],
        mapped=detail == "full",
        expanded=rows,
    )
    before_drawn = drawn[0] if compared else None
    released_drawing = drawn[-1]
    saved = changed
    standing = released_drawing
    if before_drawn is not None and only_if_better:
        if released_drawing.score >= before_drawn.score:
            saved = False
            standing = before_drawn
    if saved:
        await context.storage.put_layout(
            system_id, candidate, expected=None if release_all else stored
        )
    if detail != "compact":
        return Answer[LayoutWrite](value=standing)
    before = None if release_all else drawn[0]
    write = compact_write(before, standing, variant, saved=saved, named=[*placed, *(release or [])])
    return Answer[LayoutWrite](
        value=write.placing([card.code for card in standing.cards if card.held]),
        view_url=context.deep_link(system_id),
    )


def register(server: FastMCP) -> None:
    """Register the graph tools, in roster order."""
    server.tool(
        name="graph_layout",
        annotations=READ,
        description=(
            "Where a product system's cards are drawn, and what is wrong with the drawing. detail "
            "selects the answer. compact, the default, reads the drawing compactly: the score, "
            "where 0 means nothing is wrong, the bounds, why nothing is scaled, how many troubles "
            "of each kind and how many cards each placer holds, then the cards' codes, places, "
            "sizes, holds and placers and the issues with the cards and exchanges each concerns, "
            "the heaviest first, in pages of 10 cards and 3 issues with their totals and a cursor "
            'for the next page. detail="amounts" answers the scaled numbers alone, without '
            "drawing anything: without card every card's activity, and with card that card's rows "
            "of exchange id, name, scaled amount and unit, in pages of 30 activities or 15 rows; "
            "read the scaled amounts there when a check needs them. drawing answers the whole "
            "arrangement as the page draws it, its map null: each card's place, size and row "
            "anchors, each arrow's corner points and label, and the same troubles, score and "
            "bounds compact reads. full answers that arrangement with a map in characters whose "
            "legend is the first line. card focuses on that card: its own row, every arrow it "
            "carries and every issue that names it. exchange_id focuses on one arrow: the two "
            "cards it joins, its first and last point, the label the drawing shows and the "
            "issues that name it; the two exchanges one pair of cards carries are told apart by "
            "it. A focus answers 5 arrows and 3 issues a page. cursor is the page to read, none "
            "the first. A card with more input or output rows than it shows folds them behind a "
            "row that says how many; the inputs that draw an arrow and the production output are "
            "always shown, at an anchor of their own. expanded names the cards whose rows the "
            "page shows in full, so a read matches the drawing on screen; it is refused under "
            "amounts, which draws nothing. The drawing is scaled to one unit of the reference "
            "process's product: "
            "each card carries its activity, how many times its process runs, and its scaled "
            "amounts, and each label its per-unit and its scaled text. Name a case or a scenario "
            "as variant to read every row, arrow and label under it, as calculate_impact "
            "evaluates a variant, and when the engine cannot solve the system, scaling names why "
            "and nothing is scaled. A system whose processes carry life_cycle_stage is drawn one "
            "band of columns per stage, from the functional unit's stage at the right, processes "
            "of no stage leftmost; stages lists each stage's cards and regions, and "
            "shared_suppliers each process of no stage that feeds several stages. Read the "
            "drawing once the model and its results are settled, in a subagent or a separate "
            "session when the client has one. Read it when a placement needs inspection, not "
            "before every write."
        ),
    )(boundary(bound(graph_layout)))
    server.tool(
        name="arrange_graph",
        annotations=WRITE,
        description=(
            "Put named cards at given places and answer what changed. A card put "
            "here is held exactly as one a person dragged: the automatic arrangement packs the "
            "others around it and never moves it, and an explicit placement is saved even when it "
            "worsens the score; a nonzero score alone is not a reason to move another card. "
            "Name cards in release to let them go back to "
            "the automatic layout; placements and release naming one card is refused. Pass "
            "release_all to let every held card go, drawn or not, before placements apply; "
            "release_all beside release is refused. Pass release_agent_holds to let go every "
            "hold an agent placed and keep a person's, a service's and one that records no placer, "
            "before placements apply; the scores before and after say whether the release drew a "
            "better drawing or a worse one, and it saves either way. Pass only_if_better to save "
            "that release only when the drawing it leads to scores lower than the stored one, the "
            "two compared under the variant named at every detail: it is the one call that tidies "
            "a graph, keeping where a person, a service and a hold that records no placer put "
            "their cards. When the release is no better, nothing is written and the answer is the "
            "stored drawing, with saved false, the same score before and after and no changed "
            "card. It is refused beside placements, which are always saved, beside release_all, "
            "which is a reset, and without release or release_agent_holds, nothing having been "
            "let go to judge. release_agent_holds beside "
            "release_all is refused. Use this tool when placement is part of the "
            "request. Arrange the "
            "cards once the model and its results are settled, in a subagent or a separate "
            "session when the client has one, and bring back the score, the troubles left and "
            "the page link. detail selects the answer. compact, the default, answers what the "
            "call changed: whether it saved, the score before and after, where 0 means nothing "
            "is wrong, how many troubles of each kind the drawing now carries, the cards whose "
            "place, hold or placer differs from the drawing before, a card the arrangement moved "
            "by itself included, with each card's x, y, held and placed_by before and after and "
            "the cards the call named first, and the issues the call added and resolved, the "
            "heaviest first, in one page of 6 changed cards, 2 added and 2 resolved with their "
            "totals, and the product system's page link where a view is served; release_all, "
            "which reads no stored layout, answers null for the score before, the changed cards "
            'and those differences. detail="drawing" answers the whole arrangement as the page '
            'draws it, its map null, and detail="full" that arrangement with a map in characters '
            "whose legend is the first line: each card's place, size and row anchors, each "
            "arrow's corner points and label, the troubles, score, bounds and scaling compact "
            "reads, and every card's activity and scaled amounts and every label's per-unit and "
            "scaled text, under the variant when one is named; where a card is held does not "
            "depend on the variant. expanded names the cards whose rows the page shows in full, "
            "so the drawing answered has the size and the anchors the page displays; it moves "
            "nothing and saves no row, and a card this system does not draw is refused."
        ),
    )(boundary(serialised(bound(arrange_graph))))
