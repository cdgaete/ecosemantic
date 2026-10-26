"""What is wrong with a drawing, measured on its cards and on the routes the page draws, each
named once, and a score that weighs them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ecosemantic.geometry import Placement
from ecosemantic.routes import Label, Point, Route

TroubleKind = Literal[
    "cards_overlap",
    "edge_through_card",
    "edges_overlap",
    "edge_backwards",
    "edges_cross",
    "label_overlap",
]
WEIGHTS: dict[TroubleKind, int] = {
    "cards_overlap": 10,
    "edge_through_card": 5,
    "edges_overlap": 3,
    "edge_backwards": 2,
    "edges_cross": 1,
    "label_overlap": 2,
}
Segment = tuple[Point, Point]


class Trouble(BaseModel):
    """One thing wrong with the drawing, with the cards it concerns."""

    kind: TroubleKind
    message: str
    codes: list[str]


def _segments(route: Route) -> list[Segment]:
    return list(zip(route.points, route.points[1:], strict=False))


def _name(route: Route) -> str:
    return f"{route.provider} to {route.consumer}"


def passes_through(segment: Segment, card: Placement) -> bool:
    (x0, y0), (x1, y1) = segment
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    inside_x = max(left, card.x) < min(right, card.x + card.width)
    inside_y = max(top, card.y) < min(bottom, card.y + card.height)
    if y0 == y1:
        return card.y < y0 < card.y + card.height and inside_x
    return card.x < x0 < card.x + card.width and inside_y


def _box(label: Label) -> Placement:
    return Placement(
        code="label",
        x=label.x,
        y=label.y,
        width=label.width,
        height=label.height,
        depth=0,
        output=0.0,
    )


def _meets(a: Placement, b: Placement) -> bool:
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height
        and b.y < a.y + a.height
    )


def _overlap(a: Segment, b: Segment) -> bool:
    (ax0, ay0), (ax1, ay1) = a
    (bx0, by0), (bx1, by1) = b
    if ay0 == ay1 == by0 == by1:
        return max(min(ax0, ax1), min(bx0, bx1)) < min(max(ax0, ax1), max(bx0, bx1))
    if ax0 == ax1 == bx0 == bx1:
        return max(min(ay0, ay1), min(by0, by1)) < min(max(ay0, ay1), max(by0, by1))
    return False


def _cross(a: Segment, b: Segment) -> bool:
    horizontal, vertical = (a, b) if a[0][1] == a[1][1] else (b, a)
    (hx0, hy), (hx1, _) = horizontal
    (vx, vy0), (_, vy1) = vertical
    if horizontal[0][1] != horizontal[1][1] or vertical[0][0] != vertical[1][0]:
        return False
    return min(hx0, hx1) < vx < max(hx0, hx1) and min(vy0, vy1) < hy < max(vy0, vy1)


def troubles(placements: list[Placement], routes: list[Route]) -> list[Trouble]:
    """Cards that overlap, arrows over a card, arrows of different providers on one line or
    crossing, and arrows pointing backwards."""
    found: list[Trouble] = []
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            if a.x < b.x + b.width and b.x < a.x + a.width:
                if a.y < b.y + b.height and b.y < a.y + a.height:
                    found.append(
                        Trouble(
                            kind="cards_overlap",
                            message=f"{a.code} and {b.code} overlap",
                            codes=[a.code, b.code],
                        )
                    )
    spots = {p.code: p for p in placements}
    for r in routes:
        for c in placements:
            if any(passes_through(s, c) for s in _segments(r)):
                found.append(
                    Trouble(
                        kind="edge_through_card",
                        message=f"the arrow {_name(r)} runs through {c.code}",
                        codes=[r.provider, r.consumer, c.code],
                    )
                )
        if r.provider != r.consumer and spots[r.consumer].x <= spots[r.provider].x:
            found.append(
                Trouble(
                    kind="edge_backwards",
                    message=f"the arrow {_name(r)} points backwards",
                    codes=[r.provider, r.consumer],
                )
            )
    for i, a in enumerate(routes):
        for b in routes[i + 1 :]:
            if a.provider == b.provider:
                continue
            pairs = [(s, t) for s in _segments(a) for t in _segments(b)]
            if any(_overlap(s, t) for s, t in pairs):
                found.append(
                    Trouble(
                        kind="edges_overlap",
                        message=f"the arrows {_name(a)} and {_name(b)} run on one line",
                        codes=[a.provider, a.consumer, b.provider, b.consumer],
                    )
                )
            for _ in [p for p in pairs if _cross(*p)]:
                found.append(
                    Trouble(
                        kind="edges_cross",
                        message=f"the arrows {_name(a)} and {_name(b)} cross",
                        codes=[a.provider, a.consumer, b.provider, b.consumer],
                    )
                )
    boxes = [_box(r.label) for r in routes]
    for i, r in enumerate(routes):
        for c in placements:
            if _meets(boxes[i], c):
                found.append(
                    Trouble(
                        kind="label_overlap",
                        message=f"the label of the arrow {_name(r)} covers {c.code}",
                        codes=[r.provider, r.consumer, c.code],
                    )
                )
        for j, other in enumerate(routes):
            if j > i and _meets(boxes[i], boxes[j]):
                found.append(
                    Trouble(
                        kind="label_overlap",
                        message=f"the labels of {_name(r)} and {_name(other)} overlap",
                        codes=[r.provider, r.consumer, other.provider, other.consumer],
                    )
                )
            if j != i and other.provider != r.provider:
                if any(passes_through(s, boxes[i]) for s in _segments(other)):
                    found.append(
                        Trouble(
                            kind="label_overlap",
                            message=f"the arrow {_name(other)} crosses the label of {_name(r)}",
                            codes=[r.provider, r.consumer, other.provider, other.consumer],
                        )
                    )
    return found


def score(found: list[Trouble]) -> int:
    """The weighted count of what is wrong; zero is a drawing with nothing wrong."""
    return sum(WEIGHTS[t.kind] for t in found)
