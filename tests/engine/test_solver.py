import sys

import numpy as np
import pytest
import scipy.sparse as sp

from ecosemantic.engine.solver import SOLVERS, Solver, require_solver
from ecosemantic.errors import Invalid, Unavailable
from tests.conftest import needs_pardiso

TECHNOSPHERE = sp.csr_matrix(np.array([[1.0, -0.2, 0.0], [-0.5, 1.0, -0.1], [0.0, -0.3, 2.0]]))

SOLVER_CASES = [
    pytest.param(name, marks=needs_pardiso) if name == "pardiso" else name for name in SOLVERS
]


@pytest.mark.parametrize("name", SOLVER_CASES)
def test_forward_and_adjoint_solve_the_technosphere_and_its_transpose(name: str) -> None:
    solver = Solver(name, TECHNOSPHERE)
    b = np.array([1.0, 2.0, 3.0])
    dense = TECHNOSPHERE.toarray()
    np.testing.assert_allclose(solver.forward(b), np.linalg.solve(dense, b), rtol=1e-14)
    np.testing.assert_allclose(solver.adjoint(b), np.linalg.solve(dense.T, b), rtol=1e-14)
    assert solver.name == name


@pytest.mark.parametrize("name", SOLVER_CASES)
def test_a_matrix_of_right_hand_sides_keeps_its_shape(name: str) -> None:
    rhs = np.eye(3)[:, :2]
    solver = Solver(name, TECHNOSPHERE)
    assert solver.forward(rhs).shape == (3, 2)
    assert solver.adjoint(rhs).shape == (3, 2)


@pytest.mark.parametrize("name", SOLVER_CASES)
def test_refit_solves_over_the_new_technosphere(name: str) -> None:
    b = np.array([1.0, 2.0, 3.0])
    solver = Solver(name, TECHNOSPHERE)
    solver.forward(b)
    solver.refit(TECHNOSPHERE * 2.0)
    expected = np.linalg.solve(2.0 * TECHNOSPHERE.toarray(), b)
    np.testing.assert_allclose(solver.forward(b), expected, rtol=1e-14)


@needs_pardiso
def test_the_two_solvers_agree() -> None:
    b = np.array([1.0, 2.0, 3.0])
    superlu, pardiso = (Solver(name, TECHNOSPHERE) for name in SOLVERS)
    np.testing.assert_allclose(superlu.forward(b), pardiso.forward(b), rtol=1e-12)
    np.testing.assert_allclose(superlu.adjoint(b), pardiso.adjoint(b), rtol=1e-12)


def test_pardiso_without_pypardiso_is_unavailable_and_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a module table entry of None makes `import pypardiso` raise ImportError
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    with pytest.raises(Unavailable, match="pypardiso") as raised:
        Solver("pardiso", TECHNOSPHERE)
    assert raised.value.hint == "install ecosemantic-engine[mkl]"


def test_superlu_needs_no_pypardiso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    assert Solver("superlu", TECHNOSPHERE).name == "superlu"


def test_an_unknown_solver_name_is_invalid() -> None:
    with pytest.raises(Invalid, match="solver is one of"):
        Solver("umfpack", TECHNOSPHERE)


def test_require_solver_refuses_a_solver_before_anything_is_factorised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert require_solver("superlu") == "superlu"
    with pytest.raises(Invalid, match="solver is one of"):
        require_solver("umfpack")
    monkeypatch.setitem(sys.modules, "pypardiso", None)
    assert require_solver("superlu") == "superlu"
    with pytest.raises(Unavailable, match="pypardiso"):
        require_solver("pardiso")


def test_a_singular_technosphere_is_invalid_under_superlu() -> None:
    with pytest.raises(Invalid, match="the technosphere is singular"):
        Solver("superlu", sp.csr_matrix(np.ones((2, 2))))
