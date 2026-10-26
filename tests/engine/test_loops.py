from __future__ import annotations

import numpy as np
import pytest

from ecosemantic.engine.background import Background, Factors, Rows
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.loops import loops_of
from tests.engine.conftest import SMALL, SMALL_GWP
from tests.engine_fixture import looped_background
from tests.fixture_data import LOOP_CODES


def test_the_loops_of_a_background_are_its_strongly_connected_groups(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    background = looped_background(tmp_path_factory.mktemp("loops"))
    found = Calculation(background).loops()
    labels = background.coords["activity"].labels
    assert [sorted(labels[m].tolist()) for m in found.members] == [
        sorted([LOOP_CODES["pellet"], LOOP_CODES["heat"]])
    ]
    assert found.signs.tolist() == [1.0, 1.0, 1.0]


def test_a_loop_holding_a_credit_is_left_out() -> None:
    # the energy's use of the mill's product is negative, a credit inside the loop
    background = Background.compile(
        SMALL,
        activities=["mill", "energy"],
        flows=["co2", "noise"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=["mill", "energy", "energy", "mill"],
            columns=["mill", "energy", "mill", "energy"],
            amounts=[1.0, 1.0, 0.5, -0.2],
            flipped=[False, False, True, True],
            uncertainties=[None] * 4,
        ),
        biosphere=Rows(
            rows=["co2"], columns=["mill"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )
    found = loops_of(Calculation(background).technosphere)
    assert found.members == ()
    np.testing.assert_array_equal(found.signs, [1.0, 1.0])
