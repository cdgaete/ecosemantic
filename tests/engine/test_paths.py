from __future__ import annotations

import uuid

import pytest

from ecosemantic.engine.background import Background, Factors, Rows
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.paths import PathNode
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import DemandItem, Exchange, Method, Process, ProductSystem
from ecosemantic.model.refs import BackgroundRef, Database, ForegroundRef
from tests.conftest import fixture_system
from tests.engine.conftest import GWP_METHOD, WIDGET
from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS


def host() -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    return system


def every_node(node: PathNode) -> list[PathNode]:
    return [node, *(n for child in node.children for n in every_node(child))]


def test_the_root_is_the_score_and_its_children_sum_to_it(calculation: Calculation) -> None:
    foreground = calculation.foreground(host(), {})
    tree = calculation.paths(foreground, WIDGET[0], GWP_METHOD, 4, 200, 0.0)
    assert tree.root.score == pytest.approx(4.158) and tree.total == pytest.approx(4.158)
    assert not tree.truncated
    first = {(child.kind, child.label): child.score for child in tree.root.children}
    assert first == {
        ("process", "frame"): pytest.approx(0.25 * 6.672),
        ("activity", CODES["steel"]): pytest.approx(0.5 * 2.78),
        ("activity", CODES["elec"]): pytest.approx(1.0),
        ("flow", FLOW_IDS["co2"]): pytest.approx(0.1),
    }
    for node in every_node(tree.root):
        if node.children:
            assert sum(child.score for child in node.children) == pytest.approx(node.score)


def test_a_bound_truncates_and_leaves_a_remainder(calculation: Calculation) -> None:
    foreground = calculation.foreground(host(), {})
    tree = calculation.paths(foreground, WIDGET[0], GWP_METHOD, 1, 3, 0.0)
    assert tree.truncated
    kinds = [child.kind for child in tree.root.children]
    assert kinds.count("remainder") == 1
    assert sum(child.score for child in tree.root.children) == pytest.approx(4.158)


def test_paths_start_at_a_foreground_process(calculation: Calculation) -> None:
    foreground = calculation.foreground(host(), {})
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)
    with pytest.raises(Invalid, match="one foreground process"):
        calculation.paths(foreground, steel, GWP_METHOD, 3, 50, 0.001)


def test_a_foreground_credit_is_a_child_with_a_negative_score(calculation: Calculation) -> None:
    # the widget avoids 0.2 kg of a recovered frame, a process using 1 kg of steel per kg
    system = host().model_copy(deep=True)
    system.processes.append(
        Process(
            id=uuid.uuid4(),
            code="recovered",
            name="recovered frame",
            unit="kilogram",
            location="GLO",
            reference_product="recovered frame",
            exchanges=[
                Exchange(
                    id=uuid.uuid4(),
                    type="production",
                    name="recovered frame",
                    amount=1.0,
                    unit="kilogram",
                ),
                Exchange(
                    id=uuid.uuid4(),
                    type="product",
                    name="steel",
                    amount=1.0,
                    unit="kilogram",
                    input=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]),
                ),
            ],
        )
    )
    system.process("widget").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="recovered frame",
            amount=-0.2,
            unit="kilogram",
            input=ForegroundRef(code="recovered"),
        )
    )
    tree = calculation.paths(calculation.foreground(system, {}), WIDGET[0], GWP_METHOD, 4, 200, 0.0)
    credit = next(child for child in tree.root.children if child.label == "recovered")
    assert credit.amount == pytest.approx(-0.2)
    assert credit.score == pytest.approx(-0.2 * 2.78)
    assert tree.root.score == pytest.approx(4.158 - 0.2 * 2.78)
    assert not any(child.kind == "remainder" for child in tree.root.children)


def test_a_background_credit_is_a_child_with_a_negative_score() -> None:
    # a mill makes paper, emits 1 kg CO2 and is credited the 0.5 kWh of energy it recovers,
    # whose making emits 1 kg CO2 per kWh
    database = Database(
        name="small",
        elementary_flows="small-biosphere",
        scheme="olca",
        version="1",
        system_model="unit process",
    )
    gwp = Method.of(("small", "gwp", "climate change > GWP100"), "kg CO2-Eq")
    background = Background.compile(
        database,
        activities=["mill", "energy"],
        flows=["co2"],
        methods=[gwp],
        technosphere=Rows(
            rows=["mill", "energy", "energy"],
            columns=["mill", "energy", "mill"],
            amounts=[1.0, 1.0, -0.5],
            flipped=[False, False, True],
            uncertainties=[None, None, None],
        ),
        biosphere=Rows(
            rows=["co2", "co2"],
            columns=["mill", "energy"],
            amounts=[1.0, 1.0],
            flipped=[False, False],
            uncertainties=[None, None],
        ),
        factors=Factors(categories=[gwp.id], flows=["co2"], values=[1.0]),
    )
    calculation = Calculation(background)
    product_system = ProductSystem(
        id=uuid.uuid4(),
        name="book",
        database=database,
        processes=[
            Process(
                id=uuid.uuid4(),
                code="book",
                name="book",
                unit="unit",
                location="GLO",
                reference_product="book",
                exchanges=[
                    Exchange(
                        id=uuid.uuid4(), type="production", name="book", amount=1.0, unit="unit"
                    ),
                    Exchange(
                        id=uuid.uuid4(),
                        type="product",
                        name="paper",
                        amount=1.0,
                        unit="kilogram",
                        input=BackgroundRef(database="small", id="mill"),
                    ),
                ],
            )
        ],
        reference_process="book",
    )
    foreground = calculation.foreground(product_system, {})
    demand = DemandItem(ref=ForegroundRef(code="book"), amount=1.0)
    tree = calculation.paths(foreground, demand, gwp, 4, 50, 0.0)
    [mill] = [child for child in tree.root.children if child.label == "mill"]
    energy = next(child for child in mill.children if child.label == "energy")
    assert energy.amount == pytest.approx(-0.5)
    assert energy.score == pytest.approx(-0.5)
    assert sum(child.score for child in mill.children) == pytest.approx(mill.score)
    assert mill.score == pytest.approx(1.0 - 0.5)
