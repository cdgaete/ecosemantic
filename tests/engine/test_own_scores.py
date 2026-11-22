from __future__ import annotations

import uuid

import pytest

from ecosemantic.engine.calculation import (
    ActivityScore,
    Calculation,
    LinkedScore,
    OwnScore,
    OwnScores,
)
from ecosemantic.engine.foreground import Foreground
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Exchange
from ecosemantic.model.refs import BackgroundRef, DemandItem, ForegroundRef
from ecosemantic.ports.types import System
from tests.conftest import fixture_system, split_system
from tests.engine.conftest import GWP_METHOD, WIDGET
from tests.fixture_data import CODES, FIXTURE_DB


def foreground_of(calculation: Calculation, system: System) -> Foreground:
    assert system.product_system is not None
    return calculation.foreground(system.product_system, system.linked)


def by_ref(scores: OwnScores) -> dict[str, OwnScore]:
    return {part.ref.code: part for part in scores.parts}


def inputs_of(part: OwnScore) -> dict[str, float]:
    return {entry.label: entry.score for entry in part.inputs if isinstance(entry, ActivityScore)}


def widget_with_plastic(amount: float) -> System:
    """The fixture's widget taking `amount` kilograms of plastic from the background."""
    system = fixture_system()
    assert system.product_system is not None
    product_system = system.product_system.model_copy(deep=True)
    product_system.process("widget").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="polyethylene",
            amount=amount,
            unit="kilogram",
            input=BackgroundRef(database=FIXTURE_DB, id=CODES["plastic"]),
        )
    )
    return system.model_copy(update={"product_system": product_system})


def test_own_scores_partition_the_widget(calculation: Calculation) -> None:
    foreground = foreground_of(calculation, fixture_system())
    scores = calculation.own_scores(foreground, WIDGET, GWP_METHOD)
    assert scores.total == pytest.approx(4.158)
    parts = by_ref(scores)
    assert list(parts) == ["widget", "frame"]
    widget, frame = parts["widget"], parts["frame"]
    assert widget.direct == pytest.approx(0.1)
    assert inputs_of(widget) == {
        CODES["steel"]: pytest.approx(1.39),
        CODES["elec"]: pytest.approx(1.0),
    }
    assert widget.score == pytest.approx(2.49)
    assert frame.direct == pytest.approx(0.0)
    assert inputs_of(frame) == {CODES["steel"]: pytest.approx(1.668)}
    assert frame.score == pytest.approx(1.668)
    assert abs(sum(part.score for part in scores.parts) - scores.total) <= 1e-12


def test_a_linked_system_is_an_input_of_the_process_taking_it(calculation: Calculation) -> None:
    system = split_system()
    foreground = foreground_of(calculation, system)
    scores = calculation.own_scores(foreground, WIDGET, GWP_METHOD)
    assert scores.total == pytest.approx(4.158)
    [part] = scores.parts
    assert part.ref.code == "widget"
    assert part.position == foreground.column_of(system.product_system.id, "widget", "the widget")
    assert part.score == pytest.approx(4.158)
    [linked] = [entry for entry in part.inputs if isinstance(entry, LinkedScore)]
    assert linked.ref.code == "frame"
    assert foreground.columns[linked.position].process.code == "frame"
    assert linked.ref == foreground.ref(linked.position)
    assert linked.score == pytest.approx(1.668)
    assert [isinstance(entry, ActivityScore) for entry in part.inputs] == [True, True, False]
    background = sorted(entry.score for entry in part.inputs if isinstance(entry, ActivityScore))
    assert background == [pytest.approx(1.0), pytest.approx(1.39)]
    assert abs(sum(part.score for part in scores.parts) - scores.total) <= 1e-12


def test_own_scores_scale_with_the_demand(calculation: Calculation) -> None:
    foreground = foreground_of(calculation, fixture_system())
    base = calculation.own_scores(foreground, WIDGET, GWP_METHOD)
    doubled = calculation.own_scores(
        foreground, [DemandItem(ref=ForegroundRef(code="widget"), amount=2.0)], GWP_METHOD
    )
    assert doubled.total == pytest.approx(2 * base.total)
    assert [part.position for part in doubled.parts] == [part.position for part in base.parts]
    for part, was in zip(doubled.parts, base.parts, strict=True):
        assert part.score == pytest.approx(2 * was.score)
        assert part.direct == pytest.approx(2 * was.direct)
        for value, before in zip(part.inputs, was.inputs, strict=True):
            assert value.score == pytest.approx(2 * before.score)


def test_a_negative_input_is_a_negative_part(calculation: Calculation) -> None:
    # polyethylene scores 5.0 a kilogram: 3 kWh of electricity at 1.0 and 2 kg of CO2
    foreground = foreground_of(calculation, widget_with_plastic(-0.5))
    scores = calculation.own_scores(foreground, WIDGET, GWP_METHOD)
    parts = by_ref(scores)
    widget = parts["widget"]
    assert inputs_of(widget)[CODES["plastic"]] == pytest.approx(-2.5)
    assert widget.score == pytest.approx(-0.01)
    assert parts["frame"].score == pytest.approx(1.668)
    assert scores.total == pytest.approx(1.658)
    assert abs(sum(part.score for part in scores.parts) - scores.total) <= 1e-12


def test_own_scores_take_only_the_systems_own_demand(calculation: Calculation) -> None:
    foreground = foreground_of(calculation, fixture_system())
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)
    with pytest.raises(Invalid, match="own processes"):
        calculation.own_scores(foreground, [steel], GWP_METHOD)
