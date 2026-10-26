from __future__ import annotations

import math

import pytest

from ecosemantic.compute.montecarlo import (
    median_ranks,
    paired_delta,
    paired_samples,
    should_stop,
    summarize_samples,
    worst_rel_se,
)
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import MonteCarloCategory, MonteCarloResult
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


def test_stop_rule_gates_on_the_worst_category() -> None:
    tight = [1.0, 1.01, 0.99, 1.0, 1.02, 0.98]
    loose = [1.0, 2.0, 0.5, 1.5, 0.7, 1.8]
    _, gating = worst_rel_se([tight, loose])
    assert gating == 1
    assert should_stop([tight, tight], n_min=6, tau=0.05)
    assert not should_stop([tight, loose], n_min=6, tau=0.05)
    assert not should_stop([tight, tight], n_min=10, tau=0.05)


def test_the_stop_rule_waits_for_six_samples_and_for_a_median_other_than_zero() -> None:
    assert not should_stop([[1.0] * 5], n_min=1, tau=0.05)
    assert should_stop([[1.0] * 6], n_min=1, tau=0.05)
    centred = [-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
    assert worst_rel_se([[1.0] * 7, centred]) == (None, 1)


def test_the_stop_rule_stops_through_a_heavy_tail() -> None:
    assert should_stop([HEAVY_TAIL], n_min=30, tau=0.05)


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
    method = Method.of(("db", "IPCC", "climate change"), "kg CO2-Eq")
    return MonteCarloResult(
        database=FIXTURE_DATABASE,
        n=len(samples),
        stopped="fixed",
        gating_method=method,
        scope="full",
        normals_at_amount=0,
        credit_loops=[],
        dropped_draws=dropped,
        dropped_loops=[["widget"]] if dropped else [],
        dropped_background=[],
        categories=[
            MonteCarloCategory(method=method, summary=summarize_samples(samples), samples=samples)
        ],
    )


def test_a_variant_pairs_with_its_base_on_the_draws_both_kept() -> None:
    # four draws: the base dropped draw 1, the variant draw 2
    base = _sampled([10.0, 12.0, 13.0], [1])
    variant = _sampled([20.0, 21.0, 23.0], [2])
    assert base.draws() == [0, 2, 3] and variant.draws() == [0, 1, 3]
    assert paired_samples(base, variant, 0) == ([10.0, 13.0], [20.0, 23.0])
