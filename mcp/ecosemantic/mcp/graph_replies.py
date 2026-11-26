"""The reply shapes the graph tools answer: one page of a list with its total, the summary a call
records, a card's scaled amounts, the drawing read compactly or focused on one of its parts, and
what a write changed."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, PrivateAttr

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.geometry import Placement
from ecosemantic.model.entities import ActorKind
from ecosemantic.model.summary import SUMMARY_ITEMS, Summary, SummaryItem
from ecosemantic.routes import Point, Route
from ecosemantic.scaling import ScaledRow
from ecosemantic.troubles import WEIGHTS, Trouble, TroubleKind

if TYPE_CHECKING:
    from ecosemantic.mcp.graph import Arrangement

T = TypeVar("T")

AMOUNT_ACTIVITIES = 30
AMOUNT_ROWS = 15
READ_CARDS = 10
READ_ISSUES = 3
FOCUS_ROUTES = 5
FOCUS_ISSUES = 3
WRITE_CARDS = 6
WRITE_ISSUES = 2


class Bounded(BaseModel, Generic[T]):
    """One page of a list: its items, how many the whole list holds, and how many follow this
    page."""

    items: list[T]
    total: int
    omitted: int


def bounded(items: Sequence[T], page: int, size: int) -> Bounded[T]:
    """The page `page` of `items`, counted in steps of `size`, with the list's total and the items
    that follow it."""
    start = page * size
    window = list(items[start : start + size])
    return Bounded[T](
        items=window, total=len(items), omitted=max(0, len(items) - start - len(window))
    )


def cursor_after(page: int, *lists: Bounded[Any]) -> str | None:
    """The cursor of the page after `page` while any of `lists` continues, and nothing once every
    one of them is read."""
    return str(page + 1) if any(entry.omitted > 0 for entry in lists) else None


def placed_summary(codes: Sequence[str]) -> Summary | None:
    """The cards someone placed, counted, with the first of their codes in order; nothing while
    there are no codes."""
    ordered = sorted(codes)
    if not ordered:
        return None
    return Summary(
        count=len(ordered),
        more=len(ordered) > SUMMARY_ITEMS,
        noun="cards placed",
        items=[SummaryItem(label=code) for code in ordered[:SUMMARY_ITEMS]],
    )


class RecordsPlaced(BaseModel):
    """A reply whose call records the cards someone placed, as every detail of the graph tools
    records them."""

    _held: list[str] = PrivateAttr(default_factory=list)

    def placing(self, codes: Sequence[str]) -> Self:
        """The answer counting `codes` as the cards someone placed, for the summary a call
        records."""
        self._held = sorted(codes)
        return self

    def summarise(self) -> Summary | None:
        """The cards someone placed, counted, with the first of their codes in order."""
        return placed_summary(self._held)


class CardActivity(BaseModel):
    """How many times one card's process runs."""

    code: str
    activity: float


AmountRow = ScaledRow


class CardAmounts(BaseModel):
    """One card's activity and one page of its scaled exchanges, in the process's own order."""

    code: str
    activity: float
    rows: Bounded[AmountRow]


class Amounts(RecordsPlaced):
    """Every card's activity, or one card's activity and rows of scaled amounts, in pages, as the
    drawing scales them; `scaling` names why nothing is scaled. Nothing here is placed, routed or
    scored."""

    kind: Literal["amounts"] = "amounts"
    variant: str | None = None
    scaling: str | None = None
    activities: Bounded[CardActivity] | None = None
    card: CardAmounts | None = None
    next_cursor: str | None = None


class CardRow(BaseModel):
    """Where one card is drawn, how big it is, whether someone holds it there and who."""

    code: str
    x: float
    y: float
    width: float
    height: float
    held: bool
    placed_by: ActorKind | None


class Issue(BaseModel):
    """One thing wrong with the drawing, with the cards it concerns and the exchanges of the
    arrows it concerns."""

    kind: TroubleKind
    codes: list[str]
    exchange_ids: list[uuid.UUID]


class Holds(BaseModel):
    """How many of the cards the drawing holds each placer put there; a hold that records no
    placer is counted `unrecorded`."""

    person: int
    agent: int
    service: int
    unrecorded: int


class RouteSummary(BaseModel):
    """One arrow as a caller reads it: the exchange it carries, the two cards it joins, where it
    starts and ends, and the text the drawing shows beside it."""

    exchange_id: uuid.UUID
    provider: str
    consumer: str
    first: Point
    last: Point
    label: str


class CompactRead(RecordsPlaced):
    """What a drawing holds, counted and in pages: its score, bounds and scaling, how many
    troubles of each kind it carries, how many cards each placer holds, then its cards and its
    issues, the heaviest issue first."""

    kind: Literal["compact"] = "compact"
    variant: str | None = None
    score: int
    bounds: dict[str, float]
    scaling: str | None = None
    troubles: dict[TroubleKind, int]
    holds: Holds
    cards: Bounded[CardRow]
    issues: Bounded[Issue]
    next_cursor: str | None = None


class Focus(RecordsPlaced):
    """One card or one arrow of a drawing, with the cards it draws, the arrows it carries and the
    issues that concern it, in pages."""

    kind: Literal["focus"] = "focus"
    variant: str | None = None
    cards: list[CardRow]
    routes: Bounded[RouteSummary]
    issues: Bounded[Issue]
    next_cursor: str | None = None


class CardState(BaseModel):
    """Where one card is drawn, whether someone holds it there and who."""

    x: float
    y: float
    held: bool
    placed_by: ActorKind | None


class ChangedCard(BaseModel):
    """One card whose place, hold or placer differs between the two drawings."""

    code: str
    before: CardState
    after: CardState


class CompactWrite(RecordsPlaced):
    """What a write changed: whether it saved, the score before and after, how many troubles of
    each kind the drawing now carries, the changed cards with their state on both sides, and the
    issues the write added and resolved, each in one page. Nothing of what came before a write
    that read no stored layout."""

    kind: Literal["write"] = "write"
    saved: bool
    variant: str | None = None
    score_before: int | None = None
    score_after: int
    troubles: dict[TroubleKind, int]
    changed: Bounded[ChangedCard] | None = None
    added: Bounded[Issue] | None = None
    resolved: Bounded[Issue] | None = None


def _row(card: Placement) -> CardRow:
    return CardRow(
        code=card.code,
        x=card.x,
        y=card.y,
        width=card.width,
        height=card.height,
        held=card.held,
        placed_by=card.placed_by,
    )


def _issue(trouble: Trouble) -> Issue:
    return Issue(
        kind=trouble.kind, codes=list(trouble.codes), exchange_ids=list(trouble.exchange_ids)
    )


def _heaviest(troubles: Sequence[Trouble]) -> list[Issue]:
    """`troubles` as issues, the heaviest first by its kind's weight, ties in their own order."""
    return [_issue(trouble) for trouble in sorted(troubles, key=lambda t: -WEIGHTS[t.kind])]


def _state(card: Placement) -> CardState:
    return CardState(x=card.x, y=card.y, held=card.held, placed_by=card.placed_by)


def _changed(before: Arrangement, after: Arrangement, named: Sequence[str]) -> list[ChangedCard]:
    """The cards whose state differs between `before` and `after`, the cards `named` first in their
    order and the rest in `after`'s drawing order."""
    states = {card.code: _state(card) for card in before.cards}
    moved = {
        card.code: ChangedCard(code=card.code, before=states[card.code], after=_state(card))
        for card in after.cards
        if states[card.code] != _state(card)
    }
    first = [moved[code] for code in dict.fromkeys(named) if code in moved]
    taken = {card.code for card in first}
    return first + [moved[card.code] for card in after.cards if card.code in moved.keys() - taken]


def _key(trouble: Trouble) -> tuple[TroubleKind, tuple[str, ...], tuple[uuid.UUID, ...]]:
    """What tells one trouble from another: its kind, the cards it concerns and their exchanges."""
    return (trouble.kind, tuple(trouble.codes), tuple(trouble.exchange_ids))


def _excess(mine: Sequence[Trouble], theirs: Sequence[Trouble]) -> list[Trouble]:
    """The troubles `mine` carries beyond `theirs`, counted with multiplicity."""
    surplus = Counter(_key(trouble) for trouble in theirs)
    found: list[Trouble] = []
    for trouble in mine:
        key = _key(trouble)
        if surplus[key] > 0:
            surplus[key] -= 1
        else:
            found.append(trouble)
    return found


def _counts(troubles: Sequence[Trouble]) -> dict[TroubleKind, int]:
    """How many troubles of each kind `troubles` holds, for the kinds it holds."""
    counts: dict[TroubleKind, int] = {}
    for trouble in troubles:
        counts[trouble.kind] = counts.get(trouble.kind, 0) + 1
    return counts


def _holds(cards: Sequence[Placement]) -> Holds:
    """How many of `cards` each placer holds."""
    counted = {"person": 0, "agent": 0, "service": 0, "unrecorded": 0}
    for card in cards:
        if not card.held:
            continue
        placer = card.placed_by
        counted["unrecorded" if placer is None else placer] += 1
    return Holds(**counted)


def _label(route: Route, *, scaled: bool) -> str:
    """The text the drawing shows beside `route`'s head: its scaled quantity when the drawing is
    scaled, its per-unit quantity otherwise."""
    if not scaled:
        return route.label.per_unit
    text = route.label.scaled
    if text is None:
        raise Invalid(
            f"a drawing scaled to its amounts carries no scaled text for exchange "
            f"{route.exchange_id}"
        )
    return text


def _summary(route: Route, *, scaled: bool) -> RouteSummary:
    return RouteSummary(
        exchange_id=route.exchange_id,
        provider=route.provider,
        consumer=route.consumer,
        first=route.points[0],
        last=route.points[-1],
        label=_label(route, scaled=scaled),
    )


def compact_read(arrangement: Arrangement, variant: str | None, page: int) -> CompactRead:
    """One page of what `arrangement` holds: its score, bounds and scaling, the kinds of trouble
    it carries, the cards each placer holds, and a page of its cards and of its issues, the
    heaviest first."""
    cards = bounded([_row(card) for card in arrangement.cards], page, READ_CARDS)
    issues = bounded(_heaviest(arrangement.troubles), page, READ_ISSUES)
    return CompactRead(
        variant=variant,
        score=arrangement.score,
        bounds=arrangement.bounds,
        scaling=arrangement.scaling,
        troubles=_counts(arrangement.troubles),
        holds=_holds(arrangement.cards),
        cards=cards,
        issues=issues,
        next_cursor=cursor_after(page, cards, issues),
    )


def focus(
    arrangement: Arrangement,
    variant: str | None,
    page: int,
    *,
    card: str | None,
    exchange_id: uuid.UUID | None,
) -> Focus:
    """`card`'s own row with every arrow it carries and every issue whose codes name it, or the
    arrow of `exchange_id` with the rows of its two cards and every issue that names it, each
    list in a page. NotFound names a card the drawing does not draw or an exchange it routes no
    arrow of."""
    if (card is None) == (exchange_id is None):
        raise Invalid("a focus names a card or an exchange, and not both")
    scaled = arrangement.scaling is None
    rows = {card.code: _row(card) for card in arrangement.cards}
    if card is not None:
        if card not in rows:
            raise NotFound(f"this drawing has no card {card!r}: name a code it draws")
        joined = [route for route in arrangement.edges if card in (route.provider, route.consumer)]
        carried = [trouble for trouble in arrangement.troubles if card in trouble.codes]
        shown = [rows[card]]
    else:
        route = next((each for each in arrangement.edges if each.exchange_id == exchange_id), None)
        if route is None:
            raise NotFound(
                f"this drawing routes no arrow of exchange {exchange_id}: name an exchange it draws"
            )
        joined = [route]
        carried = [
            trouble for trouble in arrangement.troubles if exchange_id in trouble.exchange_ids
        ]
        shown = [rows[route.provider], rows[route.consumer]]
    routes = bounded([_summary(route, scaled=scaled) for route in joined], page, FOCUS_ROUTES)
    issues = bounded(_heaviest(carried), page, FOCUS_ISSUES)
    return Focus(
        variant=variant,
        cards=shown,
        routes=routes,
        issues=issues,
        next_cursor=cursor_after(page, routes, issues),
    )


def compact_write(
    before: Arrangement | None,
    after: Arrangement,
    variant: str | None,
    *,
    saved: bool,
    named: Sequence[str],
) -> CompactWrite:
    """What writing `after` over `before` changed: whether it saved, the score on both sides, how
    many troubles of each kind the drawing now carries, and the first page of the changed cards,
    the cards `named` first, and of the issues it added and resolved, the heaviest first. Nothing
    compares without a `before`."""
    if before is None:
        return CompactWrite(
            saved=saved, variant=variant, score_after=after.score, troubles=_counts(after.troubles)
        )
    return CompactWrite(
        saved=saved,
        variant=variant,
        score_before=before.score,
        score_after=after.score,
        troubles=_counts(after.troubles),
        changed=bounded(_changed(before, after, named), 0, WRITE_CARDS),
        added=bounded(_heaviest(_excess(after.troubles, before.troubles)), 0, WRITE_ISSUES),
        resolved=bounded(_heaviest(_excess(before.troubles, after.troubles)), 0, WRITE_ISSUES),
    )
