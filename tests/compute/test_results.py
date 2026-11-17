from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecosemantic.compute.results import ContributionResult, ImpactResult
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import DemandItem, ForegroundRef
from ecosemantic.ports.types import Score
from tests.fixture_data import FIXTURE_DATABASE

GWP = Method.of(("db", "IPCC", "climate change"), "kg CO2-Eq")
TOTAL = Score(value=1.0, unit="kg CO2-Eq", method_id=GWP.id)


def test_a_decomposition_carries_the_rows_its_axis_names_and_no_others() -> None:
    assert (
        ContributionResult(
            database=FIXTURE_DATABASE,
            by="process",
            method=GWP,
            total=TOTAL,
            processes=[],
            credit_loops=[],
        ).processes
        == []
    )
    with pytest.raises(ValidationError, match="by='process' carries processes"):
        ContributionResult(
            database=FIXTURE_DATABASE,
            by="process",
            method=GWP,
            total=TOTAL,
            credit_loops=[],
        )
    with pytest.raises(ValidationError, match="by='flow' carries flows"):
        ContributionResult(
            database=FIXTURE_DATABASE,
            by="flow",
            method=GWP,
            total=TOTAL,
            processes=[],
            credit_loops=[],
        )


def test_an_impact_s_summary_carries_the_demand_it_scored() -> None:
    demand = [DemandItem(ref=ForegroundRef(code="widget"), amount=10.0)]
    result = ImpactResult(
        database=FIXTURE_DATABASE,
        product_system="widget",
        methods=[GWP],
        scores=[TOTAL],
        credit_loops=[],
        demand=demand,
    )
    assert result.demand == demand
    assert result.summarise().demand == demand


def test_a_summary_without_a_demand_carries_none() -> None:
    assert (
        ContributionResult(
            database=FIXTURE_DATABASE,
            by="process",
            method=GWP,
            total=TOTAL,
            processes=[],
            credit_loops=[],
        )
        .summarise()
        .demand
        is None
    )
