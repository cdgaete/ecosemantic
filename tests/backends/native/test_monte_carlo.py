import uuid

import pytest

from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import DemandItem, Exchange, Method, ProductSystem
from ecosemantic.model.refs import ForegroundRef
from ecosemantic.ports.types import LinkedLoop, MonteCarloConfig, System
from tests.conftest import fixture_system, frame_system, widget_linking
from tests.engine.test_montecarlo import feeding, lognormal, looped_demand
from tests.fixture_data import LOOP_DB

GWP = Method.of(("fixture", "gwp", "climate change > GWP100"), "kg CO2-Eq")
WATER = Method.of(("fixture", "water", "water use > m3"), "m3")
LOOP_GWP = Method.of(("looped", "gwp", "climate change > GWP100"), "kg CO2-Eq")
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
    assert first.categories[0].method == GWP
    assert first.categories[0].summary.mean == pytest.approx(4.158, rel=0.2)
    assert first.categories[1].samples == pytest.approx([0.0] * 8)


async def test_a_run_says_why_it_stopped_and_reports_its_progress(
    calculation: NativeCalculation,
) -> None:
    reached = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n_min=3, n_max=40, rel_se_target=1.0)
    )
    # the median has no interval below six samples, so no target is reached sooner
    assert reached.stopped == "target" and reached.n == 6
    capped = await calculation.monte_carlo(
        fixture_system(), WIDGET, [GWP], MonteCarloConfig(n_min=2, n_max=4, rel_se_target=1e-9)
    )
    assert capped.stopped == "ceiling" and capped.n == 4
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
    assert full.normals_at_amount == 2 and held.normals_at_amount == 1


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
