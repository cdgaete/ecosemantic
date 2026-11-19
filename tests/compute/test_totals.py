"""One total per weighting set of a method family: each category's score normalised and weighted by
the set's factors, over the categories the set weights, in the unit the set or its categories
name."""

from __future__ import annotations

import statistics

from ecosemantic.compute.montecarlo import summarize_samples
from ecosemantic.compute.totals import total_deltas, total_of, totals_of, weighted_sum, with_totals
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import (
    VALUE_CHOICES,
    MonteCarloCategory,
    MonteCarloResult,
    Score,
    WeightingFactor,
    WeightingSet,
)
from tests.conftest import drawn_counts
from tests.fixture_data import FIXTURE_DATABASE

FAMILY = "value choices"
CLIMATE = Method.of(("fixture", FAMILY, "climate change", "GWP100"), "kg CO2-Eq")
BIOGENIC = Method.of(("fixture", FAMILY, "climate change, biogenic", "GWP100"), "kg CO2-Eq")
WATER = Method.of(("fixture", FAMILY, "water use", "m3"), "m3")
METHODS = [CLIMATE, BIOGENIC, WATER]
SCORES = [
    Score(value=2.0, unit=CLIMATE.unit, method_id=CLIMATE.id),
    Score(value=5.0, unit=BIOGENIC.unit, method_id=BIOGENIC.id),
    Score(value=3.0, unit=WATER.unit, method_id=WATER.id),
]


def _factor(
    method: Method, weighting: float | None, normalisation: float | None
) -> WeightingFactor:
    return WeightingFactor(method_id=method.id, normalisation=normalisation, weighting=weighting)


def _set(name: str | None, *factors: WeightingFactor, unit: str | None = None) -> WeightingSet:
    return WeightingSet(impact_method=FAMILY, name=name, unit=unit, factors=list(factors))


def _scores() -> dict[str, float]:
    return {score.method_id: score.value for score in SCORES}


def test_each_set_gives_its_weighted_sum() -> None:
    alone = _set("climate alone", _factor(CLIMATE, 1.0, None))
    weighted = _set(
        "water and biogenic", _factor(BIOGENIC, 1.0, None), _factor(WATER, 2.0, None), unit="Pt"
    )

    totals = totals_of([alone, weighted], METHODS, SCORES)

    assert [(total.weighting_set, total.value) for total in totals] == [
        ("climate alone", 2.0),
        ("water and biogenic", 11.0),
    ]
    assert totals[0].categories == [CLIMATE.id]
    assert totals[1].categories == [BIOGENIC.id, WATER.id]
    assert totals[0].reason is None and totals[1].reason is None


def test_a_normalisation_divides_and_a_weight_multiplies() -> None:
    normalised = _set("normalised", _factor(CLIMATE, 3.0, 2.0))

    assert weighted_sum(normalised, _scores()) == 3.0
    assert total_of(normalised, 0, METHODS, _scores()).value == 3.0


def test_a_category_normalised_by_0_takes_no_part() -> None:
    by_zero = _set(
        "one normalised by 0",
        _factor(CLIMATE, 1.0, 0.0),
        _factor(WATER, 1.0, None),
        unit="UBP",
    )

    total = total_of(by_zero, 0, METHODS, _scores())

    assert total.value == 3.0
    assert total.categories == [WATER.id]
    assert total.normalised_by_zero == [CLIMATE.id]
    assert total.reason is None


def test_a_set_weighting_no_category_gives_no_total() -> None:
    normalisation_only = _set(
        "normalisation only", _factor(CLIMATE, None, 1.0e-4), _factor(WATER, 0.0, 1.0e-4)
    )

    total = total_of(normalisation_only, 0, METHODS, _scores())

    assert total.value is None
    assert total.reason == "weights no category"
    assert total.categories == []
    assert total.normalised_by_zero == []


def test_a_normalised_sets_total_states_no_unit() -> None:
    normalised = _set(
        "normalised",
        _factor(CLIMATE, 1.0, 2.0),
        _factor(WATER, 1.0, 3.0),
    )

    total = total_of(normalised, 0, METHODS, _scores())

    assert total.value == 2.0 / 2.0 + 3.0 / 3.0
    assert total.unit is None
    assert total.reason is None


def test_the_unit_is_the_one_the_categories_share() -> None:
    shared = _set("shared unit", _factor(CLIMATE, 1.0, None), _factor(BIOGENIC, 1.0, None))

    total = total_of(shared, 0, METHODS, _scores())

    assert total.unit == "kg CO2-Eq"
    assert total.value == 7.0


def test_a_set_whose_categories_differ_and_names_no_unit_gives_no_total() -> None:
    differ = _set("no unit", _factor(CLIMATE, 1.0, None), _factor(WATER, 1.0, None))

    total = total_of(differ, 0, METHODS, _scores())

    assert total.value is None
    assert total.unit is None
    assert total.reason == "its categories are in kg CO2-Eq, m3 and it names no unit"
    assert total.categories == [CLIMATE.id, WATER.id]


def test_an_unnamed_set_is_told_apart_by_its_position() -> None:
    first = _set(None, _factor(CLIMATE, 1.0, None))
    second = _set(None, _factor(WATER, 1.0, None))

    named = totals_of([first, second], METHODS, SCORES)

    assert [(total.weighting_set, total.position) for total in named] == [(None, 0), (None, 1)]
    assert [total.value for total in named] == [2.0, 3.0]


def test_a_variants_total_delta_is_its_total_less_the_bases() -> None:
    alone = _set("climate alone", _factor(CLIMATE, 1.0, None))
    both = _set(
        "water and biogenic", _factor(BIOGENIC, 1.0, None), _factor(WATER, 2.0, None), unit="Pt"
    )
    weighted = _set(
        "climate and water", _factor(CLIMATE, 2.0, None), _factor(WATER, 1.0, None), unit="Pt"
    )
    none = _set("no category", _factor(CLIMATE, 0.0, None))
    moved = [
        Score(value=5.0, unit=CLIMATE.unit, method_id=CLIMATE.id),
        Score(value=6.0, unit=BIOGENIC.unit, method_id=BIOGENIC.id),
        Score(value=6.0, unit=WATER.unit, method_id=WATER.id),
    ]
    base = totals_of([alone, none, both, weighted], METHODS, SCORES)
    variant = totals_of([alone, both, none, weighted], METHODS, moved)
    base.reverse()

    assert [total.position for total in base] == [3, 2, 1, 0]
    assert [total.value for total in base] == [7.0, 11.0, None, 2.0]
    assert [total.value for total in variant] == [5.0, 18.0, None, 16.0]
    assert total_deltas(base, variant) == [3.0, None, None, 9.0]


def _sampled(samples_by_method: dict[str, list[float]]) -> MonteCarloResult:
    n = len(next(iter(samples_by_method.values())))
    return MonteCarloResult(
        database=FIXTURE_DATABASE,
        n=n,
        stopped="fixed",
        gating_method=None,
        constant=[],
        indistinguishable_from_zero=[],
        scope="full",
        drawn=drawn_counts(),
        credit_loops=[],
        dropped_draws=[],
        dropped_loops=[],
        dropped_background=[],
        categories=[
            MonteCarloCategory(
                method_id=method_id, summary=summarize_samples(samples), samples=samples
            )
            for method_id, samples in samples_by_method.items()
        ],
    )


def test_a_monte_carlo_total_summarises_each_draws_sum() -> None:
    climate = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    water = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    result = _sampled({CLIMATE.id: climate, WATER.id: water})
    both = _set("both", _factor(CLIMATE, 0.5, None), _factor(WATER, 2.0, None), unit="Pt")

    drawn = with_totals(result, [both], METHODS)

    total = drawn.totals[0]
    sums = [0.5 * c + 2.0 * w for c, w in zip(climate, water, strict=True)]
    assert total.samples == sums
    assert total.histogram is None
    assert total.summary is not None
    assert total.summary.median == statistics.median(sums)
    assert total.unit == "Pt"
    assert total.value_choices == VALUE_CHOICES
    assert drawn.categories[0].samples == climate

    without = drawn.without_samples()
    assert without.totals[0].samples is None
    assert without.totals[0].histogram is not None
    assert sum(without.totals[0].histogram.counts) == len(sums)
    assert without.totals[0].summary == total.summary
