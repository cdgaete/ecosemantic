from __future__ import annotations

import math
import uuid

import numpy as np
import pytest
import scipy.sparse as sp

from ecosemantic.engine.background import Background, Exchanges, Factors, Rows
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.montecarlo import (
    DENSE,
    FOREGROUND_STREAM,
    Draw,
    MonteCarlo,
    Refactorised,
    Serial,
    drawn,
    generator,
    on_block,
)
from ecosemantic.engine.solver import Solver
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import (
    DemandItem,
    Exchange,
    Method,
    ProductSystem,
    Scope,
    Uncertainty,
    method_id,
)
from ecosemantic.model.refs import BackgroundRef, ForegroundRef
from tests.conftest import fixture_system, needs_pardiso, split_system
from tests.engine.conftest import GWP_METHOD, SMALL, SMALL_GWP, WATER_METHOD, WIDGET
from tests.engine_fixture import looped_background
from tests.fixture_data import CODES, FIXTURE_DB, LOOP_CODES, LOOP_DB, LOOP_GWP

LOOP_METHOD = Method(
    id=method_id(" > ".join(LOOP_GWP)),
    tuple=LOOP_GWP,
    spec=" > ".join(LOOP_GWP),
    unit="kg CO2-Eq",
    impact_method="gwp",
    impact_category="climate change",
    indicator="GWP100",
)


class Counted:
    """A draw solve that counts its solves."""

    def __init__(self, inner: Refactorised) -> None:
        self.inner = inner
        self.calls = 0

    def solve(self, technosphere, b):
        self.calls += 1
        return self.inner.solve(technosphere, b)


def host() -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    return system


def certain(system: ProductSystem) -> ProductSystem:
    """The system with no distribution on any exchange."""
    changed = system.model_copy(deep=True)
    for process in changed.processes:
        for exchange in process.exchanges:
            exchange.uncertainty = None
    return changed


def lognormal(amount: float, gsd: float) -> Uncertainty:
    return Uncertainty(type="lognormal", params={"loc": math.log(amount), "scale": math.log(gsd)})


def uniform(low: float, high: float) -> Uncertainty:
    return Uncertainty(type="uniform", params={"minimum": low, "maximum": high})


def with_direct_co2(system: ProductSystem, spread: Uncertainty) -> ProductSystem:
    """The system with a distribution on the widget's direct 0.1 kg CO2."""
    changed = system.model_copy(deep=True)
    changed.process("widget").exchanges[4].uncertainty = spread
    return changed


def feeding(
    system: ProductSystem, consumer: str, provider: str, amount: float, spread: Uncertainty | None
) -> ProductSystem:
    """The system with the consumer using an amount of the provider's product."""
    fed = system.model_copy(deep=True)
    fed.process(consumer).exchanges.append(
        Exchange(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"{consumer}/{provider}"),
            type="product",
            name=provider,
            amount=amount,
            unit="unit",
            input=ForegroundRef(code=provider),
            uncertainty=spread,
        )
    )
    return fed


def sampler(
    calculation: Calculation,
    system: ProductSystem | None,
    demand: list[DemandItem] = WIDGET,
    *,
    methods: list[Method] | None = None,
    scope: Scope = "full",
    seed: int = 5,
    dense: int = DENSE,
) -> MonteCarlo:
    foreground = None if system is None else calculation.foreground(system, {})
    return MonteCarlo(
        calculation,
        foreground,
        demand,
        methods or [GWP_METHOD],
        scope=scope,
        seed=seed,
        solve=Refactorised("superlu"),
        dense=dense,
    )


def scores(draws: list[Draw]) -> list[float | None]:
    return [None if d.scores is None else float(d.scores[0]) for d in draws]


def test_without_distributions_every_draw_scores_the_point_score(calculation: Calculation) -> None:
    system = certain(host())
    point = calculation.scores(
        calculation.solve(calculation.foreground(system, {}), WIDGET),
        [GWP_METHOD, WATER_METHOD],
    ).data
    mc = sampler(calculation, system, methods=[GWP_METHOD, WATER_METHOD])
    for draw in Serial().run(mc, range(5)):
        # the fixture's two wide normals are held at their amounts
        assert draw.scores is not None
        assert draw.scores == pytest.approx(point, rel=1e-12)
    assert point[0] == pytest.approx(4.158)


def test_a_linked_system_samples_as_the_one_system_it_came_from(
    calculation: Calculation,
) -> None:
    system = split_system()
    assert system.product_system is not None
    host_certain = certain(system.product_system)
    linked = {key: certain(other) for key, other in system.linked.items()}
    foreground = calculation.foreground(host_certain, linked)
    mc = MonteCarlo(
        calculation,
        foreground,
        WIDGET,
        [GWP_METHOD],
        scope="full",
        seed=5,
        solve=Refactorised("superlu"),
    )
    assert scores(list(Serial().run(mc, range(3)))) == pytest.approx([4.158] * 3)


def test_a_demand_of_several_items_draws_the_score_of_all_of_them(
    calculation: Calculation,
) -> None:
    system = certain(host())
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=2.0)
    demand = [*WIDGET, steel]
    point = calculation.scores(
        calculation.solve(calculation.foreground(system, {}), demand), [GWP_METHOD]
    ).data[0]
    mc = sampler(calculation, system, demand)
    assert scores(list(Serial().run(mc, range(3)))) == pytest.approx([point] * 3, rel=1e-12)
    # the widget's 4.158 and two kilograms of steel at 2.78 each
    assert point == pytest.approx(4.158 + 2 * 2.78)


def test_a_seed_and_an_index_fix_a_draw(calculation: Calculation) -> None:
    mc = sampler(calculation, host())
    indices = list(range(12))
    by_index = [mc.draw(k) for k in indices]
    shuffled = [7, 2, 11, 0, 5, 9, 1, 10, 3, 8, 6, 4]
    drawn_shuffled = list(Serial().run(sampler(calculation, host()), shuffled))
    assert [d.index for d in drawn_shuffled] == shuffled
    assert scores(drawn_shuffled) == [scores(by_index)[k] for k in shuffled]
    assert scores([mc.draw(4)]) == scores([by_index[4]])
    assert scores(list(Serial().run(sampler(calculation, host(), seed=6), indices))) != scores(
        by_index
    )


def test_each_foreground_exchange_draws_from_a_stream_of_its_own(
    calculation: Calculation,
) -> None:
    spread = lognormal(0.1, 1.2)
    both = with_direct_co2(host(), spread)
    base = sampler(calculation, host())
    varied = sampler(calculation, both)
    system_id = both.id.int
    co2 = both.process("widget").exchanges[4]
    for k in range(8):
        z = generator(5, (k, FOREGROUND_STREAM, system_id, co2.id.int)).standard_normal()
        expected = math.exp(math.log(0.1) + math.log(1.2) * z)
        # the steel draws are shared, so the scores differ by the CO2 drawn less the 0.1 stated
        difference = varied.draw(k).scores[0] - base.draw(k).scores[0]
        assert difference == pytest.approx(expected - 0.1, rel=1e-9, abs=1e-12)


def biosphere_background() -> Background:
    """A mill emitting a lognormal kilogram of CO2, and an energy whose production is lognormal and
    which the mill does not use."""
    return Background.compile(
        SMALL,
        activities=["mill", "energy"],
        flows=["co2", "noise"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=["mill", "energy"],
            columns=["mill", "energy"],
            amounts=[1.0, 1.0],
            flipped=[False, False],
            uncertainties=[None, lognormal(1.0, 1.1)],
        ),
        biosphere=Rows(
            rows=["co2"],
            columns=["mill"],
            amounts=[1.0],
            flipped=[False],
            uncertainties=[lognormal(1.0, 1.5)],
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )


def test_full_and_biosphere_only_draw_the_same_biosphere_amounts() -> None:
    calculation = Calculation(biosphere_background())
    mill = [DemandItem(ref=BackgroundRef(database=SMALL.name, id="mill"), amount=1.0)]
    full = sampler(calculation, None, mill, methods=[SMALL_GWP])
    fixed = sampler(calculation, None, mill, methods=[SMALL_GWP], scope="biosphere_only")
    full_scores = scores(list(Serial().run(full, range(10))))
    assert full_scores == pytest.approx(scores(list(Serial().run(fixed, range(10)))), rel=1e-12)
    # the mill's one kilogram of CO2 is drawn from the biosphere's stream, its own
    expected = [
        math.exp(math.log(1.5) * generator(5, (k, 1)).standard_normal(1)[0]) for k in range(10)
    ]
    assert full_scores == pytest.approx(expected, rel=1e-12)


def test_the_background_technosphere_draws_from_a_stream_of_its_own() -> None:
    background = Background.compile(
        SMALL,
        activities=["mill", "energy"],
        flows=["co2", "noise"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=["mill", "energy", "energy"],
            columns=["mill", "energy", "mill"],
            amounts=[1.0, 1.0, 2.0],
            flipped=[False, False, True],
            uncertainties=[None, None, lognormal(2.0, 1.3)],
        ),
        biosphere=Rows(
            rows=["co2"], columns=["energy"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )
    calculation = Calculation(background)
    mill = [DemandItem(ref=BackgroundRef(database=SMALL.name, id="mill"), amount=1.0)]
    drawn_scores = scores(
        list(Serial().run(sampler(calculation, None, mill, methods=[SMALL_GWP]), range(10)))
    )
    # the mill's energy is the third technosphere row, drawn from the technosphere's stream
    expected = [
        math.exp(math.log(2.0) + math.log(1.3) * generator(5, (k, 0)).standard_normal(3)[2])
        for k in range(10)
    ]
    assert drawn_scores == pytest.approx(expected, rel=1e-12)


def rows_of(uncertainty: Uncertainty, amount: float, n: int) -> Exchanges:
    return Exchanges.of(
        row=np.zeros(n, dtype=np.int64),
        column=np.zeros(n, dtype=np.int64),
        amounts=[amount] * n,
        flipped=[False] * n,
        uncertainties=[uncertainty] * n,
    )


@pytest.mark.parametrize(
    ("uncertainty", "amount", "mean", "variance"),
    [
        (lognormal(2.0, 1.2), 2.0, 2.0 * math.exp(math.log(1.2) ** 2 / 2), None),
        (
            Uncertainty(
                type="lognormal", params={"loc": math.log(2.0), "scale": 0.2, "negative": True}
            ),
            -2.0,
            -2.0 * math.exp(0.02),
            4.0 * (math.exp(0.04) - 1) * math.exp(0.04),
        ),
        (Uncertainty(type="normal", params={"loc": 3.0, "scale": 0.5}), 3.0, 3.0, 0.25),
        (uniform(1.0, 4.0), 2.5, 2.5, 9.0 / 12),
        # a mode off centre: mean (1 + 1.5 + 4) / 3, variance (1 + 2.25 + 16 - 1.5 - 4 - 6) / 18
        (
            Uncertainty(type="triangular", params={"minimum": 1.0, "loc": 1.5, "maximum": 4.0}),
            1.5,
            6.5 / 3,
            7.75 / 18,
        ),
    ],
)
def test_each_distribution_draws_its_own_mean_and_variance(
    uncertainty: Uncertainty, amount: float, mean: float, variance: float | None
) -> None:
    n = 20_000
    rows = rows_of(uncertainty, amount, n)
    g = generator(11, (0,))
    z, u = g.standard_normal(n), g.random(n)
    sample = drawn(rows=rows, z=z, u=u, held=np.zeros(n, dtype=bool))
    if variance is None:
        sigma = math.log(1.2)
        variance = (math.exp(sigma**2) - 1) * math.exp(2 * math.log(2.0) + sigma**2)
    centred = sample - sample.mean()
    se_variance = math.sqrt((np.mean(centred**4) - sample.var() ** 2) / n)
    assert abs(sample.mean() - mean) <= 4 * math.sqrt(variance / n)
    assert abs(sample.var(ddof=1) - variance) <= 4 * se_variance


def test_a_row_held_keeps_its_amount() -> None:
    rows = rows_of(Uncertainty(type="normal", params={"loc": 1.0, "scale": 5.0}), 1.0, 3)
    held = drawn(rows=rows, z=np.ones(3), u=np.ones(3) / 2, held=np.ones(3, dtype=bool))
    assert held.tolist() == [1.0, 1.0, 1.0]


def test_the_wide_background_normals_are_counted(calculation: Calculation) -> None:
    # one wide technosphere normal and one wide biosphere normal in the fixture
    assert sampler(calculation, host()).normals_at_amount == 2
    assert sampler(calculation, host(), scope="biosphere_only").normals_at_amount == 1


def test_a_draw_in_which_a_foreground_loop_delivers_nothing_is_dropped(
    calculation: Calculation,
) -> None:
    fed = feeding(host(), "widget", "widget", 0.5, lognormal(0.5, 1.5))
    own_use = fed.process("widget").exchanges[-1]
    draws = list(Serial().run(sampler(calculation, fed), range(200)))
    expected = []
    for k in range(200):
        z = generator(5, (k, FOREGROUND_STREAM, fed.id.int, own_use.id.int)).standard_normal()
        # the widget makes one and uses this much of it: it delivers while it uses less than one
        expected.append(math.exp(math.log(0.5) + math.log(1.5) * z) >= 1.0)
    assert [d.scores is None for d in draws] == expected
    assert any(expected)
    for d in draws:
        assert [o.loop.codes for o in d.short] == ([["widget"]] if d.scores is None else [])
        assert d.failing == ()
        assert d.scores is None or d.scores[0] > 0
    looped = feeding(host(), "frame", "widget", 3.6, lognormal(3.6, 1.5))
    loop_draws = list(Serial().run(sampler(calculation, looped), range(50)))
    dropped = [d for d in loop_draws if d.scores is None]
    assert dropped and all(
        [o.loop.codes for o in d.short] == [["frame", "widget"]] for d in dropped
    )


def test_a_loop_holding_a_credit_is_not_judged_in_a_draw(calculation: Calculation) -> None:
    # the frame co-produces four widgets, a credit against the widget's use of the frame
    spread = Uncertainty(
        type="lognormal", params={"loc": math.log(4.0), "scale": math.log(1.5), "negative": True}
    )
    credited = feeding(host(), "frame", "widget", -4.0, spread)
    draws = list(Serial().run(sampler(calculation, credited), range(30)))
    assert all(d.short == () for d in draws)


def looped_demand(key: str) -> list[DemandItem]:
    return [DemandItem(ref=BackgroundRef(database=LOOP_DB, id=LOOP_CODES[key]), amount=1.0)]


@pytest.fixture(scope="module")
def looped(tmp_path_factory: pytest.TempPathFactory) -> Calculation:
    return Calculation(looped_background(tmp_path_factory.mktemp("looped")))


def test_a_draw_in_which_a_background_loop_delivers_nothing_is_dropped_for_every_demand(
    looped: Calculation,
) -> None:
    pellets = list(
        Serial().run(
            sampler(looped, None, looped_demand("pellet"), methods=[LOOP_METHOD]), range(40)
        )
    )
    dropped = [d.index for d in pellets if d.scores is None]
    assert dropped
    members = {LOOP_CODES["pellet"], LOOP_CODES["heat"]}
    assert all(d.failing and set(d.failing) <= members for d in pellets if d.scores is None)
    assert all(d.scores[0] > 0 for d in pellets if d.scores is not None)
    elec = list(
        Serial().run(sampler(looped, None, looped_demand("elec"), methods=[LOOP_METHOD]), range(40))
    )
    assert [d.index for d in elec if d.scores is None] == dropped
    fixed = sampler(
        looped, None, looped_demand("pellet"), methods=[LOOP_METHOD], scope="biosphere_only"
    )
    assert all(d.scores is not None for d in Serial().run(fixed, range(5)))


def test_a_loop_solved_through_the_draw_solve_drops_what_its_block_drops(
    looped: Calculation,
) -> None:
    def run(dense: int) -> list[Draw]:
        mc = sampler(looped, None, looped_demand("pellet"), methods=[LOOP_METHOD], dense=dense)
        return list(Serial().run(mc, range(40)))

    on_blocks, through_solve = run(DENSE), run(1)
    assert [d.failing for d in through_solve] == [d.failing for d in on_blocks]
    assert scores(through_solve) == pytest.approx(scores(on_blocks), rel=1e-12)


def test_a_full_draw_solves_once_and_a_biosphere_draw_never(calculation: Calculation) -> None:
    foreground = calculation.foreground(host(), {})
    for scope, expected in (("full", 6), ("biosphere_only", 0)):
        counted = Counted(Refactorised("superlu"))
        mc = MonteCarlo(
            calculation,
            foreground,
            WIDGET,
            [GWP_METHOD],
            scope=scope,
            seed=5,
            solve=counted,
        )
        list(Serial().run(mc, range(6)))
        assert counted.calls == expected


def test_a_draw_solve_factorises_each_draw_and_never_the_stated_technosphere(
    calculation: Calculation, monkeypatch: pytest.MonkeyPatch
) -> None:
    factorised: list[sp.csr_matrix] = []

    class Recorded(Solver):
        """A solver that records each technosphere it factorises."""

        def refit(self, technosphere):
            factorised.append(technosphere)
            super().refit(technosphere)

    monkeypatch.setattr("ecosemantic.engine.montecarlo.Solver", Recorded)
    foreground = calculation.foreground(host(), {})
    for scope, expected in (("full", 6), ("biosphere_only", 0)):
        factorised.clear()
        mc = MonteCarlo(
            calculation,
            foreground,
            WIDGET,
            [GWP_METHOD],
            scope=scope,
            seed=5,
            solve=Refactorised("superlu"),
        )
        list(Serial().run(mc, range(6)))
        assert len(factorised) == expected
        assert all(t is not calculation.technosphere for t in factorised)


def test_a_draw_solve_refuses_a_solver_it_does_not_know_when_built() -> None:
    with pytest.raises(Invalid, match="solver is one of"):
        Refactorised("umfpack")


@needs_pardiso
def test_draws_under_pardiso_score_what_draws_under_superlu_score(
    calculation: Calculation,
) -> None:
    foreground = calculation.foreground(host(), {})

    def run(name: str) -> list[float | None]:
        mc = MonteCarlo(
            calculation,
            foreground,
            WIDGET,
            [GWP_METHOD],
            scope="full",
            seed=5,
            solve=Refactorised(name),
        )
        return scores(list(Serial().run(mc, range(6))))

    assert run("pardiso") == pytest.approx(run("superlu"), rel=1e-12)


def test_a_method_the_background_does_not_hold_is_not_found(calculation: Calculation) -> None:
    missing = Method.of(("fixture", "missing", "nothing"), "kg")
    with pytest.raises(NotFound, match="lacks methods"):
        sampler(calculation, host(), methods=[missing])


def test_a_foreground_demand_without_a_product_system_is_invalid(
    calculation: Calculation,
) -> None:
    with pytest.raises(Invalid, match="has no product system"):
        sampler(calculation, None)


def test_a_range_that_reaches_its_own_use_is_refused_before_sampling(
    calculation: Calculation,
) -> None:
    reaching = feeding(host(), "widget", "widget", 0.9, uniform(0.6, 1.2))
    with pytest.raises(Invalid, match="widget can use as much of its own product as it makes"):
        sampler(calculation, reaching)
    # a range is recentred on the amount, so it stays below one when centred on 0.9
    sampler(calculation, feeding(host(), "widget", "widget", 0.9, uniform(0.82, 0.98)))
    # with the technosphere held fixed, no range is judged
    sampler(calculation, reaching, scope="biosphere_only")
    # a loop holding a credit is not decided: the frame co-produces two to six widgets
    sampler(calculation, feeding(host(), "frame", "widget", -4.0, uniform(-6.0, -2.0)))


def test_a_range_that_takes_a_loop_to_its_threshold_is_refused_before_sampling(
    calculation: Calculation,
) -> None:
    # the widget uses 0.25 frame, so a frame using 3.6 widgets has a gain of 0.9, and up to 1.2
    # across a uniform range from 2.4 to 4.8
    with pytest.raises(Invalid, match="frame, widget feed each other"):
        sampler(calculation, feeding(host(), "frame", "widget", 3.6, uniform(2.4, 4.8)))
    peaked = Uncertainty(type="triangular", params={"minimum": 2.4, "loc": 3.6, "maximum": 3.9})
    sampler(calculation, feeding(host(), "frame", "widget", 3.6, peaked))


def test_a_distribution_centred_on_zero_that_must_follow_an_amount_is_invalid(
    calculation: Calculation,
) -> None:
    centred = with_direct_co2(host(), Uncertainty(type="normal", params={"loc": 0.0, "scale": 0.5}))
    with pytest.raises(Invalid, match="centred on 0"):
        sampler(calculation, centred)


def test_a_singular_loop_block_is_invalid_naming_the_draw() -> None:
    with pytest.raises(Invalid, match="draw 7 leaves a loop of 2 activities singular"):
        on_block(block=np.ones((2, 2)), signs=np.ones(2), k=7)
