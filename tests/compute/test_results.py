from __future__ import annotations

import pytest
from pydantic import ValidationError

from ecosemantic.compute.results import ContributionResult
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import Score
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
