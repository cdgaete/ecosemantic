"""A method family's weighting sets: how openLCA applies one, and the total each gives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ecosemantic.compute.montecarlo import summarize_samples
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import (
    MonteCarloResult,
    MonteCarloSummary,
    MonteCarloTotal,
    Score,
    Total,
    WeightingFactor,
    WeightingSet,
)


def _parts(factor: WeightingFactor) -> tuple[float, float | None] | None:
    """A factor's weight and the normalisation it states, or nothing when it gives its category no
    part in the total: the set states no weight for it, weights it at 0, or normalises it by 0."""
    if factor.weighting is None or factor.weighting == 0 or factor.normalisation == 0:
        return None
    return factor.weighting, factor.normalisation


def _taking(weighting: WeightingSet) -> list[tuple[WeightingFactor, float, float | None]]:
    """Every factor of the set that gives its category a part in the total, in the set's order, with
    its weight and the normalisation it states."""
    held: list[tuple[WeightingFactor, float, float | None]] = []
    for factor in weighting.factors:
        parts = _parts(factor)
        if parts is None:
            continue
        held.append((factor, *parts))
    return held


def _score_of(scores: Mapping[str, float], weighting: WeightingSet, method_id: str) -> float:
    """One category's score, or Invalid when the scores hold none for a category the set weights."""
    score = scores.get(method_id)
    if score is None:
        raise Invalid(
            f"the set {weighting.name!r} weights {method_id!r}, and the scores hold no such method"
        )
    return score


def weighted_sum(weighting: WeightingSet, scores: Mapping[str, float]) -> float:
    """The set's total over the categories it weights: each score divided by the normalisation the
    set states for it, not divided where it states none, and multiplied by its weight."""
    total = 0.0
    for factor, weight, normalisation in _taking(weighting):
        score = _score_of(scores, weighting, factor.method_id)
        total += (score if normalisation is None else score / normalisation) * weight
    return total


def _unit_of(methods: Sequence[Method], method_id: str) -> str:
    """The unit the method a category answers in is stated in, or Invalid naming a method the family
    does not hold."""
    for method in methods:
        if method.id == method_id:
            return method.unit
    raise Invalid(f"the set weights {method_id!r}, and the methods hold no such method")


def _unit(
    weighting: WeightingSet, taking: Sequence[WeightingFactor], methods: Sequence[Method]
) -> tuple[str | None, str | None]:
    """The unit a set's total answers in and, when it gives no total, why: the unit the set names;
    else none for a set that normalises every category it weights, its total being dimensionless;
    else the unit its unnormalised categories share, and no total when they share none."""
    if weighting.unit is not None:
        return weighting.unit, None
    unnormalised = [factor for factor in taking if factor.normalisation is None]
    if not unnormalised:
        return None, None
    units = sorted({_unit_of(methods, factor.method_id) for factor in unnormalised})
    if len(units) == 1:
        return units[0], None
    return None, f"its categories are in {', '.join(units)} and it names no unit"


def _identity(weighting: WeightingSet, position: int, methods: Sequence[Method]) -> Total:
    """A set's total without a value: the set, its place, the categories that take part, those it
    normalises by 0, and the unit or the reason it gives no total."""
    taking = [factor for factor, _weight, _normalisation in _taking(weighting)]
    zero = [
        factor.method_id
        for factor in weighting.factors
        if factor.weighting not in (None, 0) and factor.normalisation == 0
    ]
    unit, reason = (
        (weighting.unit, "weights no category") if not taking else _unit(weighting, taking, methods)
    )
    return Total(
        impact_method=weighting.impact_method,
        weighting_set=weighting.name,
        position=position,
        unit=unit,
        value=None,
        categories=[factor.method_id for factor in taking],
        normalised_by_zero=zero,
        reason=reason,
    )


def total_of(
    weighting: WeightingSet,
    position: int,
    methods: Sequence[Method],
    scores: Mapping[str, float],
) -> Total:
    """The total a set gives at its place in the family: its weighted sum over the categories it
    weights, or the reason it gives none — it weights no category, or its unnormalised categories
    share no unit and it names none."""
    identified = _identity(weighting, position, methods)
    if identified.reason is not None:
        return identified
    return identified.model_copy(update={"value": weighted_sum(weighting, scores)})


def totals_of(
    weightings: Sequence[WeightingSet], methods: Sequence[Method], scores: Sequence[Score]
) -> list[Total]:
    """One total per weighting set of a family, in the bundle's order of its sets, over the scores
    each category answers."""
    by_method = {score.method_id: score.value for score in scores}
    return [
        total_of(weighting, position, methods, by_method)
        for position, weighting in enumerate(weightings)
    ]


def total_deltas(base: Sequence[Total], variant: Sequence[Total]) -> list[float | None]:
    """How far each of a variant's totals moved, in the variant's order: each total less the
    base's total of the same set, matched by position, and none where either gives no total."""
    base_values = {total.position: total.value for total in base}
    held: list[float | None] = []
    for total in variant:
        base_value = base_values.get(total.position)
        held.append(None if total.value is None or base_value is None else total.value - base_value)
    return held


def _drawn_scores(result: MonteCarloResult, at: int) -> dict[str, float]:
    """Every category's sample at one draw."""
    return {category.method_id: category.sampled()[at] for category in result.categories}


def _monte_carlo_total(
    identity: Total, summary: MonteCarloSummary | None, samples: list[float] | None
) -> MonteCarloTotal:
    """A set's total over a run's draws, its identity taken from the total the same set gives
    deterministically."""
    return MonteCarloTotal(
        impact_method=identity.impact_method,
        weighting_set=identity.weighting_set,
        position=identity.position,
        unit=identity.unit,
        categories=identity.categories,
        normalised_by_zero=identity.normalised_by_zero,
        summary=summary,
        samples=samples,
        reason=identity.reason,
    )


def with_totals(
    result: MonteCarloResult, weightings: Sequence[WeightingSet], methods: Sequence[Method]
) -> MonteCarloResult:
    """The result with one total per weighting set: each draw's weighted sum over the categories the
    set weights, summarised as a category is, and a set that gives no total with the reason it gives
    none. No total takes part in the stop rule."""
    totals: list[MonteCarloTotal] = []
    for position, weighting in enumerate(weightings):
        identity = _identity(weighting, position, methods)
        if identity.reason is not None:
            totals.append(_monte_carlo_total(identity, None, None))
            continue
        samples = [weighted_sum(weighting, _drawn_scores(result, at)) for at in range(result.n)]
        totals.append(_monte_carlo_total(identity, summarize_samples(samples), samples))
    return result.model_copy(update={"totals": totals})
