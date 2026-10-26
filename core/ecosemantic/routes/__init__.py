"""Every arrow of a drawing as an orthogonal route: out of its provider to the right, on a
track in a column gap, over a lane clear of the cards when it crosses columns, and into the
row it feeds from the left."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.geometry import COLUMN_GAP, Link, LinkText, Placement

TRACK_MARGIN = 24.0
TRACK_SPACING = 12.0
TRACK_SHARE = 0.45
CHAR_WIDTH = 7.0
LABEL_PAD = 8.0
LABEL_HEIGHT = 16.0
LABEL_GAP = 6.0
LABEL_LIFT = 2.0
LANE_MARGIN = 12.0
LANE_SPACING = 12.0
LANE_TRIES = 64

Point = tuple[float, float]
Gap = tuple[float, float]
Lane = tuple[float, float, float, str]


class Label(BaseModel):
    """The box an arrow's quantity text occupies, and the texts it carries."""

    x: float
    y: float
    width: float
    height: float
    per_unit: str
    scaled: str | None
    formula: str | None


class Route(BaseModel):
    """One arrow's path as the page draws it, corner by corner."""

    provider: str
    consumer: str
    exchange_id: uuid.UUID
    points: list[Point]
    label: Label


def _source(card: Placement) -> Point:
    return card.x + card.width, card.y + card.output


def _target(card: Placement, exchange_id: uuid.UUID) -> Point:
    for port in card.inputs:
        if port.exchange_id == exchange_id:
            return card.x, card.y + port.y
    raise Invalid(f"card {card.code} has no input {exchange_id}")


def _gaps(cards: list[Placement]) -> list[Gap]:
    """The free x-intervals between the bands the cards cover, and one column gap beyond each
    outermost band."""
    bands: list[list[float]] = []
    for left, right in sorted((c.x, c.x + c.width) for c in cards):
        if bands and left <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], right)
        else:
            bands.append([left, right])
    found: list[Gap] = [(bands[0][0] - COLUMN_GAP, bands[0][0])]
    found += [(a[1], b[0]) for a, b in zip(bands, bands[1:], strict=False)]
    found.append((bands[-1][1], bands[-1][1] + COLUMN_GAP))
    return found


def _gap_after(x: float, gaps: list[Gap], cards: list[Placement]) -> Gap:
    right = max((c.x + c.width for c in cards if c.x <= x <= c.x + c.width), default=x)
    return next(g for g in gaps if g[0] >= right)


def _gap_before(x: float, gaps: list[Gap], cards: list[Placement]) -> Gap:
    left = min((c.x for c in cards if c.x <= x <= c.x + c.width), default=x)
    return next(g for g in reversed(gaps) if g[1] <= left)


def _free(y: float, low: float, high: float, provider: str, taken: list[Lane]) -> bool:
    return all(
        other == provider or abs(y - lane) >= LANE_SPACING or high <= start or end <= low
        for lane, start, end, other in taken
    )


def _lane(
    source: Point,
    target: Point,
    low: float,
    high: float,
    cards: list[Placement],
    provider: str,
    taken: list[Lane],
) -> float:
    """The height of a horizontal run from low to high: clear of every card it passes, of every
    other provider's lane over the same span, and as close to the source as that allows."""
    blocked = sorted(
        (c.y - LANE_MARGIN, c.y + c.height + LANE_MARGIN)
        for c in cards
        if c.x < high and low < c.x + c.width
    )
    merged: list[list[float]] = []
    for start, end in blocked:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    bounds = [float("-inf")] + [v for pair in merged for v in pair] + [float("inf")]
    best: tuple[float, float] | None = None
    for start, end in zip(bounds[::2], bounds[1::2], strict=True):
        base = min(max(source[1], start), end)
        for k in range(LANE_TRIES):
            found = next(
                (
                    y
                    for y in (base + k * LANE_SPACING, base - k * LANE_SPACING)
                    if start <= y <= end and _free(y, low, high, provider, taken)
                ),
                None,
            )
            if found is not None:
                cost = abs(found - source[1]) + abs(found - target[1])
                if best is None or cost < best[0]:
                    best = (cost, found)
                break
    if best is None:
        raise Invalid(f"no lane for an arrow from {provider}")
    return best[1]


def _simplified(points: list[Point]) -> list[Point]:
    found: list[Point] = []
    for point in points:
        if found and point == found[-1]:
            continue
        if len(found) >= 2:
            a, b = found[-2], found[-1]
            if (a[0] == b[0] == point[0]) or (a[1] == b[1] == point[1]):
                found[-1] = point
                continue
        found.append(point)
    return found


def _label(end: Point, text: LinkText) -> Label:
    width = CHAR_WIDTH * max(len(t) for t in text if t is not None) + LABEL_PAD
    return Label(
        x=end[0] - LABEL_GAP - width,
        y=end[1] - LABEL_LIFT - LABEL_HEIGHT,
        width=width,
        height=LABEL_HEIGHT,
        per_unit=text.per_unit,
        scaled=text.scaled,
        formula=text.formula,
    )


def route(
    placements: list[Placement],
    links: list[Link],
    texts: Mapping[uuid.UUID, LinkText],
) -> list[Route]:
    """Every link's route over these placements, deterministic for one arrangement, each with
    the box of its quantity text placed before the consumer."""
    if not placements:
        return []
    spots = {p.code: p for p in placements}
    for link in links:
        for code in (link.provider, link.consumer):
            if code not in spots:
                raise Invalid(f"no card {code} for an arrow of {link.exchange_id}")
    gaps = _gaps(placements)
    ordered = sorted(
        links,
        key=lambda k: (_source(spots[k.provider])[1], spots[k.consumer].x, str(k.exchange_id)),
    )
    plans: list[tuple[Link, Point, Point, Gap, Gap]] = []
    tracks: dict[Gap, list[str]] = {}
    for link in ordered:
        start = _source(spots[link.provider])
        end = _target(spots[link.consumer], link.exchange_id)
        out_gap = _gap_after(start[0], gaps, placements)
        in_gap = _gap_before(end[0], gaps, placements)
        for gap in (out_gap, in_gap):
            providers = tracks.setdefault(gap, [])
            if link.provider not in providers:
                providers.append(link.provider)
        plans.append((link, start, end, out_gap, in_gap))

    def track(gap: Gap, provider: str) -> float:
        providers = tracks[gap]
        width = gap[1] - gap[0]
        margin = min(TRACK_MARGIN, width / 4)
        span = TRACK_SHARE * width - margin
        spacing = min(TRACK_SPACING, span / max(len(providers) - 1, 1))
        return gap[0] + margin + spacing * providers.index(provider)

    taken: list[Lane] = []
    found: list[Route] = []
    for link, start, end, out_gap, in_gap in plans:
        if out_gap == in_gap:
            x = track(out_gap, link.provider)
            points = [start, (x, start[1]), (x, end[1]), end]
        else:
            x_out = track(out_gap, link.provider)
            x_in = track(in_gap, link.provider)
            low, high = min(x_out, x_in), max(x_out, x_in)
            lane = _lane(start, end, low, high, placements, link.provider, taken)
            taken.append((lane, low, high, link.provider))
            points = [start, (x_out, start[1]), (x_out, lane), (x_in, lane), (x_in, end[1]), end]
        if link.exchange_id not in texts:
            raise Invalid(f"no label texts for the arrow of exchange {link.exchange_id}")
        found.append(
            Route(
                provider=link.provider,
                consumer=link.consumer,
                exchange_id=link.exchange_id,
                points=_simplified(points),
                label=_label(end, texts[link.exchange_id]),
            )
        )
    return found
