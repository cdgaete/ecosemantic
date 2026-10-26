"""Residual refinement of a sparse solve."""

from __future__ import annotations

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from ecosemantic.engine.refine import refined

# a symmetric system whose entries span eighty orders of magnitude, conditioned at 5.5e9
_ILL_CONDITIONED = csc_matrix(
    [
        [2.0**30, 2.0**20, 1.0, 2.0**-20, -(2.0**-10)],
        [2.0**20, -(2.0**-30), -(2.0**40), -(2.0**40), 2.0**40],
        [1.0, -(2.0**40), 2.0**30, 2.0**40, -(2.0**40)],
        [2.0**-20, -(2.0**40), 2.0**40, -(2.0**-10), -(2.0**-40)],
        [-(2.0**-10), 2.0**40, -(2.0**40), -(2.0**-40), -(2.0**10)],
    ]
)
_EXACT = np.ones(5)


def test_the_refinement_recovers_what_one_superlu_solve_loses() -> None:
    rhs = _ILL_CONDITIONED @ _EXACT
    assert np.abs(splu(_ILL_CONDITIONED).solve(rhs) - _EXACT).max() > 1e-9
    refined_solution = refined(splu(_ILL_CONDITIONED).solve, _ILL_CONDITIONED, rhs)
    assert np.abs(refined_solution - _EXACT).max() < 1e-12


def test_the_refinement_solves_a_matrix_of_right_hand_sides() -> None:
    exact = np.column_stack([_EXACT, np.arange(1.0, 6.0)])
    rhs = _ILL_CONDITIONED @ exact
    solve = splu(_ILL_CONDITIONED).solve
    one_solve_error = np.abs(solve(rhs) - exact).max()
    assert one_solve_error > 1e-9
    refined_solution = refined(solve, _ILL_CONDITIONED, rhs)
    refined_error = np.abs(refined_solution - exact).max()
    # the refinement recovers at least one decimal digit the single solve loses
    assert refined_error <= one_solve_error / 10, (refined_error, one_solve_error)


class _Scaled:
    """A solve that returns a fixed fraction of every right-hand side it is given."""

    def __init__(self, fraction: float) -> None:
        self.fraction = fraction
        self.calls = 0

    def __call__(self, rhs: np.ndarray) -> np.ndarray:
        self.calls += 1
        return self.fraction * rhs


def test_the_refinement_applies_a_correction_while_it_still_shrinks() -> None:
    solve = _Scaled(0.9)
    rhs = np.array([1.0, 2.0])
    result = refined(solve, csc_matrix(np.eye(2)), rhs, limit=10)
    # each correction is a tenth of the last, so ten of them reach the right-hand side
    assert solve.calls == 12
    assert np.abs(result - rhs).max() < 1e-9


def test_the_refinement_stops_at_a_correction_that_does_not_shrink() -> None:
    solve = _Scaled(-0.5)
    rhs = np.array([1.0, 2.0])
    result = refined(solve, csc_matrix(np.eye(2)), rhs, limit=10)
    # the first correction is larger than the solve's error, so none is applied
    assert solve.calls == 3
    assert np.array_equal(result, -0.5 * rhs)


def test_the_refinement_stops_at_a_correction_below_what_float64_holds_of_the_solution() -> None:
    solve = _Scaled(1.0)
    rhs = np.array([1.0, 2.0])
    result = refined(solve, csc_matrix(np.eye(2)), rhs)
    # the solve is exact, so its first correction is zero and no third solve is needed
    assert solve.calls == 2
    assert np.array_equal(result, rhs)


def test_an_empty_system_refines_to_an_empty_solution() -> None:
    empty = csc_matrix((0, 0))
    lu = splu(empty)
    calls = 0

    def solve(rhs: np.ndarray) -> np.ndarray:
        nonlocal calls
        calls += 1
        return lu.solve(rhs)

    solution = refined(solve, empty, np.zeros(0))
    assert solution.size == 0
    assert calls == 1


def test_the_refinement_applies_the_correction_it_stops_at() -> None:
    solve = _Scaled(1.0 - 1e-15)
    rhs = np.array([1.0, 2.0])
    result = refined(solve, csc_matrix(np.eye(2)), rhs)
    assert solve.calls == 2
    assert np.array_equal(
        result, solve.fraction * rhs + solve.fraction * (rhs - solve.fraction * rhs)
    )
