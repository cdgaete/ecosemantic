"""The graph tools: read where the cards are drawn, and put them somewhere else."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel

from ecosemantic.compute.links import held_pins, linked_documents
from ecosemantic.compute.overrides import apply_variant
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Invalid
from ecosemantic.geometry import Placement, link_texts, links
from ecosemantic.layout import arrange, bounds
from ecosemantic.mcp.calculation import demand_of, refuse_stale
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ, WRITE
from ecosemantic.mcp.envelopes import Answer, as_uuid, bound, boundary
from ecosemantic.model.refs import ElementaryFlowRef
from ecosemantic.model.validation import SOLVABLE, anchors, validate
from ecosemantic.ports.types import Layout, Spot, System
from ecosemantic.routes import Route, route
from ecosemantic.scaling import Scaled, scale
from ecosemantic.textmap import as_text
from ecosemantic.troubles import Trouble, score, troubles


class Arrangement(BaseModel):
    """Where every card of a product system is drawn and how every arrow runs: the map an agent
    reads, the numbers the page draws, what is wrong with the drawing and its score."""

    map: str
    cards: list[Placement]
    edges: list[Route]
    troubles: list[Trouble]
    score: int
    bounds: dict[str, float]
    scaling: str | None


class CardSpot(BaseModel):
    """One card put somewhere."""

    code: str
    x: float
    y: float


async def _arrangement(
    context: ServerContext, product_system_id: str, variant: str | None
) -> Arrangement:
    system_id = as_uuid(product_system_id)
    stored = await context.storage.get_product_system(system_id)
    if variant is None:
        system = stored
    else:
        await refuse_stale(context, stored, [variant])
        system = apply_variant(stored, variant)
    stored = await context.storage.get_layout(system_id)
    held = {code: (spot.x, spot.y) for code, spot in stored.held.items()}
    flows = {
        e.input.id: e.input
        for p in system.processes
        for e in p.exchanges
        if isinstance(e.input, ElementaryFlowRef)
    }
    sides = {
        flow_id: (await context.inventory.get_elementary_flow(ref)).side
        for flow_id, ref in flows.items()
    }
    report = validate(system, system.reference_process, await held_pins(system, context.storage))
    blocking = [i for i in report.errors if i.case in SOLVABLE]
    reason = blocking[0].message if blocking else None
    scaled: dict[str, Scaled] | None = None
    if reason is None:
        linked = await linked_documents(system, context.storage.get_version)
        base = materialize(system)
        activities = await context.calculation.supply(
            System.of(base, linked), demand_of(base, None)
        )
        scaled = scale(base, linked, activities)
    amounts = None if scaled is None else {c: s.amounts for c, s in scaled.items()}
    placements = arrange(system, anchors(system), held, sides, amounts)
    if scaled is not None:
        placements = [
            p.model_copy(
                update={"activity": scaled[p.code].activity, "scaled": scaled[p.code].amounts}
            )
            for p in placements
        ]
    routes = route(placements, links(system), link_texts(system, amounts))
    found = troubles(placements, routes)
    return Arrangement(
        map=as_text(system, placements, routes),
        cards=placements,
        edges=routes,
        troubles=found,
        score=score(found),
        bounds=bounds(placements),
        scaling=reason,
    )


async def graph_layout(
    context: ServerContext, product_system_id: str, variant: str | None = None
) -> Answer[Arrangement]:
    return Answer[Arrangement](value=await _arrangement(context, product_system_id, variant))


async def arrange_graph(
    context: ServerContext,
    product_system_id: str,
    placements: list[CardSpot],
    release: list[str] | None = None,
    variant: str | None = None,
) -> Answer[Arrangement]:
    system_id = as_uuid(product_system_id)
    released = set(release or [])
    both = sorted({placement.code for placement in placements} & released)
    if both:
        raise Invalid(f"placements and release both name {', '.join(both)}")
    stored = await context.storage.get_layout(system_id)
    held = {code: spot for code, spot in stored.held.items() if code not in released}
    for placement in placements:
        held[placement.code] = Spot(x=placement.x, y=placement.y)
    await context.storage.put_layout(system_id, Layout(held=held))
    return Answer[Arrangement](value=await _arrangement(context, product_system_id, variant))


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the graph tools, in roster order."""
    server.tool(
        name="graph_layout",
        annotations=READ,
        description=(
            "Where every process of a product system is drawn and how every arrow runs, exactly "
            "as the page draws it: a map in characters with its legend on the first line, each "
            "card's place, size and row anchors, each arrow's corner points and label, what is "
            "wrong with the drawing, and a score where 0 means nothing is wrong. The drawing is "
            "scaled to one unit of the reference process's product: each card carries its "
            "activity, how many times its process runs, and scaled, each exchange's amount at "
            "that activity; each label carries its per-unit and its scaled text, and the map "
            "titles each card with its scaled output and writes each row's scaled amount. When "
            "the engine cannot solve the system, scaling names why and nothing is scaled. Name a "
            "case or a scenario as variant to draw every row, arrow and label under it, as "
            "calculate_impact evaluates a variant. Read it before arrange_graph."
        ),
    )(boundary(bound(graph_layout, context)))
    server.tool(
        name="arrange_graph",
        annotations=WRITE,
        description=(
            "Put named cards at given places and answer the drawing that results. A card put "
            "here is held exactly as one a person dragged: the automatic arrangement packs the "
            "others around it and never moves it. Name cards in release to let them go back to "
            "the automatic layout; placements and release naming one card is refused. Move cards, "
            "read the map and the score, and move again until the score is 0 or stops falling. "
            "The answer is graph_layout's: activity, scaled amounts, labels and scaling, under the "
            "variant when one is named; where a card is held does not depend on the variant."
        ),
    )(boundary(bound(arrange_graph, context)))
