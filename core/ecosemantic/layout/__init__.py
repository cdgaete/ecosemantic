"""Where a product system's processes are drawn: the size of a card, its distance from the
functional unit, and the arrangement the page and the tools both read."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping

from pydantic import BaseModel

from ecosemantic.geometry import (
    CARD_WIDTH,
    COLUMN_GAP,
    COLUMN_TOP,
    LINKED,
    ROW_GAP,
    Placement,
    Port,
    Region,
    SharedSupplier,
    StageRegions,
    card_size,
    folds,
    link_texts,
    linked_card,
    links,
    ports,
    rows,
)
from ecosemantic.model.entities import Process, ProductSystem
from ecosemantic.model.stages import stage_of, stage_order
from ecosemantic.ports.types import Side
from ecosemantic.routes import route
from ecosemantic.troubles import score, troubles

EVALUATIONS = 400_000
REGION_PAD = 24.0
GROWTH = 1.25


def evaluation_budget(arrows: int) -> int:
    """How many drawings an arrangement of this many arrows may measure: fewer as the arrows grow,
    so what is drawn follows the graph and not the machine's speed. A drawing of no arrow counts as
    one arrow, the division it makes undefined otherwise."""
    return max(EVALUATIONS // max(arrows, 1) ** 2, 1)


class Evaluations(BaseModel):
    """The drawings one arrangement may measure and how many it has measured, shared by the two
    searches so the search spends one count wherever it runs."""

    limit: int
    used: int = 0

    def take(self) -> bool:
        """Whether one more drawing may be measured, which it then counts."""
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    def spent(self) -> bool:
        """Whether the budget is used up."""
        return self.used >= self.limit


class _Anatomy(BaseModel):
    """What a card's contents fix about it, whichever place the search tries it at: its size, the
    rows it shows on each side with their anchors, and the rows the fold hides."""

    width: float
    height: float
    shown_inputs: int
    shown_outputs: int
    folded_inputs: int
    folded_outputs: int
    inputs: list[Port]
    outputs: list[uuid.UUID]
    output: float


def _anatomy(
    process: Process,
    sides: Mapping[str, Side],
    arrows: Collection[uuid.UUID],
    *,
    expanded: bool,
) -> _Anatomy:
    width, height = card_size(process, sides, arrows, expanded=expanded)
    found, output = ports(process, sides, arrows, expanded=expanded)
    inputs, outputs = folds(process, sides, arrows, expanded=expanded)
    return _Anatomy(
        width=width,
        height=height,
        shown_inputs=inputs.shown,
        shown_outputs=outputs.shown,
        folded_inputs=inputs.folded,
        folded_outputs=outputs.folded,
        inputs=found,
        outputs=[e.id for e in rows(process, sides, arrows)[1]],
        output=output,
    )


def _linked_anatomy() -> _Anatomy:
    width, height, output = linked_card()
    return _Anatomy(
        width=width,
        height=height,
        shown_inputs=0,
        shown_outputs=0,
        folded_inputs=0,
        folded_outputs=0,
        inputs=[],
        outputs=[],
        output=output,
    )


def nodes(system: ProductSystem) -> dict[str, list[str]]:
    """Every card of a drawing with the cards that feed it: the providers `links` gives each
    process once, in its order, and each linked system once, which nothing here feeds."""
    found: dict[str, list[str]] = {p.code: [] for p in system.processes}
    for arrow in links(system):
        providers = found[arrow.consumer]
        if arrow.provider not in providers:
            providers.append(arrow.provider)
        found.setdefault(arrow.provider, [])
    return found


def card_stages(system: ProductSystem) -> dict[str, str | None]:
    """The stage every card of a drawing belongs to: a process's own, and a linked system's the
    one its consuming processes share, None when they share none or hold several."""
    found: dict[str, str | None] = {p.code: stage_of(p) for p in system.processes}
    consumers: dict[str, list[str]] = {}
    for arrow in links(system):
        consumers.setdefault(arrow.provider, []).append(arrow.consumer)
    by_code = {p.code: p for p in system.processes}
    for provider, taking in consumers.items():
        if provider in found:
            continue
        held = {stage_of(by_code[code]) for code in taking}
        found[provider] = held.pop() if len(held) == 1 else None
    return found


def _padded(cards: list[Placement]) -> Region:
    """One region around these cards, padded by `REGION_PAD` on every side."""
    left = min(card.x for card in cards)
    top = min(card.y for card in cards)
    right = max(card.x + card.width for card in cards)
    bottom = max(card.y + card.height for card in cards)
    return Region(
        x=left - REGION_PAD,
        y=top - REGION_PAD,
        width=right - left + 2 * REGION_PAD,
        height=bottom - top + 2 * REGION_PAD,
    )


def _within(card: Placement, left: float, right: float) -> bool:
    """Whether the card's rectangle lies within these left and right edges."""
    return left <= card.x and card.x + card.width <= right


def stage_regions(system: ProductSystem, placements: list[Placement]) -> list[StageRegions]:
    """Each stage that holds a card, in `stage_order`, with its cards in the order the drawing
    places them and the regions that hold them: one around the cards nobody held and the held
    cards within the columns those cards span, and one around each held card outside them. A
    stage whose cards are all held answers one region per card."""
    stages = card_stages(system)
    by_stage: dict[str, list[Placement]] = {}
    for placement in placements:
        stage = stages[placement.code]
        if stage is not None:
            by_stage.setdefault(stage, []).append(placement)
    found: list[StageRegions] = []
    for stage in stage_order(system):
        cards = by_stage.get(stage)
        if cards is None:
            continue
        free = [card for card in cards if not card.held]
        regions: list[Region] = []
        if not free:
            regions = [_padded([card]) for card in cards]
        else:
            left = min(card.x for card in free)
            right = max(card.x + card.width for card in free)
            inside = [card for card in cards if not card.held or _within(card, left, right)]
            regions.append(_padded(inside))
            regions += [
                _padded([card]) for card in cards if card.held and not _within(card, left, right)
            ]
        found.append(
            StageRegions(stage=stage, codes=[card.code for card in cards], regions=regions)
        )
    return found


def shared_suppliers(system: ProductSystem) -> list[SharedSupplier]:
    """Each card of no stage whose consumers hold two or more stages, in card order, with how many
    processes it feeds and how many stages those processes hold."""
    stages = card_stages(system)
    consumers: dict[str, list[str]] = {}
    for arrow in links(system):
        consumers.setdefault(arrow.provider, []).append(arrow.consumer)
    found: list[SharedSupplier] = []
    for code, stage in stages.items():
        if stage is not None:
            continue
        fed = consumers.get(code, [])
        held = {stages[consumer] for consumer in fed} - {None}
        if len(held) < 2:
            continue
        found.append(SharedSupplier(code=code, processes=len(set(fed)), stages=len(held)))
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


def _stage_bands(system: ProductSystem, anchors: list[str]) -> dict[str, int]:
    """Each stage's band, counted from the right: the functional unit's stage holds band zero and
    every next band to its left is the stage carrying the fewest arrows into the stages still
    unplaced, ties by `stage_order`."""
    order = stage_order(system)
    stages = card_stages(system)
    into: dict[tuple[str, str], int] = {}
    for arrow in links(system):
        provider, consumer = stages.get(arrow.provider), stages.get(arrow.consumer)
        if provider is None or consumer is None or provider == consumer:
            continue
        into[provider, consumer] = into.get((provider, consumer), 0) + 1
    bands: dict[str, int] = {}
    remaining = set(order)
    unit = next((stages[code] for code in anchors if stages.get(code) is not None), None)
    if unit is not None:
        bands[unit] = 0
        remaining.discard(unit)

    def into_rest(stage: str) -> int:
        return sum(n for (a, b), n in into.items() if a == stage and b in remaining)

    while remaining:
        chosen = min(remaining, key=lambda stage: (into_rest(stage), order.index(stage)))
        remaining.discard(chosen)
        bands[chosen] = len(bands)
    return bands


def _columns(
    system: ProductSystem, distances: dict[str, int], anchors: list[str]
) -> tuple[dict[str, int], int]:
    """Each card's column and how many columns the drawing takes: the distances themselves when
    no card carries a stage, and otherwise one band of columns per stage, from the bands
    `_stage_bands` gives, nearest the functional unit first, and the cards of no stage in the
    leftmost. Inside a band a card's column is the rank of its distance among the band's cards,
    nearest first."""
    stages = card_stages(system)
    if all(stage is None for stage in stages.values()):
        return distances, max(distances.values(), default=0) + 1
    bands = _stage_bands(system, anchors)
    leftmost = len(bands)
    in_band: dict[int, list[str]] = {}
    for code, stage in stages.items():
        in_band.setdefault(leftmost if stage is None else bands[stage], []).append(code)
    columns: dict[str, int] = {}
    total = 0
    for band in sorted(in_band):
        found = sorted({distances[code] for code in in_band[band]})
        for code in in_band[band]:
            columns[code] = total + found.index(distances[code])
        total += len(found)
    return columns, total


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


def _meets(a: Placement, b: Placement) -> bool:
    """Whether two cards' rectangles overlap horizontally and come nearer vertically than the row
    gap, which is the closeness the stack packs a card around."""
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height + ROW_GAP
        and b.y < a.y + a.height + ROW_GAP
    )


def _centred(placements: list[Placement], reference: str | None) -> list[Placement]:
    """The reference moved to the middle height of everything else, unless someone held it or that
    height would meet a card someone held."""
    found = next((p for p in placements if p.code == reference), None)
    if found is None or len(placements) < 2:
        return sorted(placements, key=lambda p: p.code)
    others = [p for p in placements if p.code != reference]
    middle = (min(p.y for p in others) + max(p.y + p.height for p in others)) / 2
    shift = middle - (found.y + found.height / 2)
    centre = found.model_copy(update={"y": found.y + shift})
    if any(_meets(centre, p) for p in placements if p.held and p.code != reference):
        return sorted(placements, key=lambda p: p.code)
    moved = [p if p.held or p.code != reference else centre for p in placements]
    return sorted(moved, key=lambda p: p.code)


def arrange(
    system: ProductSystem,
    anchors: list[str],
    held: dict[str, tuple[float, float]],
    sides: Mapping[str, Side],
    amounts: Mapping[str, Mapping[uuid.UUID, float]] | None = None,
    expanded: Collection[str] = (),
    budget: Evaluations | None = None,
) -> list[Placement]:
    """Every card's place: columns measured from the anchors, or one band of columns per stage
    when any card carries one, ordered by median to start, then each column's adjacent free cards
    swapped while a swap lowers the drawing's score, or its height at an equal score, then each
    free card moved in its column to where one of its arrows runs straight or it sits beside a
    neighbour while that lowers the same pair. Packed at real heights, and centred on the anchor
    when there is exactly one.

    Both searches share `budget`'s evaluations, `evaluation_budget` of the drawing's arrows when
    it is None, and answer the best drawing they find, the packed one on a tie. A card in `held`
    keeps the position it was given and neither search moves it, and the rest pack around it.
    `sides` puts each elementary flow of the system on its side, by the flow's native id.
    `amounts` are the scaled exchange amounts by card, so arrow labels are measured at their
    scaled width; None when the drawing is not scaled. `expanded` names the cards whose rows the
    page shows in full; a card it does not name folds its rows past `FOLD_AFTER` on each side.
    """
    reference = anchors[0] if len(anchors) == 1 else None
    drawn = nodes(system)
    drawn_links = links(system)
    arrows = {link.exchange_id for link in drawn_links}
    anatomy = {
        p.code: _anatomy(p, sides, arrows, expanded=p.code in expanded) for p in system.processes
    }
    for code in drawn:
        if code.startswith(LINKED):
            anatomy[code] = _linked_anatomy()
    sizes = {code: (a.width, a.height) for code, a in anatomy.items()}
    distances = depths(system, anchors)
    column_of, total = _columns(system, distances, anchors)
    consumers: dict[str, list[str]] = {}
    for code, providers in drawn.items():
        for provider in providers:
            consumers.setdefault(provider, []).append(code)
    columns: dict[int, list[str]] = {}
    for code in drawn:
        columns.setdefault(column_of[code], []).append(code)
    pinned = {code: at for code, at in held.items() if code in drawn}
    spent = Evaluations(limit=evaluation_budget(len(drawn_links))) if budget is None else budget

    def _pitch(column: int) -> float:
        return float(total - 1 - column) * (CARD_WIDTH + COLUMN_GAP)

    def _card(code: str, x: float, y: float, *, at_hold: bool) -> Placement:
        card = anatomy[code]
        return Placement(
            code=code,
            x=x,
            y=y,
            width=card.width,
            height=card.height,
            depth=distances[code],
            shown_inputs=card.shown_inputs,
            shown_outputs=card.shown_outputs,
            folded_inputs=card.folded_inputs,
            folded_outputs=card.folded_outputs,
            held=at_hold,
            inputs=card.inputs,
            outputs=card.outputs,
            output=card.output,
        )

    def _place(orders: Mapping[int, list[str]], shifts: Mapping[str, float]) -> list[Placement]:
        placed: list[Placement] = []
        for column in sorted(orders):
            x = _pitch(column)
            tops = _stack(orders[column], sizes, _held_spans(pinned, sizes, x))
            for code in orders[column]:
                placed.append(_card(code, x, tops[code] + shifts.get(code, 0.0), at_hold=False))
        for code, (left, top) in pinned.items():
            placed.append(_card(code, left, top, at_hold=True))
        return _centred(placed, reference)

    orders: dict[int, list[str]] = {}
    previous: list[str] = []
    for column in sorted(columns):
        ordered = _ordered(sorted(columns[column]), previous, consumers)
        orders[column] = [code for code in ordered if code not in pinned]
        previous = ordered
    texts = link_texts(system, amounts)

    def scored(
        candidate: Mapping[int, list[str]], shifts: Mapping[str, float]
    ) -> tuple[int, float, list[Placement]]:
        placed = _place(candidate, shifts)
        found = troubles(placed, route(placed, drawn_links, texts))
        return score(found), bounds(placed)["height"], placed

    def measured(
        candidate: Mapping[int, list[str]], shifts: Mapping[str, float]
    ) -> tuple[int, float, list[Placement]] | None:
        """`scored` of one drawing, counted against the budget; None once the budget is spent."""
        if not spent.take():
            return None
        return scored(candidate, shifts)

    best = scored(orders, {})
    while not spent.spent():
        swapped = False
        for column in sorted(orders):
            for at in range(len(orders[column]) - 1):
                if spent.spent():
                    break
                order = list(orders[column])
                order[at], order[at + 1] = order[at + 1], order[at]
                trial = measured({**orders, column: order}, {})
                if trial is not None and trial[:2] < best[:2]:
                    best = trial
                    orders = {**orders, column: order}
                    swapped = True
        if not swapped:
            break

    def _spread(placed: list[Placement], code: str | None = None, y: float = 0.0) -> float:
        """How tall the free cards reach, with the card `code` at height `y`."""
        at = [(y if card.code == code else card.y) for card in placed if not card.held]
        end = [
            (y + card.height if card.code == code else card.y + card.height)
            for card in placed
            if not card.held
        ]
        return max(end) - min(at) if at else 0.0

    tallest = GROWTH * _spread(best[2])
    leaving: dict[str, list[tuple[str, uuid.UUID]]] = {}
    entering: dict[str, list[tuple[str, uuid.UUID]]] = {}
    for link in drawn_links:
        leaving.setdefault(link.provider, []).append((link.consumer, link.exchange_id))
        entering.setdefault(link.consumer, []).append((link.provider, link.exchange_id))
    ported = {
        (code, port.exchange_id): port.y for code, card in anatomy.items() for port in card.inputs
    }

    def _straight(code: str, now: Mapping[str, Placement]) -> list[float]:
        """The heights at which an arrow of this card leaves its output at the height of the row it
        feeds, nearest this card's place first."""
        found: list[float] = []
        for consumer, exchange in leaving.get(code, []):
            found.append(now[consumer].y + ported[consumer, exchange] - anatomy[code].output)
        for provider, exchange in entering.get(code, []):
            found.append(now[provider].y + anatomy[provider].output - ported[code, exchange])
        here = now[code].y
        return sorted({y for y in found if y != here}, key=lambda y: abs(y - here))

    def _beside(code: str, now: Mapping[str, Placement], same: Collection[str]) -> list[float]:
        """The heights at which this card sits directly above or below another card of its column,
        nearest this card's place first."""
        here = now[code].y
        height = anatomy[code].height
        found = [
            y
            for other in same
            if other != code
            for y in (now[other].y - height - ROW_GAP, now[other].y + now[other].height + ROW_GAP)
        ]
        return sorted({y for y in found if y != here}, key=lambda y: abs(y - here))

    shifts: dict[str, float] = {}
    moving = True
    while moving and not spent.spent():
        moving = False
        for column in sorted(orders):
            same = [
                *orders[column],
                *(code for code, (left, _) in pinned.items() if left == _pitch(column)),
            ]
            for code in orders[column]:
                if code == reference or spent.spent():
                    continue
                now = {card.code: card for card in best[2]}
                here = now[code]
                for target in [*_straight(code, now), *_beside(code, now, same)]:
                    if spent.spent():
                        break
                    moved = here.model_copy(update={"y": target})
                    if any(_meets(moved, card) for card in best[2] if card.code != code):
                        continue
                    if _spread(best[2], code, target) > tallest:
                        continue
                    shift = shifts.get(code, 0.0) + target - here.y
                    trial = measured(orders, {**shifts, code: shift})
                    if trial is None:
                        break
                    if trial[:2] < best[:2]:
                        best = trial
                        shifts = {**shifts, code: shift}
                        moving = True
                        break
    return best[2]
