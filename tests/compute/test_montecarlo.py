from __future__ import annotations

import math

import pytest

from ecosemantic.compute.montecarlo import (
    Holding,
    Standing,
    constant,
    median_ranks,
    paired_delta,
    paired_samples,
    should_stop,
    standing,
    summarize_samples,
)
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import MonteCarloCategory, MonteCarloResult
from tests.conftest import drawn_counts
from tests.fixture_data import FIXTURE_DATABASE

Z95 = 1.959963984540054
# one draw near a loop's crossing among 199 ordinary ones
HEAVY_TAIL = [1.0 + i / 1000 for i in range(199)] + [10_000.0]


def test_summary_of_a_constant_stream() -> None:
    s = summarize_samples([2.0] * 6)
    assert s.n == 6
    assert s.mean == 2.0
    assert s.median == 2.0
    assert s.median_ci95 == (2.0, 2.0)
    assert s.rel_se == 0.0
    assert s.percentiles == (2.0, 2.0)


def test_the_median_has_an_interval_from_six_samples() -> None:
    # the extreme pair of five samples covers the median 1 - 2 / 2**5 = 93.75 % of the time
    five = summarize_samples([5.0, 1.0, 4.0, 2.0, 3.0])
    assert five.median_ci95 is None and five.rel_se is None
    six = summarize_samples([5.0, 1.0, 6.0, 4.0, 2.0, 3.0])
    assert six.median_ci95 == (1.0, 6.0)


def test_the_median_interval_is_the_narrowest_pair_of_ranks_covering_95_percent() -> None:
    assert median_ranks(5) is None
    for n, ranks in (
        (6, (1, 6)),
        (30, (10, 21)),
        (100, (40, 61)),
        (200, (86, 115)),
        (1000, (469, 532)),
    ):
        assert median_ranks(n) == ranks
        low, high = ranks
        assert sum(math.comb(n, k) for k in range(low, high)) / 2**n >= 0.95
        assert sum(math.comb(n, k) for k in range(low + 1, high - 1)) / 2**n < 0.95


def test_the_relative_standard_error_is_the_half_width_of_the_median_interval_over_1_96() -> None:
    s = summarize_samples([float(x) for x in range(1, 101)])
    assert s.median == 50.5
    # the 40th and the 61st of 1..100
    assert s.median_ci95 == (40.0, 61.0)
    assert s.rel_se == pytest.approx(21 / (2 * Z95 * 50.5))
    assert s.mean == 50.5
    assert s.percentiles == (pytest.approx(3.475), pytest.approx(97.525))


def test_a_negative_median_has_an_ordered_interval_and_a_positive_relative_error() -> None:
    s = summarize_samples([-float(x) for x in range(1, 101)])
    assert s.median == -50.5
    assert s.median_ci95 == (-61.0, -40.0)
    assert s.rel_se == pytest.approx(21 / (2 * Z95 * 50.5))


def test_a_heavy_tail_moves_the_mean_beyond_the_percentiles_and_leaves_the_median() -> None:
    s = summarize_samples(HEAVY_TAIL)
    # (199 + 19.701 + 10,000) / 200
    assert s.mean == pytest.approx(51.0935)
    assert s.percentiles[1] < 1.2
    assert s.median == pytest.approx(1.0995)
    # the 86th and the 115th of 200
    assert s.median_ci95 == (pytest.approx(1.085), pytest.approx(1.114))
    assert s.rel_se == pytest.approx(0.029 / (2 * Z95 * 1.0995))


def test_a_median_of_zero_has_an_interval_and_no_relative_error() -> None:
    s = summarize_samples([-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0])
    assert s.median == 0.0
    assert s.median_ci95 == (-3.0, 3.0)
    assert s.rel_se is None


def test_summary_of_a_single_sample_has_no_interval() -> None:
    s = summarize_samples([3.0])
    assert s.median_ci95 is None and s.rel_se is None
    assert s.percentiles == (3.0, 3.0)


def test_summary_rejects_empty() -> None:
    with pytest.raises(Invalid):
        summarize_samples([])


TIGHT = [1.0 + 0.01 * (i % 3) for i in range(30)]
# thirty draws in six symmetric triples about 0: its median's interval holds 0
ABOUT_ZERO = [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0] * 5


def test_stop_rule_gates_on_the_worst_category() -> None:
    tight = [1.0, 1.01, 0.99, 1.0, 1.02, 0.98]
    loose = [1.0, 2.0, 0.5, 1.5, 0.7, 1.8]
    met = standing([tight, loose])
    assert met.worst == 1
    assert not should_stop(met, 6, 6, 0.05)
    assert should_stop(standing([tight, tight]), 6, 6, 0.05)
    assert not should_stop(standing([tight, tight]), 5, 6, 0.05)


def test_a_category_below_six_draws_is_unmeasured() -> None:
    met = standing([[1.0, 2.0, 0.5, 1.5, 0.7]])
    assert met.unmeasured == [0] and met.worst_rel_se is None and met.worst is None
    assert not should_stop(met, 5, 6, 0.05)


def test_the_stop_rule_stops_through_a_heavy_tail() -> None:
    assert should_stop(standing([HEAVY_TAIL]), 200, 30, 0.05)


def test_a_constant_category_counts_as_met() -> None:
    met = standing([[2.0] * 30, TIGHT])
    assert met.constant == [0] and met.near_zero == [] and met.unmeasured == []
    assert met.worst == 1 and met.worst_rel_se is not None
    assert should_stop(met, 30, 6, 0.05)


def test_draws_equal_within_1e_12_are_constant() -> None:
    assert constant([1.0, 1.0 + 1e-13] * 3)
    assert not constant([1.0, 1.0 + 1e-11])
    assert constant([0.0] * 30)


def test_a_median_indistinguishable_from_zero_is_left_out_and_named() -> None:
    met = standing([TIGHT, ABOUT_ZERO])
    assert met.near_zero == [1] and met.constant == []
    assert met.worst == 0 and met.worst_rel_se is not None
    assert should_stop(met, 30, 6, 0.05)


def test_a_category_returns_to_the_rule_when_its_interval_leaves_zero() -> None:
    prefix = [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0, -3.0, -2.0, -1.0, 1.0]
    assert standing([prefix]).near_zero == [0]
    later = prefix + [5.0 + 0.01 * (i % 3) for i in range(390)]
    met = standing([later])
    assert met.near_zero == [] and met.unmeasured == []
    assert met.worst == 0 and met.worst_rel_se is not None
    assert should_stop(met, 400, 6, 0.05)


def test_a_run_with_nothing_to_measure_stops_at_n_min() -> None:
    five = standing([[0.0] * 5, [-3.0, -2.0, -1.0, 1.0, 2.0]])
    # a median's interval needs six draws, so the second is unmeasured at five
    assert five.constant == [0] and five.near_zero == [] and five.unmeasured == [1]
    assert not should_stop(five, 5, 6, 0.05)
    met = standing([[0.0] * 6, [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0]])
    assert met.constant == [0] and met.near_zero == [1] and met.unmeasured == []
    assert met.worst_rel_se is None and met.worst is None
    assert should_stop(met, 6, 6, 0.05)


def _check(worst: int | None, error: float | None) -> Standing:
    """A check of the stop rule as a run makes it: one category measured, or none."""
    return Standing(worst_rel_se=error, worst=worst, constant=[], near_zero=[], unmeasured=[])


def test_the_category_that_held_the_run_longest() -> None:
    holding = Holding()
    for draw in range(1, 101):
        if draw <= 50:
            holding.observe(_check(1, 0.3), 0.05)
        elif draw <= 80:
            holding.observe(_check(0, 0.2), 0.05)
        else:
            holding.observe(_check(0, 0.01), 0.05)
    assert holding.longest() == 0
    never = Holding()
    for _ in range(10):
        never.observe(_check(0, 0.01), 0.05)
    assert never.longest() is None


def test_paired_delta_is_the_median_of_the_draw_by_draw_differences() -> None:
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    # every pair moves by 0.5 but the last, which a draw near a loop's crossing takes far
    variant = [1.5, 2.5, 3.5, 4.5, 5.5, 1000.0]
    d = paired_delta(base, variant)
    assert d.delta_abs == 0.5
    assert d.delta_pct == pytest.approx(0.5 / 3.5 * 100.0)
    assert d.delta_ci95 == (0.5, 994.0)
    assert paired_delta(base[:5], variant[:5]).delta_ci95 is None
    assert paired_delta([-1.0, 1.0], [0.0, 2.0]).delta_pct is None
    with pytest.raises(Invalid):
        paired_delta([1.0], [1.0, 2.0])


def _sampled(samples: list[float], dropped: list[int]) -> MonteCarloResult:
    method = Method.of(("db", "IPCC", "climate change", "climate change"), "kg CO2-Eq")
    return MonteCarloResult(
        database=FIXTURE_DATABASE,
        n=len(samples),
        stopped="fixed",
        gating_method=None,
        constant=[],
        indistinguishable_from_zero=[],
        scope="full",
        drawn=drawn_counts(),
        credit_loops=[],
        dropped_draws=dropped,
        dropped_loops=[["widget"]] if dropped else [],
        dropped_background=[],
        categories=[
            MonteCarloCategory(
                method_id=method.id, summary=summarize_samples(samples), samples=samples
            )
        ],
    )


def test_a_variant_pairs_with_its_base_on_the_draws_both_kept() -> None:
    # four draws: the base dropped draw 1, the variant draw 2
    base = _sampled([10.0, 12.0, 13.0], [1])
    variant = _sampled([20.0, 21.0, 23.0], [2])
    assert base.draws() == [0, 2, 3] and variant.draws() == [0, 1, 3]
    assert paired_samples(base, variant, 0) == ([10.0, 13.0], [20.0, 23.0])
