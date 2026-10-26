from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest

from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import NOISE_FLOOR, Calculation
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import DemandItem, Exchange, Method, ProductSystem, method_id
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef
from tests.conftest import fixture_system, split_system
from tests.engine.conftest import GWP_METHOD, WATER_METHOD, WIDGET
from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS


def host() -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    return system


def score(
    calculation: Calculation, product_system: ProductSystem, demand: list[DemandItem]
) -> float:
    foreground = calculation.foreground(product_system, {})
    solution = calculation.solve(foreground, demand)
    return float(calculation.scores(solution, [GWP_METHOD]).values()[0])


def using_its_own(own: float) -> ProductSystem:
    """The fixture with the widget using `own` of the one widget it makes."""
    system = host().model_copy(deep=True)
    system.process("widget").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="widget",
            amount=own,
            unit="unit",
            input=ForegroundRef(code="widget"),
        )
    )
    return system


def test_the_widget_its_frame_and_twice_the_demand(calculation: Calculation) -> None:
    assert score(calculation, host(), WIDGET) == pytest.approx(4.158)
    frame = [DemandItem(ref=ForegroundRef(code="frame"), amount=1.0)]
    assert score(calculation, host(), frame) == pytest.approx(6.672)
    twice = [DemandItem(ref=ForegroundRef(code="widget"), amount=2.0)]
    assert score(calculation, host(), twice) == pytest.approx(8.316)


def test_a_process_using_some_of_its_own_product_scales_by_what_it_delivers(
    calculation: Calculation,
) -> None:
    # one widget delivered takes 1 / (1 - 0.2) widgets made
    assert score(calculation, using_its_own(0.2), WIDGET) == pytest.approx(4.158 / 0.8)


def test_a_process_using_as_much_of_its_own_product_as_it_makes_is_invalid(
    calculation: Calculation,
) -> None:
    for own in (1.0, 1.5):
        with pytest.raises(Invalid, match="widget uses"):
            calculation.foreground(using_its_own(own), {})


def test_a_loop_using_as_much_of_its_products_as_it_makes_is_invalid(
    calculation: Calculation,
) -> None:
    looped = host().model_copy(deep=True)
    looped.process("frame").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="widget",
            amount=4.0,
            unit="unit",
            input=ForegroundRef(code="widget"),
        )
    )
    with pytest.raises(Invalid, match="frame, widget feed each other"):
        calculation.foreground(looped, {})


def test_a_process_that_produces_nothing_makes_the_foreground_singular(
    calculation: Calculation,
) -> None:
    idle = host().model_copy(deep=True)
    production = next(e for e in idle.process("frame").exchanges if e.type == "production")
    production.amount = 0.0
    foreground = calculation.foreground(idle, {})
    with pytest.raises(Invalid, match="singular"):
        calculation.solve(foreground, WIDGET)


def test_a_background_demand_with_no_foreground(calculation: Calculation) -> None:
    steel = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=1.0)]
    solution = calculation.solve(None, steel)
    assert calculation.scores(solution, [GWP_METHOD]).values()[0] == pytest.approx(2.78)
    assert solution.process_supply.nnz == 0


def test_a_foreground_demand_without_a_product_system_is_invalid(
    calculation: Calculation,
) -> None:
    with pytest.raises(Invalid, match="no product system"):
        calculation.solve(None, WIDGET)


def test_an_unknown_background_demand_is_not_found(calculation: Calculation) -> None:
    for unknown in (f"{uuid.uuid4()}_{uuid.uuid4()}", "not-a-native-id"):
        demand = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=unknown), amount=1.0)]
        with pytest.raises(NotFound, match="does not hold"):
            calculation.solve(None, demand)


def test_a_demand_on_another_database_is_invalid(calculation: Calculation) -> None:
    demand = [DemandItem(ref=BackgroundRef(database="elsewhere", id=CODES["steel"]), amount=1.0)]
    with pytest.raises(Invalid, match="elsewhere"):
        calculation.solve(None, demand)


def test_scores_keep_the_order_given_and_name_every_missing_method(
    calculation: Calculation,
) -> None:
    solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
    scores = calculation.scores(solution, [WATER_METHOD, GWP_METHOD])
    assert scores.coords["category"].labels.tolist() == [WATER_METHOD.id, GWP_METHOD.id]
    assert scores.values().tolist() == pytest.approx([0.0, 4.158])
    bogus = GWP_METHOD.model_copy(
        update={
            "tuple": ("fixture", "nothing"),
            "spec": "fixture > nothing",
            "id": method_id("fixture > nothing"),
        }
    )
    with pytest.raises(NotFound, match="fixture > nothing"):
        calculation.scores(solution, [GWP_METHOD, bogus])


def test_contributions_by_process_sum_to_the_score(calculation: Calculation) -> None:
    solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
    contributions = calculation.by_process(solution, GWP_METHOD)
    background = dict(
        zip(
            contributions.background.coords["activity"].labels.tolist(),
            contributions.background.values().tolist(),
            strict=True,
        )
    )
    # electricity: widget's 1 kWh plus 2 kWh per kg of the 1.1 kg of steel
    assert background[CODES["elec"]] == pytest.approx(3.2)
    assert background[CODES["steel"]] == pytest.approx(1.1 * 0.78)
    foreground = contributions.foreground.values()
    assert foreground.tolist() == pytest.approx([0.1, 0.0])
    assert foreground.sum() + sum(background.values()) == pytest.approx(4.158)


def test_contributions_by_flow_are_carbon_dioxide_then_methane(calculation: Calculation) -> None:
    solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
    by_flow = calculation.by_flow(solution, GWP_METHOD)
    values = dict(
        zip(by_flow.coords["flow"].labels.tolist(), by_flow.values().tolist(), strict=True)
    )
    assert values[FLOW_IDS["co2"]] == pytest.approx(3.85)
    assert values[FLOW_IDS["ch4"]] == pytest.approx(0.011 * 28)
    assert sum(values.values()) == pytest.approx(4.158)


def emitting(pm: float) -> ProductSystem:
    """The fixture with the widget emitting `pm` kilograms of particulates."""
    system = host().model_copy(deep=True)
    flows = system.database.elementary_flows
    system.process("widget").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="elementary",
            name="pm",
            amount=pm,
            unit="kilogram",
            input=ElementaryFlowRef(database=flows, id=FLOW_IDS["pm"]),
        )
    )
    return system


def test_an_amount_at_the_noise_floor_is_set_aside_and_counted(calculation: Calculation) -> None:
    assert NOISE_FLOOR == 1e-34
    for pm, kept in ((1e-40, False), (1e-30, True)):
        solution = calculation.solve(calculation.foreground(emitting(pm), {}), WIDGET)
        inventory = calculation.inventory(solution)
        amounts = dict(
            zip(
                inventory.amounts.coords["flow"].labels.tolist(),
                inventory.amounts.values().tolist(),
                strict=True,
            )
        )
        largest = max(abs(v) for v in solution.inventory.values().tolist())
        assert inventory.floor == NOISE_FLOOR * largest
        assert (amounts[FLOW_IDS["pm"]] != 0.0) is kept
        assert (FLOW_IDS["pm"] in inventory.sources) is kept
        assert inventory.dropped == (0 if kept else 1)


def test_the_inventory_names_each_flow_by_its_dominant_process(calculation: Calculation) -> None:
    solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
    inventory = calculation.inventory(solution)
    amounts = dict(
        zip(
            inventory.amounts.coords["flow"].labels.tolist(),
            inventory.amounts.values().tolist(),
            strict=True,
        )
    )
    assert amounts[FLOW_IDS["co2"]] == pytest.approx(3.85)
    assert amounts[FLOW_IDS["ch4"]] == pytest.approx(0.011)
    assert amounts[FLOW_IDS["pm"]] == 0.0
    assert inventory.sources == {FLOW_IDS["co2"]: "widget", FLOW_IDS["ch4"]: "frame"}


def test_a_flow_from_a_demanded_background_activity_has_no_source(
    calculation: Calculation,
) -> None:
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["lorry"]), amount=100.0)
    solution = calculation.solve(calculation.foreground(host(), {}), [*WIDGET, steel])
    inventory = calculation.inventory(solution)
    # the lorry's particulate matter has no foreground process
    assert inventory.sources[FLOW_IDS["pm"]] is None
    assert inventory.sources[FLOW_IDS["ch4"]] == "frame"
    alone = calculation.inventory(calculation.solve(None, [steel]))
    assert set(alone.sources.values()) == {None}


def test_supply_solves_the_foreground_alone(
    calculation: Calculation, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_: np.ndarray) -> np.ndarray:
        raise AssertionError("supply solved the background")

    monkeypatch.setattr(calculation.solver, "forward", refuse)
    supply = calculation.supply(calculation.foreground(host(), {}), WIDGET)
    assert supply.coords["process"].labels.tolist() == ["widget", "frame"]
    assert supply.values().tolist() == pytest.approx([1.0, 0.25])


def test_a_linked_system_scores_as_the_one_system_it_came_from(calculation: Calculation) -> None:
    system = split_system()
    assert system.product_system is not None
    foreground = calculation.foreground(system.product_system, system.linked)
    solution = calculation.solve(foreground, WIDGET)
    assert calculation.scores(solution, [GWP_METHOD]).values()[0] == pytest.approx(4.158)
    [frame_id] = system.linked
    labels = foreground.labels.tolist()
    assert labels == ["widget", f"{frame_id}/frame"]
    assert foreground.ref(1).kind == "linked"
    assert calculation.inventory(solution).sources[FLOW_IDS["ch4"]] == f"{frame_id}/frame"


def test_the_two_solvers_agree_and_each_solution_names_its_solver(background: Background) -> None:
    results = {}
    for name in ("superlu", "pardiso"):
        calculation = Calculation(background, name)
        solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
        assert solution.solver == name
        results[name] = solution.inventory.values()
    np.testing.assert_allclose(results["superlu"], results["pardiso"], rtol=1e-12)


def test_the_intensities_are_each_dataset_cradle_to_gate(calculation: Calculation) -> None:
    intensities = calculation.intensities([GWP_METHOD, WATER_METHOD])
    assert intensities.dims == ("category", "activity")
    gwp = intensities.sel({"category": GWP_METHOD.id})
    by_label = dict(zip(gwp.coords["activity"].labels.tolist(), gwp.values().tolist(), strict=True))
    assert by_label[CODES["steel"]] == pytest.approx(2.78)
    assert by_label[CODES["elec"]] == pytest.approx(1.0)


def test_a_method_is_resolved_by_its_id(calculation: Calculation) -> None:
    same = Method.of(("fixture", "gwp", "climate change > GWP100"), "kg CO2-Eq")
    assert same.id == GWP_METHOD.id
    solution = calculation.solve(calculation.foreground(host(), {}), WIDGET)
    assert calculation.scores(solution, [same]).values()[0] == pytest.approx(4.158)


def test_a_saved_and_loaded_background_scores_as_the_one_compiled(
    background: Background, tmp_path: Path
) -> None:
    background.save(tmp_path / "saved")
    loaded = Calculation(Background.load(tmp_path / "saved"))
    solution = loaded.solve(loaded.foreground(host(), {}), WIDGET)
    assert loaded.scores(solution, [GWP_METHOD]).values()[0] == pytest.approx(4.158)


def test_the_demand_is_placed_on_the_foreground_and_on_the_background(
    calculation: Calculation,
) -> None:
    system = fixture_system().product_system
    assert system is not None
    fg = calculation.foreground(system, {})
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=2.0)
    d_fg, d_bg = calculation.placed(fg, [*WIDGET, steel])
    assert d_fg.tolist() == [1.0, 0.0]
    assert d_bg[calculation.background.position("activity", CODES["steel"])] == 2.0
    assert d_bg.sum() == 2.0
