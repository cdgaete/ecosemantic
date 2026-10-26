from __future__ import annotations

import uuid

import pytest

from ecosemantic.errors import Invalid
from ecosemantic.geometry import Link, LinkText, Placement, Port
from ecosemantic.routes import LABEL_GAP, LABEL_HEIGHT, LABEL_LIFT, Route
from ecosemantic.routes import route as routed


def route(placements: list[Placement], links: list[Link]) -> list[Route]:
    return routed(
        placements, links, {k.exchange_id: LinkText("1 kg", "12 kg", None) for k in links}
    )


def card(code: str, x: float, y: float, height: float = 120.0, ports: int = 1) -> Placement:
    return Placement(
        code=code,
        x=x,
        y=y,
        width=300.0,
        height=height,
        depth=0,
        inputs=[
            Port(exchange_id=uuid.uuid5(uuid.NAMESPACE_OID, f"{code}{n}"), y=70.0 + 22 * n)
            for n in range(ports)
        ],
        output=100.0,
    )


def port(code: str, n: int = 0) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_OID, f"{code}{n}")


def horizontal_and_vertical(points: list[tuple[float, float]]) -> bool:
    return all(a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:], strict=False))


def test_an_arrow_to_the_next_column_leaves_right_turns_in_the_gap_and_enters_its_row() -> None:
    a, b = card("a", 0, 40), card("b", 420, 200)
    (found,) = route([a, b], [Link(provider="a", consumer="b", exchange_id=port("b"))])
    assert found.points[0] == (300.0, 140.0)
    assert found.points[-1] == (420.0, 270.0)
    assert horizontal_and_vertical(found.points)
    assert all(300.0 <= x <= 420.0 for x, _ in found.points)


def test_an_arrow_across_a_column_runs_on_a_lane_clear_of_the_cards_between() -> None:
    a, middle, c = card("a", 0, 40), card("m", 420, 40, height=400), card("c", 840, 40)
    (found,) = route([a, middle, c], [Link(provider="a", consumer="c", exchange_id=port("c"))])
    assert horizontal_and_vertical(found.points)
    lanes = [
        y
        for (x0, y), (x1, y1) in zip(found.points, found.points[1:], strict=False)
        if y == y1 and x0 < 720 and x1 > 420
    ]
    assert lanes and all(y < 40 or y > 440 for y in lanes)


def test_arrows_from_one_provider_share_a_track_and_others_do_not() -> None:
    a, b = card("a", 0, 40), card("b", 0, 300)
    c = card("c", 420, 40, ports=3)
    found = route(
        [a, b, c],
        [
            Link(provider="a", consumer="c", exchange_id=port("c", 0)),
            Link(provider="a", consumer="c", exchange_id=port("c", 1)),
            Link(provider="b", consumer="c", exchange_id=port("c", 2)),
        ],
    )
    tracks = [r.points[1][0] for r in found]
    assert tracks[0] == tracks[1] != tracks[2]


def test_an_arrow_back_to_an_earlier_column_goes_out_right_over_a_lane_and_in_from_the_left() -> (
    None
):
    a, b = card("a", 420, 40), card("b", 0, 40)
    (found,) = route([a, b], [Link(provider="a", consumer="b", exchange_id=port("b"))])
    assert found.points[0][0] == 720.0 and found.points[1][0] > 720.0
    assert found.points[-2][0] < 0.0 and found.points[-1] == (0.0, 110.0)
    assert horizontal_and_vertical(found.points)


def inside(points: list[tuple[float, float]], cards: list[Placement]) -> bool:
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        for c in cards:
            if (
                min(x0, x1) < c.x + c.width
                and c.x < max(x0, x1)
                and min(y0, y1) < c.y + c.height
                and c.y < max(y0, y1)
            ):
                return True
    return False


def test_the_same_input_twice_gives_equal_routes() -> None:
    a, b = card("a", 0, 40), card("b", 420, 200)
    link = [Link(provider="a", consumer="b", exchange_id=port("b"))]
    assert route([a, b], link) == route([a, b], link)


def test_lanes_of_different_providers_over_overlapping_spans_are_apart() -> None:
    a, b = card("a", 0, 40), card("b", 0, 200)
    middle = card("m", 420, 40, height=400)
    c = card("c", 840, 40, ports=2)
    found = route(
        [a, b, middle, c],
        [
            Link(provider="a", consumer="c", exchange_id=port("c", 0)),
            Link(provider="b", consumer="c", exchange_id=port("c", 1)),
        ],
    )
    lanes = [
        y
        for r in found
        for (x0, y), (x1, y1) in zip(r.points, r.points[1:], strict=False)
        if y == y1 and x0 < 720 and x1 > 420
    ]
    assert len(lanes) == 2 and abs(lanes[0] - lanes[1]) >= 12.0


def test_a_held_card_straddling_the_provider_edge_is_not_crossed() -> None:
    a, held, c = card("a", 0, 40), card("s", 200, 300), card("c", 620, 40)
    (found,) = route([a, held, c], [Link(provider="a", consumer="c", exchange_id=port("c"))])
    assert horizontal_and_vertical(found.points)
    assert found.points[1][0] > 500.0
    assert not inside(found.points, [a, held, c])


def test_a_gap_narrower_than_the_margins_keeps_every_track_inside() -> None:
    a, b = card("a", 0, 40), card("b", 0, 300)
    c = card("c", 320, 40, ports=2)
    found = route(
        [a, b, c],
        [
            Link(provider="a", consumer="c", exchange_id=port("c", 0)),
            Link(provider="b", consumer="c", exchange_id=port("c", 1)),
        ],
    )
    assert all(300.0 < r.points[1][0] < 320.0 for r in found)


def test_no_placements_have_no_routes() -> None:
    assert route([], []) == []


def test_every_vertical_track_of_a_gap_lies_in_its_left_45_percent() -> None:
    providers = [card(f"p{n}", 0, 40 + 150 * n) for n in range(6)]
    c = card("c", 500, 40, ports=6)
    found = route(
        [*providers, c],
        [Link(provider=f"p{n}", consumer="c", exchange_id=port("c", n)) for n in range(6)],
    )
    tracks = [
        x for r in found for (x, _), (x1, _) in zip(r.points, r.points[1:], strict=False) if x == x1
    ]
    assert tracks and all(300.0 < x <= 300.0 + 0.45 * 200.0 for x in tracks)


def test_a_label_sits_before_the_consumer_above_the_entry_line() -> None:
    a, b = card("a", 0, 40), card("b", 500, 200)
    (found,) = routed(
        [a, b],
        [Link(provider="a", consumer="b", exchange_id=port("b"))],
        {port("b"): LinkText("1 kg", "12345 kg", None)},
    )
    label = found.label
    width = 7.0 * len("12345 kg") + 8.0
    assert label.width == width and label.height == 16.0
    assert label.x + label.width == 500.0 - LABEL_GAP
    assert label.y + label.height == 270.0 - LABEL_LIFT
    assert (label.per_unit, label.scaled) == ("1 kg", "12345 kg")
    assert LABEL_HEIGHT == 16.0


def test_a_label_without_a_scaled_text_is_measured_on_the_per_unit_text() -> None:
    a, b = card("a", 0, 40), card("b", 500, 200)
    (found,) = routed(
        [a, b],
        [Link(provider="a", consumer="b", exchange_id=port("b"))],
        {port("b"): LinkText("1 kg", None, None)},
    )
    assert found.label.width == 7.0 * 4 + 8.0 and found.label.scaled is None


def test_a_link_without_texts_is_named() -> None:
    a, b = card("a", 0, 40), card("b", 500, 200)
    with pytest.raises(Invalid, match=str(port("b"))):
        routed([a, b], [Link(provider="a", consumer="b", exchange_id=port("b"))], {})


def test_labels_of_arrows_into_consecutive_rows_do_not_overlap() -> None:
    a, b = card("a", 0, 40), card("b", 500, 40, ports=2)
    found = route(
        [a, b],
        [
            Link(provider="a", consumer="b", exchange_id=port("b", 0)),
            Link(provider="a", consumer="b", exchange_id=port("b", 1)),
        ],
    )
    first, second = sorted((r.label for r in found), key=lambda label: label.y)
    assert second.y - first.y == 22.0
    assert first.y + first.height <= second.y


def test_a_label_carries_its_formula_text_and_is_measured_over_the_longest_text() -> None:
    a, b = card("a", 0, 40), card("b", 500, 200)
    (found,) = routed(
        [a, b],
        [Link(provider="a", consumer="b", exchange_id=port("b"))],
        {port("b"): LinkText("1 kg", "2 kg", "ƒ kWh")},
    )
    assert found.label.formula == "ƒ kWh"
    assert found.label.width == 7.0 * len("ƒ kWh") + 8.0
