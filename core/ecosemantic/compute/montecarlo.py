"""Sample statistics for Monte Carlo runs: summaries, the stop rule, and paired deltas."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from functools import cache

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.ports.types import MonteCarloResult, MonteCarloSummary

Z95 = 1.959963984540054
EQUAL = 1e-12


class PairedDelta(BaseModel):
    """Variant minus base over iteration-aligned samples: the median of the differences, its
    95 % interval, and that median as a percentage of the base's median."""

    delta_abs: float
    delta_pct: float | None
    delta_ci95: tuple[float, float] | None


@cache
def median_ranks(n: int) -> tuple[int, int] | None:
    """The ranks, counted from one, of the two samples of n that bound the median with
    probability at least 0.95 whatever the distribution: the lowest rank l whose Binomial(n, 1/2)
    tail below it exceeds 2.5 %, and n + 1 - l. None below six samples, where no pair does."""
    below, term, rank, total = 0, 1, 0, 2**n
    while 40 * (below + term) <= total:
        below += term
        term = term * (n - rank) // (rank + 1)
        rank += 1
    return None if rank == 0 else (rank, n + 1 - rank)


def summarize_samples(samples: list[float]) -> MonteCarloSummary:
    """The median with its 95 % interval and relative standard error, the 2.5th and 97.5th
    percentiles, and the mean."""
    n = len(samples)
    if n == 0:
        raise Invalid("a summary needs at least one sample")
    ordered = sorted(samples)
    median = statistics.median(ordered)
    ranks = median_ranks(n)
    interval = None if ranks is None else (ordered[ranks[0] - 1], ordered[ranks[1] - 1])
    cuts = (
        statistics.quantiles(ordered, n=40, method="inclusive")
        if n > 1
        else [ordered[0], ordered[0]]
    )
    return MonteCarloSummary(
        n=n,
        mean=statistics.fmean(samples),
        median=median,
        median_ci95=interval,
        percentiles=(cuts[0], cuts[-1]),
        rel_se=None
        if interval is None or median == 0
        else (interval[1] - interval[0]) / (2 * Z95 * abs(median)),
    )


def constant(samples: Sequence[float]) -> bool:
    """True when every draw equals the rest within `EQUAL` of their magnitude: the largest less
    the smallest is at most `EQUAL` times the larger magnitude of the two, so thirty zeros are
    constant and so are draws a rounding apart."""
    if not samples:
        raise Invalid("the stop rule needs at least one sample per category")
    low, high = min(samples), max(samples)
    return high - low <= EQUAL * max(abs(low), abs(high))


def near_zero(summary: MonteCarloSummary) -> bool:
    """True when the median's 95 % interval exists and holds 0: no relative error then states how
    far from zero the median is."""
    interval = summary.median_ci95
    return interval is not None and interval[0] <= 0.0 <= interval[1]


class Standing(BaseModel):
    """The stop rule's reading of a run at one check: the largest relative standard error among
    the categories it can measure and that category, both None when it can measure none; the
    categories met as constant, every draw equal; those left out, their median indistinguishable
    from zero; and those unmeasured, under six draws, where a median has no interval. A constant
    category is never left out."""

    worst_rel_se: float | None
    worst: int | None
    constant: list[int]
    near_zero: list[int]
    unmeasured: list[int]


def standing(samples_by_category: list[list[float]]) -> Standing:
    """One check of the stop rule over every category's draws so far."""
    if not samples_by_category:
        raise Invalid("the stop rule needs at least one category")
    met: list[int] = []
    left_out: list[int] = []
    unmeasured: list[int] = []
    errors: dict[int, float] = {}
    for at, samples in enumerate(samples_by_category):
        if not samples:
            unmeasured.append(at)
        elif constant(samples):
            met.append(at)
        else:
            summary = summarize_samples(samples)
            if near_zero(summary):
                left_out.append(at)
            elif summary.rel_se is None:
                unmeasured.append(at)
            else:
                errors[at] = summary.rel_se
    worst = max(errors, key=errors.__getitem__) if errors else None
    return Standing(
        worst_rel_se=None if worst is None else errors[worst],
        worst=worst,
        constant=met,
        near_zero=left_out,
        unmeasured=unmeasured,
    )


def should_stop(standing: Standing, n: int, n_min: int, tau: float) -> bool:
    """True once the run has kept `n_min` draws and every category it can measure is within
    `tau`: none is unmeasured, and the worst relative standard error is at most `tau`, or none
    exists because no category is left to measure."""
    if n < n_min or standing.unmeasured:
        return False
    return standing.worst_rel_se is None or standing.worst_rel_se <= tau


class Holding:
    """The category that held a run, its median's error above the target at the latest check that
    found one; the standing names the largest error of that check, which breaks a tie."""

    def __init__(self) -> None:
        self._held: int | None = None

    def observe(self, standing: Standing, tau: float) -> None:
        """Take a check, keeping the category remembered when it finds none above `tau`."""
        if standing.worst_rel_se is not None and standing.worst_rel_se > tau:
            self._held = standing.worst

    def longest(self) -> int | None:
        """The category above the target at the latest check that found one, or None when no
        check found any."""
        return self._held


def paired_samples(
    base: MonteCarloResult, variant: MonteCarloResult, category: int
) -> tuple[list[float], list[float]]:
    """One category's samples of a base and a variant at the draws both kept, in draw order, so
    each pair shares its random numbers."""
    at_base = dict(zip(base.draws(), base.categories[category].sampled(), strict=True))
    at_variant = dict(zip(variant.draws(), variant.categories[category].sampled(), strict=True))
    common = sorted(at_base.keys() & at_variant.keys())
    return [at_base[d] for d in common], [at_variant[d] for d in common]


def paired_delta(base: list[float], variant: list[float]) -> PairedDelta:
    """Common-random-number delta of a variant against its base, on the median of the draw by
    draw differences; the interval is None below six pairs, and the percentage for a base whose
    median is zero."""
    if len(base) != len(variant):
        raise Invalid(f"paired streams differ in length: {len(base)} and {len(variant)}")
    summary = summarize_samples([v - b for b, v in zip(base, variant, strict=True)])
    base_median = statistics.median(base)
    return PairedDelta(
        delta_abs=summary.median,
        delta_pct=None if base_median == 0 else summary.median / base_median * 100.0,
        delta_ci95=summary.median_ci95,
    )
