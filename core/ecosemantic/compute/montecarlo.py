"""Sample statistics for Monte Carlo runs: summaries, the stop rule, and paired deltas."""

from __future__ import annotations

import statistics
from functools import cache

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.ports.types import MonteCarloResult, MonteCarloSummary

Z95 = 1.959963984540054


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


def worst_rel_se(samples_by_category: list[list[float]]) -> tuple[float | None, int]:
    """The largest relative standard error of a category's median, and that category; None, and
    the first category without one, while any is undefined."""
    if not samples_by_category:
        raise Invalid("the stop rule needs at least one category")
    rel = [summarize_samples(cat).rel_se for cat in samples_by_category]
    defined = [r for r in rel if r is not None]
    if len(defined) < len(rel):
        return None, rel.index(None)
    gating = max(range(len(defined)), key=defined.__getitem__)
    return defined[gating], gating


def should_stop(samples_by_category: list[list[float]], n_min: int, tau: float) -> bool:
    """True once every category has n_min samples and the relative standard error of every
    median is within tau."""
    if len(samples_by_category[0]) < n_min:
        return False
    worst, _ = worst_rel_se(samples_by_category)
    return worst is not None and worst <= tau


def paired_samples(
    base: MonteCarloResult, variant: MonteCarloResult, category: int
) -> tuple[list[float], list[float]]:
    """One category's samples of a base and a variant at the draws both kept, in draw order, so
    each pair shares its random numbers."""
    at_base = dict(zip(base.draws(), base.categories[category].samples, strict=True))
    at_variant = dict(zip(variant.draws(), variant.categories[category].samples, strict=True))
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
