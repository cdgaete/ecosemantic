"""Where a product system's processes are drawn: the size of a card, its distance from the
functional unit, and the arrangement the page and the tools both read."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from itertools import permutations

from pydantic import BaseModel

from ecosemantic.geometry import (
    CARD_WIDTH,
    COLUMN_GAP,
    COLUMN_TOP,
    LINKED,
    ROW_GAP,
    Placement,
    Port,
    card_size,
    link_texts,
    linked_card,
    linked_code,
    links,
    ports,
    rows,
    shown_inputs,
)
from ecosemantic.model.entities import Process, ProductSystem
from ecosemantic.model.refs import ForegroundRef, SystemRef
from ecosemantic.ports.types import Side
from ecosemantic.routes import route
from ecosemantic.troubles import score, troubles

MAX_PERMUTED = 6


class _Anatomy(BaseModel):
    """What a card's contents fix about it, whichever place the search tries it at."""

    width: float
    height: float
    shown_inputs: int
    inputs: list[Port]
    outputs: list[uuid.UUID]
    output: float


def _anatomy(process: Process, sides: Mapping[str, Side]) -> _Anatomy:
    width, height = card_size(process, sides)
    found, output = ports(process, sides)
    return _Anatomy(
        width=width,
        height=height,
        shown_inputs=shown_inputs(process, sides),
        inputs=found,
        outputs=[e.id for e in rows(process, sides)[1]],
        output=output,
    )


def _linked_anatomy() -> _Anatomy:
    width, height, output = linked_card()
    return _Anatomy(
        width=width, height=height, shown_inputs=0, inputs=[], outputs=[], output=output
    )


def providers_of(process: Process) -> list[str]:
    """The cards that feed one process: the processes of its product system by code, and each
    linked system by its card's key."""
    found: list[str] = []
    for e in process.exchanges:
        if isinstance(e.input, ForegroundRef):
            found.append(e.input.code)
        elif isinstance(e.input, SystemRef) and linked_code(e.input) not in found:
            found.append(linked_code(e.input))
    return found


def nodes(system: ProductSystem) -> dict[str, list[str]]:
    """Every card of a drawing with the cards that feed it: each process, and each linked
    system once, which nothing in this system feeds."""
    found = {p.code: providers_of(p) for p in system.processes}
    for providers in list(found.values()):
        for provider in providers:
            if provider.startswith(LINKED):
                found.setdefault(provider, [])
    return found


def _without_cycles(edges: dict[str, list[str]], anchors: list[str]) -> dict[str, list[str]]:
    """The provider edges with those that close a cycle dropped, so a column is well defined.
    The walk starts at the anchors, so a loop through an anchor loses the edge back into it."""
    state: dict[str, int] = {}
    kept: dict[str, list[str]] = {code: [] for code in edges}
    order = [code for code in anchors if code in edges] + sorted(set(edges) - set(anchors))

    def visit(code: str) -> None:
        state[code] = 1
        for provider in edges.get(code, []):
            if state.get(provider, 0) == 1 or provider not in kept:
                continue
            kept[code].append(provider)
            if state.get(provider, 0) == 0:
                visit(provider)
        state[code] = 2

    for code in order:
        if state.get(code, 0) == 0:
            visit(code)
    return kept


def depths(system: ProductSystem, anchors: list[str]) -> dict[str, int]:
    """Each process's column: every anchor is zero and its providers grow leftwards by the
    longest path to them. A process the walk never reaches sits one past the deepest."""
    kept = _without_cycles(nodes(system), anchors)
    found: dict[str, int] = {code: 0 for code in anchors}
    changed = True
    while changed:
        changed = False
        for code, providers in kept.items():
            if code not in found:
                continue
            for provider in providers:
                if found.get(provider, -1) < found[code] + 1:
                    found[provider] = found[code] + 1
                    changed = True
    deepest = max(found.values(), default=-1)
    for code in kept:
        if code not in found:
            found[code] = deepest + 1
    return found


def _ordered(column: list[str], previous: list[str], consumers: dict[str, list[str]]) -> list[str]:
    """One column ordered by the median position of the cards it feeds in the column before it,
    which is what reduces crossings; a card feeding nothing there keeps its place."""
    rank = {code: i for i, code in enumerate(previous)}

    def median(code: str) -> float:
        positions = sorted(rank[n] for n in consumers.get(code, []) if n in rank)
        if not positions:
            return float(column.index(code))
        return float(positions[len(positions) // 2])

    return sorted(column, key=lambda code: (median(code), code))


def _held_spans(
    held: dict[str, tuple[float, float]],
    sizes: dict[str, tuple[float, float]],
    x: float,
) -> list[tuple[float, float]]:
    """The vertical spans a column at this x already holds, from every held card whose
    rectangle overlaps this x, whatever column its code was assigned to."""
    return [
        (top, top + sizes[code][1])
        for code, (left, top) in held.items()
        if code in sizes and left < x + CARD_WIDTH and x < left + sizes[code][0]
    ]


def _stack(
    codes: list[str],
    sizes: dict[str, tuple[float, float]],
    taken: list[tuple[float, float]],
) -> dict[str, float]:
    """Each card's top in one column, packed below the last and skipped past any span already
    taken by a held card."""
    tops: dict[str, float] = {}
    y = COLUMN_TOP
    for code in codes:
        height = sizes[code][1]
        moved = True
        while moved:
            moved = False
            for start, end in taken:
                if y < end + ROW_GAP and start < y + height + ROW_GAP:
                    y = end + ROW_GAP
                    moved = True
        tops[code] = y
        y += height + ROW_GAP
    return tops


def bounds(placements: list[Placement]) -> dict[str, float]:
    """How much room the drawing takes, and how much of the tallest column is gap."""
    if not placements:
        return {"width": 0.0, "height": 0.0, "wasted": 0.0}
    left = min(p.x for p in placements)
    top = min(p.y for p in placements)
    width = max(p.x + p.width for p in placements) - left
    height = max(p.y + p.height for p in placements) - top
    columns: dict[float, float] = {}
    for placement in placements:
        columns[placement.x] = columns.get(placement.x, 0.0) + placement.height
    tallest = max(columns.values(), default=0.0)
    return {"width": width, "height": height, "wasted": max(height - tallest, 0.0)}


def _centred(placements: list[Placement], reference: str | None) -> list[Placement]:
    """The reference moved to the middle height of everything else, unless someone held it."""
    found = next((p for p in placements if p.code == reference), None)
    if found is None or len(placements) < 2:
        return sorted(placements, key=lambda p: p.code)
    others = [p for p in placements if p.code != reference]
    middle = (min(p.y for p in others) + max(p.y + p.height for p in others)) / 2
    shift = middle - (found.y + found.height / 2)
    moved = [
        p if p.held or p.code != reference else p.model_copy(update={"y": p.y + shift})
        for p in placements
    ]
    return sorted(moved, key=lambda p: p.code)


def arrange(
    system: ProductSystem,
    anchors: list[str],
    held: dict[str, tuple[float, float]],
    sides: Mapping[str, Side],
    amounts: Mapping[str, Mapping[uuid.UUID, float]] | None = None,
) -> list[Placement]:
    """Every card's place: columns measured from the anchors, ordered by median to start, then
    each column of two to six free cards tried in every order and kept when the drawing's score
    falls, or ties with a lower height. Packed at real heights, and centred on the anchor when
    there is exactly one.

    A card in `held` keeps the position it was given and the rest pack around it. `sides` puts
    each elementary flow of the system on its side, by the flow's native id. `amounts` are the
    scaled exchange amounts by card, so arrow labels are measured at their scaled width; None
    when the drawing is not scaled.
    """
    reference = anchors[0] if len(anchors) == 1 else None
    drawn = nodes(system)
    anatomy = {p.code: _anatomy(p, sides) for p in system.processes}
    for code in drawn:
        if code.startswith(LINKED):
            anatomy[code] = _linked_anatomy()
    sizes = {code: (a.width, a.height) for code, a in anatomy.items()}
    column_of = depths(system, anchors)
    consumers: dict[str, list[str]] = {}
    for code, providers in drawn.items():
        for provider in providers:
            consumers.setdefault(provider, []).append(code)
    deepest = max(column_of.values(), default=0)
    columns: dict[int, list[str]] = {}
    for code in drawn:
        columns.setdefault(column_of[code], []).append(code)

    def _place(orders: dict[int, list[str]]) -> list[Placement]:
        placements: list[Placement] = []
        for depth in sorted(orders):
            order = orders[depth]
            x = float(deepest - depth) * (CARD_WIDTH + COLUMN_GAP)
            taken = _held_spans(held, sizes, x)
            free = [code for code in order if code not in held]
            tops = _stack(free, sizes, taken)
            for code in order:
                spot = held.get(code)
                card = anatomy[code]
                placements.append(
                    Placement(
                        code=code,
                        x=spot[0] if spot else x,
                        y=spot[1] if spot else tops[code],
                        width=card.width,
                        height=card.height,
                        depth=depth,
                        shown_inputs=card.shown_inputs,
                        held=spot is not None,
                        inputs=card.inputs,
                        outputs=card.outputs,
                        output=card.output,
                    )
                )
        return _centred(placements, reference)

    orders: dict[int, list[str]] = {}
    previous: list[str] = []
    for depth in sorted(columns):
        orders[depth] = _ordered(sorted(columns[depth]), previous, consumers)
        previous = orders[depth]
    drawn_links = links(system)
    texts = link_texts(system, amounts)

    def measured(candidate: dict[int, list[str]]) -> tuple[int, float, list[Placement]]:
        placed = _place(candidate)
        found = troubles(placed, route(placed, drawn_links, texts))
        return score(found), bounds(placed)["height"], placed

    best = measured(orders)
    for _ in range(2):
        for depth in sorted(orders):
            free = [c for c in orders[depth] if c not in held]
            if len(free) < 2 or len(free) > MAX_PERMUTED:
                continue
            for order in permutations(free):
                candidate = {**orders, depth: [*order, *[c for c in orders[depth] if c in held]]}
                trial = measured(candidate)
                if trial[:2] < best[:2]:
                    best, orders = trial, candidate
    return best[2]
