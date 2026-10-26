from __future__ import annotations

import uuid

from ecosemantic.geometry import Placement
from ecosemantic.routes import Label, Route
from ecosemantic.troubles import score, troubles


def card(code: str, x: float, y: float) -> Placement:
    return Placement(code=code, x=x, y=y, width=300.0, height=100.0, depth=0, output=50.0)


def far() -> Label:
    far.count += 1
    return Label(
        x=-900 - 100 * far.count,
        y=-900,
        width=50,
        height=16,
        per_unit="1 kg",
        scaled=None,
        formula=None,
    )


far.count = 0


def arrow(
    provider: str,
    consumer: str,
    points: list[tuple[float, float]],
    label: Label | None = None,
) -> Route:
    label = label or far()
    return Route(
        provider=provider, consumer=consumer, exchange_id=uuid.uuid4(), points=points, label=label
    )


def boxed(x: float, y: float, width: float = 50.0) -> Label:
    return Label(x=x, y=y, width=width, height=16, per_unit="1 kg", scaled=None, formula=None)


def kinds(placements: list[Placement], routes: list[Route]) -> list[str]:
    return [t.kind for t in troubles(placements, routes)]


def test_an_arrow_over_a_card_is_named() -> None:
    cards = [card("a", 0, 0), card("m", 420, 0), card("c", 840, 0)]
    found = kinds(cards, [arrow("a", "c", [(300, 50), (840, 50)])])
    assert found == ["edge_through_card"]


def test_two_arrows_of_different_providers_crossing_anywhere_are_named() -> None:
    cards = [card("a", 0, 0), card("b", 0, 300), card("c", 840, 0), card("d", 840, 300)]
    routes = [
        arrow("a", "d", [(300, 50), (600, 50), (600, 350), (840, 350)]),
        arrow("b", "c", [(300, 350), (500, 350), (500, 200), (700, 200), (700, 50), (840, 50)]),
    ]
    assert kinds(cards, routes).count("edges_cross") == 1


def test_arrows_of_one_provider_on_one_track_are_not_named() -> None:
    cards = [card("a", 0, 0), card("c", 420, 0), card("d", 420, 200)]
    routes = [
        arrow("a", "c", [(300, 50), (340, 50), (340, 60), (420, 60)]),
        arrow("a", "d", [(300, 50), (340, 50), (340, 260), (420, 260)]),
    ]
    assert kinds(cards, routes) == []


def test_arrows_of_different_providers_on_one_line_are_named() -> None:
    cards = [card("a", 0, 0), card("b", 0, 200), card("c", 420, 0)]
    routes = [
        arrow("a", "c", [(300, 50), (340, 50), (340, 60), (420, 60)]),
        arrow("b", "c", [(300, 250), (340, 250), (340, 40), (420, 40)]),
    ]
    assert "edges_overlap" in kinds(cards, routes)


def test_the_score_weighs_each_kind() -> None:
    cards = [card("a", 0, 0), card("b", 100, 0)]
    found = troubles(cards, [])
    assert [t.kind for t in found] == ["cards_overlap"] and score(found) == 10


def test_an_arrow_from_a_card_to_itself_points_no_way() -> None:
    cards = [card("a", 0, 0)]
    loop = arrow("a", "a", [(300, 50), (324, 50), (324, -30), (-24, -30), (-24, 60), (0, 60)])
    assert kinds(cards, [loop]) == []


def test_an_arrow_into_an_earlier_column_is_named_backwards() -> None:
    cards = [card("a", 420, 0), card("c", 0, 0)]
    found = kinds(
        cards, [arrow("a", "c", [(720, 50), (744, 50), (744, -30), (-24, -30), (-24, 50), (0, 50)])]
    )
    assert found == ["edge_backwards"]


def test_an_arrow_along_a_card_border_does_not_pass_through_it() -> None:
    cards = [card("a", 0, 0), card("m", 420, 0), card("c", 840, 200)]
    found = kinds(cards, [arrow("a", "c", [(300, 50), (360, 50), (360, 100), (840, 100)])])
    assert "edge_through_card" not in found
    along = kinds(cards, [arrow("a", "c", [(300, 50), (420, 50), (420, 250), (840, 250)])])
    assert "edge_through_card" not in along


def test_arrows_touching_at_an_end_or_meeting_in_a_t_do_not_cross() -> None:
    cards = [card("a", 0, 0), card("b", 0, 300), card("c", 840, 0), card("d", 840, 300)]
    tee = [
        arrow("a", "c", [(300, 50), (600, 50), (600, 200), (840, 200)]),
        arrow("b", "d", [(300, 350), (500, 350), (500, 120), (600, 120)]),
    ]
    assert "edges_cross" not in kinds(cards, tee)
    shared = [
        arrow("a", "c", [(300, 50), (500, 50), (500, 150), (840, 150)]),
        arrow("b", "d", [(300, 350), (500, 350), (500, 150)]),
    ]
    assert "edges_cross" not in kinds(cards, shared)


def test_a_label_over_a_card_is_named() -> None:
    cards = [card("a", 0, 0), card("c", 500, 0)]
    routes = [arrow("a", "c", [(300, 50), (500, 50)], boxed(480, 40))]
    assert kinds(cards, routes) == ["label_overlap"]


def test_a_label_clear_of_everything_is_not_named() -> None:
    cards = [card("a", 0, 0), card("c", 500, 0)]
    routes = [arrow("a", "c", [(300, 50), (500, 50)], boxed(430, 32))]
    assert kinds(cards, routes) == []


def test_two_labels_over_each_other_are_named_once() -> None:
    cards = [card("a", 0, 0), card("b", 0, 200), card("c", 500, 0), card("d", 500, 200)]
    routes = [
        arrow("a", "c", [(300, 50), (500, 50)], boxed(420, 300)),
        arrow("b", "d", [(300, 250), (500, 250)], boxed(430, 305)),
    ]
    assert kinds(cards, routes).count("label_overlap") == 1


def test_a_label_over_another_providers_vertical_segment_is_named() -> None:
    cards = [card("a", 0, 0), card("b", 0, 300), card("c", 500, 0)]
    routes = [
        arrow("a", "c", [(300, 50), (500, 50)], boxed(420, 32)),
        arrow("b", "c", [(300, 350), (440, 350), (440, 10), (500, 10)]),
    ]
    assert kinds(cards, routes).count("label_overlap") == 1


def test_a_label_over_its_own_providers_segment_is_not_named() -> None:
    cards = [card("a", 0, 0), card("c", 500, 0)]
    routes = [
        arrow("a", "c", [(300, 50), (440, 50), (440, 10), (500, 10)], boxed(420, 32)),
    ]
    assert kinds(cards, routes) == []


def test_two_arrows_into_one_fold_row_have_coinciding_labels_named() -> None:
    cards = [card("a", 0, 0), card("b", 0, 200), card("c", 500, 0)]
    routes = [
        arrow("a", "c", [(300, 50), (500, 50)], boxed(430, 32)),
        arrow("b", "c", [(300, 250), (350, 250), (350, 50), (500, 50)], boxed(430, 32)),
    ]
    assert kinds(cards, routes).count("label_overlap") == 1
