from __future__ import annotations

import pytest

from ecosemantic.engine.background import Background, Factors, Rows
from ecosemantic.engine.calculation import Calculation
from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import Database, ForegroundRef
from tests.engine_fixture import fixture_background
from tests.fixture_data import GWP, WATER

GWP_METHOD = Method.of(GWP, "kg CO2-Eq")
WATER_METHOD = Method.of(WATER, "m3")
WIDGET = [DemandItem(ref=ForegroundRef(code="widget"), amount=1.0)]
SMALL = Database(
    name="small",
    elementary_flows="small-biosphere",
    scheme="olca",
    version="1",
    system_model="unit process",
)
SMALL_GWP = Method.of(("small", "gwp", "climate change > GWP100"), "kg CO2-Eq")


def small(
    rows: list[str], columns: list[str], amounts: list[float], flipped: list[bool]
) -> Background:
    """Two activities, a mill and its energy, and two flows, one of them emitted by nothing."""
    return Background.compile(
        SMALL,
        activities=["mill", "energy"],
        flows=["co2", "noise"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=rows,
            columns=columns,
            amounts=amounts,
            flipped=flipped,
            uncertainties=[None] * len(rows),
        ),
        biosphere=Rows(
            rows=["co2"], columns=["mill"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )


@pytest.fixture(scope="module")
def background(tmp_path_factory: pytest.TempPathFactory) -> Background:
    return fixture_background(tmp_path_factory.mktemp("engine"))


@pytest.fixture(scope="module")
def calculation(background: Background) -> Calculation:
    return Calculation(background)
