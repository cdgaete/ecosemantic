import math
import uuid

import pytest

from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.compute.overrides import apply_case
from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import (
    Case,
    Exchange,
    Method,
    Parameter,
    Process,
    ProductSystem,
    Uncertainty,
)
from ecosemantic.model.refs import BackgroundRef, DemandItem, ElementaryFlowRef, ForegroundRef
from ecosemantic.ports.types import (
    Drawn,
    DrawnCount,
    LinkedLoop,
    MonteCarloConfig,
    System,
)
from tests.conftest import fixture_system, frame_system, uid, widget_linking
from tests.engine.test_montecarlo import feeding, lognormal, looped_demand
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS, LOOP_DB

GWP = Method.of(("fixture", "gwp", "climate change", "GWP100"), "kg CO2-Eq")
WATER = Method.of(("fixture", "water", "water use", "m3"), "m3")
LOOP_GWP = Method.of(("looped", "gwp", "climate change", "GWP100"), "kg CO2-Eq")
WIDGET = [DemandItem(ref=ForegroundRef(code="widget"), amount=1.0)]


@pytest.fixture
def calculation(native_store: NativeStore) -> NativeCalculation:
    return NativeCalculation(native_store)


def host() -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    return system


async def test_a_fixed_count_at_a_seed_reproduces(calculation: NativeCalculation) -> None:
    config = MonteCarloConfig(n=8, seed=7)
    first = await calculation.monte_carlo(fixture_system(), WIDGET, [GWP, WATER], config)
    again = await calculation.monte_carlo(fixture_system(), WIDGET, [GWP, WATER], config)
    assert first.n == 8 and first.stopped == "fixed" and first.scope == "full"
    assert [c.samples for c in first.categories] == [c.samples for c in again.categories]
    assert first.categories[0].method_id == GWP.id
    assert first.gating_method is None
    assert first.categories[0].summary.mean == pytest.approx(4.158, rel=0.2)
    assert first.categories[1].samples == pytest.approx([0.0] * 8)


async def test_a_run_says_why_it_stopped_and_reports_its_progress(
    calculation: NativeCalculation,
) -> None:
    reached = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n_min=6, n_max=40, rel_se_target=1.0)
    )
    # the median has no interval below six samples, so no target is reached sooner
    assert reached.stopped == "target" and reached.n == 6
    capped = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n_min=6, n_max=6, rel_se_target=1e-9)
    )
    assert capped.stopped == "ceiling" and capped.n == 6
    progress: list[tuple[int, float | None]] = []

    def watch(done: int, worst: float | None) -> bool:
        progress.append((done, worst))
        return done < 7

    cancelled = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n=10), on_iteration=watch
    )
    assert cancelled.stopped == "cancelled" and cancelled.n == 7
    assert [done for done, _ in progress] == [1, 2, 3, 4, 5, 6, 7]
    assert [worst for _, worst in progress[:5]] == [None] * 5
    assert all(worst is not None and worst > 0 for _, worst in progress[5:])


async def test_the_result_counts_the_background_normals_sampled_at_their_amount(
    calculation: NativeCalculation,
) -> None:
    full = await calculation.monte_carlo(fixture_system(), WIDGET, [GWP], MonteCarloConfig(n=2))
    held = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n=2, scope="biosphere_only")
    )
    # one wide technosphere normal and one wide biosphere normal in the fixture
    assert full.drawn.background.held == 2 and held.drawn.background.held == 1


def counted_system() -> ProductSystem:
    """The fixture widget taking a quarter kilogram of frame from an uncertain parameter, its
    0.1 kg of CO2 drawn beside the steel's own lognormal."""
    system = host().model_copy(deep=True, update={"hash": None})
    widget = system.process("widget")
    widget.exchanges[3].formula = "frame_mass"
    widget.exchanges[4].uncertainty = Uncertainty(
        type="lognormal", params={"loc": math.log(0.1), "scale": 0.1}
    )
    system.parameters = [
        Parameter(
            name="frame_mass",
            value=0.25,
            unit="kilogram",
            uncertainty=Uncertainty(
                type="lognormal", params={"loc": math.log(0.25), "scale": 0.05}
            ),
        )
    ]
    return system


async def test_a_run_counts_what_it_drew(calculation: NativeCalculation) -> None:
    system = counted_system()
    full = await calculation.monte_carlo(System.of(system), WIDGET, [GWP], MonteCarloConfig(n=2))
    assert full.drawn == Drawn(
        parameters=DrawnCount(there=1, carried=1, drawn=1),
        foreground=DrawnCount(there=7, carried=2, drawn=2),
        background=DrawnCount(there=6, carried=2, drawn=0, held=2),
    )
    fixed = await calculation.monte_carlo(
        System.of(system), WIDGET, [GWP], MonteCarloConfig(n=2, scope="biosphere_only")
    )
    # only the elementary exchange is drawn, so the parameter the frame's amount reads is not
    assert fixed.drawn == Drawn(
        parameters=DrawnCount(there=1, carried=1, drawn=0),
        foreground=DrawnCount(there=7, carried=2, drawn=1),
        background=DrawnCount(there=6, carried=2, drawn=0, held=1),
    )


async def test_a_parameter_centred_on_0_at_0_is_drawn(calculation: NativeCalculation) -> None:
    system = host().model_copy(deep=True, update={"hash": None})
    steel = system.process("widget").exchanges[1]
    steel.formula = "offset + 0.5"
    steel.amount = 0.5
    steel.uncertainty = None
    system.parameters = [
        Parameter(
            name="offset",
            value=0.0,
            unit="kilogram",
            uncertainty=Uncertainty(type="normal", params={"loc": 0.0, "scale": 0.1}),
        )
    ]
    result = await calculation.monte_carlo(System.of(system), WIDGET, [GWP], MonteCarloConfig(n=8))
    assert result.drawn.parameters == DrawnCount(there=1, carried=1, drawn=1)
    samples = result.categories[0].samples
    assert samples is not None and len(set(samples)) > 1


async def test_a_parameter_no_sampled_exchange_reads_is_carried_not_drawn(
    calculation: NativeCalculation,
) -> None:
    # under biosphere_only the frame's amount is not taken from the formulas, so the parameter
    # its exchange reads is carried and not drawn
    system = counted_system()
    fixed = await calculation.monte_carlo(
        System.of(system), WIDGET, [GWP], MonteCarloConfig(n=2, scope="biosphere_only")
    )
    assert fixed.drawn.parameters == DrawnCount(there=1, carried=1, drawn=0)
    # a case that sets a parameter centred elsewhere to none leaves it no distribution to carry
    variant = apply_case(system, Case(name="none", values={"frame_mass": 0.0}))
    result = await calculation.monte_carlo(System.of(variant), WIDGET, [GWP], MonteCarloConfig(n=2))
    assert result.drawn.parameters == DrawnCount(there=1, carried=0, drawn=0)


async def test_the_held_normals_are_counted_among_the_reached_background(
    calculation: NativeCalculation,
) -> None:
    # the fixture carries two normals wider than their amounts, on electricity's CO2 and on the
    # steel's electricity, and a lorry reaches neither
    background = System(database=FIXTURE_DB)
    lorry = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["lorry"]), amount=1.0)]
    result = await calculation.monte_carlo(background, lorry, [GWP], MonteCarloConfig(n=2))
    assert result.drawn.background == DrawnCount(there=3, carried=0, drawn=0)
    assert result.drawn.foreground == DrawnCount(there=0, carried=0, drawn=0)


async def test_a_constant_category_does_not_hold_a_run(calculation: NativeCalculation) -> None:
    result = await calculation.monte_carlo(
        fixture_system(),
        WIDGET,
        [GWP, WATER],
        MonteCarloConfig(n_min=6, n_max=200, rel_se_target=0.005),
    )
    # the widget's water score is 0 in every draw, so the rule has one category to measure
    assert result.stopped == "target" and 6 < result.n < 200
    assert result.constant == [WATER.id] and result.indistinguishable_from_zero == []
    assert result.gating_method == GWP.id


async def test_a_run_stopping_at_n_min_names_no_category_as_holding_it(
    calculation: NativeCalculation,
) -> None:
    checks: list[tuple[int, float | None]] = []

    def watch(done: int, worst: float | None) -> bool:
        checks.append((done, worst))
        return True

    result = await calculation.monte_carlo(
        fixture_system(),
        WIDGET,
        [GWP, WATER],
        MonteCarloConfig(n_min=30, n_max=60, rel_se_target=0.007),
        on_iteration=watch,
    )
    assert result.stopped == "target" and result.n == 30
    # the run was inside the rule's count until n_min, so n_min held it and no category did
    assert any(worst is not None and worst > 0.007 for done, worst in checks if done < 30)
    assert all(worst is not None and worst <= 0.007 for done, worst in checks if done >= 30)
    assert result.gating_method is None


def swing_system() -> ProductSystem:
    """A kilogram of swing emitting a kilogram of carbon dioxide and crediting another, each a
    normal of the same spread about its amount, so its climate score is symmetric about 0."""
    co2 = ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"])
    whole = fixture_system().product_system
    assert whole is not None

    def emission(n: int, amount: float) -> Exchange:
        return Exchange(
            id=uid("swing-ex", str(n)),
            type="elementary",
            name="Carbon dioxide, fossil",
            amount=amount,
            unit="kilogram",
            input=co2,
            uncertainty=Uncertainty(type="normal", params={"loc": amount, "scale": 0.5}),
        )

    swing = Process(
        id=uid("swing-act", "swing"),
        code="swing",
        name="swing",
        unit="unit",
        location="GLO",
        reference_product="swing",
        exchanges=[
            Exchange(
                id=uid("swing-ex", "product"),
                type="production",
                name="swing",
                amount=1.0,
                unit="unit",
            ),
            emission(0, 1.0),
            emission(1, -1.0),
        ],
    )
    return ProductSystem(
        id=uid("swing-product_system", "swing"),
        name="swing",
        database=whole.database,
        processes=[swing],
        reference_process="swing",
    )


async def test_a_fixed_run_reports_its_constant_and_left_out_categories_and_holds_no_category(
    calculation: NativeCalculation,
) -> None:
    result = await calculation.monte_carlo(
        System.of(swing_system()),
        [DemandItem(ref=ForegroundRef(code="swing"), amount=1.0)],
        [GWP, WATER],
        MonteCarloConfig(n=6),
    )
    assert result.stopped == "fixed" and result.n == 6
    assert result.constant == [WATER.id]
    assert result.indistinguishable_from_zero == [GWP.id]
    assert result.gating_method is None


async def test_a_run_refuses_a_parameter_that_cannot_be_drawn_naming_it_and_its_system(
    calculation: NativeCalculation,
) -> None:
    system = host().model_copy(deep=True, update={"hash": None})
    steel = system.process("widget").exchanges[1]
    steel.formula = "steel_kg"
    steel.uncertainty = None
    steel.amount = 0.5
    system.parameters = [
        Parameter(
            name="steel_kg",
            value=0.5,
            uncertainty=Uncertainty(
                type="lognormal",
                params={"loc": math.log(0.5), "scale": 3.0, "minimum": 0.4995, "maximum": 0.5005},
            ),
        )
    ]
    with pytest.raises(
        Invalid,
        match="parameter steel_kg of widget keeps drawing outside its bounds 0.4995 to 0.5005",
    ):
        await calculation.monte_carlo(System.of(system), WIDGET, [GWP], MonteCarloConfig(n=1))


async def test_a_run_names_the_loops_holding_a_credit(calculation: NativeCalculation) -> None:
    credited = host().model_copy(deep=True)
    # the frame co-produces four widgets, a negative input of widget
    credited.process("frame").exchanges.append(
        Exchange(
            id=uuid.uuid4(),
            type="product",
            name="widget",
            amount=-4.0,
            unit="unit",
            input=ForegroundRef(code="widget"),
        )
    )
    result = await calculation.monte_carlo(
        System.of(credited), WIDGET, [GWP], MonteCarloConfig(n=3)
    )
    assert result.credit_loops == [["frame", "widget"]]


async def test_a_draw_in_which_a_loop_delivers_nothing_is_dropped_and_named(
    calculation: NativeCalculation,
) -> None:
    # a lognormal own use of 0.5 at a geometric standard deviation of 1.5 reaches one in 4.4 %
    tail = feeding(host(), "widget", "widget", 0.5, lognormal(0.5, 1.5))
    result = await calculation.monte_carlo(System.of(tail), WIDGET, [GWP], MonteCarloConfig(n=200))
    assert result.dropped_draws and result.dropped_loops == [["widget"]]
    assert result.n == 200 - len(result.dropped_draws) == len(result.categories[0].samples)
    assert result.draws() == [d for d in range(200) if d not in result.dropped_draws]


async def test_a_loop_inside_a_linked_system_is_named_with_its_system_and_pin(
    calculation: NativeCalculation,
) -> None:
    frame = feeding(frame_system(), "frame", "frame", 0.5, lognormal(0.5, 1.5))
    pinned = frame.model_copy(update={"hash": content_hash(frame)})
    system = System.of(widget_linking(pinned), {pinned.id: pinned})
    result = await calculation.monte_carlo(system, WIDGET, [GWP], MonteCarloConfig(n=200))
    assert result.dropped_draws and result.dropped_loops == []
    assert result.dropped_linked_loops == [
        LinkedLoop(product_system_id=pinned.id, at_hash=content_hash(pinned), codes=["frame"])
    ]


async def test_a_run_that_drops_every_draw_is_invalid_naming_the_loop(
    calculation: NativeCalculation,
) -> None:
    wide = feeding(host(), "widget", "widget", 0.9, lognormal(0.9, 2.0))
    # under seed 0 the one draw of this wide own use lands at or above one
    config = MonteCarloConfig(n=1, seed=0)
    with pytest.raises(Invalid, match=r"all 1 draws were dropped: widget used as much"):
        await calculation.monte_carlo(System.of(wide), WIDGET, [GWP], config)


async def test_a_draw_a_background_loop_fails_in_is_dropped_naming_its_process(
    calculation: NativeCalculation,
) -> None:
    background = System(database=LOOP_DB)
    config = MonteCarloConfig(n=40)
    pellets = await calculation.monte_carlo(background, looped_demand("pellet"), [LOOP_GWP], config)
    assert pellets.dropped_draws and pellets.dropped_loops == []
    assert set(pellets.dropped_background) <= {"pellet production [GLO]", "heat production [GLO]"}
    assert pellets.dropped_background
    elec = await calculation.monte_carlo(background, looped_demand("elec"), [LOOP_GWP], config)
    assert elec.dropped_draws == pellets.dropped_draws
    held = await calculation.monte_carlo(
        background,
        looped_demand("pellet"),
        [LOOP_GWP],
        MonteCarloConfig(n=5, scope="biosphere_only"),
    )
    assert held.dropped_draws == [] and held.n == 5
