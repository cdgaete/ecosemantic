from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecosemantic.compute.results import ContributionResult, cut_below
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.ports.types import Hotspot, Score
from tests.fixture_data import FIXTURE_DATABASE

GWP = Method.of(("db", "IPCC", "climate change"), "kg CO2-Eq")
TOTAL = Score(value=1.0, unit="kg CO2-Eq", method=GWP)


def test_a_decomposition_carries_the_rows_its_axis_names_and_no_others() -> None:
    assert (
        ContributionResult(
            database=FIXTURE_DATABASE, by="process", total=TOTAL, processes=[], credit_loops=[]
        ).processes
        == []
    )
    with pytest.raises(ValidationError, match="by='process' carries processes"):
        ContributionResult(database=FIXTURE_DATABASE, by="process", total=TOTAL, credit_loops=[])
    with pytest.raises(ValidationError, match="by='flow' carries flows"):
        ContributionResult(
            database=FIXTURE_DATABASE, by="flow", total=TOTAL, processes=[], credit_loops=[]
        )


def _hotspot(rank: int, fraction: float) -> Hotspot:
    return Hotspot(
        rank=rank,
        ref=BackgroundRef(database=FIXTURE_DATABASE.name, id=f"process-{rank}"),
        name=f"process {rank}",
        location=None,
        reference_product="product",
        score=4.0 * fraction,
        fraction=fraction,
    )


def test_a_cut_contribution_list_says_what_it_cut() -> None:
    listed = [_hotspot(1, 0.75), _hotspot(2, 0.02), _hotspot(3, 0.004), _hotspot(4, -0.002)]
    kept, cut = cut_below(listed, 0.01)
    assert [item.rank for item in kept] == [1, 2]
    assert (cut.cutoff, cut.below) == (0.01, 2)
    assert cut.share == pytest.approx(0.006)

    kept, cut = cut_below(listed, 0.001)
    assert kept == listed
    assert (cut.below, cut.share) == (0, 0.0)

    kept, cut = cut_below(listed, 0.02)
    assert [item.rank for item in kept] == [1, 2]
    assert cut.below == 2
    assert cut.share == pytest.approx(0.006)
