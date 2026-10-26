"""Forward and adjoint solves over one technosphere matrix, factorised once for both."""

from __future__ import annotations

from typing import Any, Literal, get_args

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ecosemantic.engine.refine import refined
from ecosemantic.errors import Invalid, Unavailable

SolverName = Literal["superlu", "pardiso"]
SOLVERS: tuple[SolverName, ...] = get_args(SolverName)


def _pypardiso() -> Any:
    """pypardiso, which the `mkl` extra installs."""
    try:
        import pypardiso
    except ImportError as error:
        raise Unavailable(
            "the pardiso solver needs pypardiso", hint="install ecosemantic-engine[mkl]"
        ) from error
    return pypardiso


def require_solver(name: str) -> SolverName:
    """The solver a name names, refused as building a `Solver` of it refuses it, before anything
    is factorised: Invalid for a name outside SOLVERS, Unavailable for pardiso without
    pypardiso."""
    if name not in SOLVERS:
        raise Invalid(f"solver is one of {list(SOLVERS)}; got {name!r}")
    if name == "pardiso":
        _pypardiso()
    return name


class Solver:
    """Forward and adjoint solves over one technosphere, factorised once for both. "superlu"
    factorises the transpose with SciPy and refines every solve against its residual; "pardiso"
    factorises the technosphere on the first solve and answers the adjoint as PARDISO's
    transposed solve on those factors."""

    def __init__(self, name: SolverName, technosphere: sp.spmatrix | sp.sparray) -> None:
        self.name: SolverName = require_solver(name)
        self._pardiso = _pypardiso().PyPardisoSolver() if name == "pardiso" else None
        self.refit(technosphere)

    def refit(self, technosphere: sp.spmatrix | sp.sparray) -> None:
        """Solve over another technosphere from here on."""
        self._t = sp.csr_matrix(technosphere)
        self._t.sort_indices()
        self._tt: sp.csr_matrix | None = None
        self._factorised = False
        if self._pardiso is None:
            try:
                self._lu = spla.splu(self._t.T.tocsc())
            except RuntimeError as error:
                raise Invalid(f"the technosphere is singular: {error}") from error
        else:
            self._t_as_csc = sp.csc_matrix(
                (self._t.data, self._t.indices, self._t.indptr), shape=self._t.shape
            )

    def forward(self, b: np.ndarray) -> np.ndarray:
        """x with T x = b, in the shape of b."""
        if self._pardiso is not None:
            return self._pardiso_solve(self._pardiso, self._t, b)
        return refined(lambda r: self._lu.solve(r, trans="T"), self._t, b)

    def adjoint(self, c: np.ndarray) -> np.ndarray:
        """y with T-transpose y = c, in the shape of c."""
        if self._pardiso is not None:
            return self._pardiso_solve(self._pardiso, self._t_as_csc, c)
        if self._tt is None:
            self._tt = self._t.T.tocsr()
        return refined(self._lu.solve, self._tt, c)

    def _pardiso_solve(
        self, pardiso: Any, matrix: sp.csr_matrix | sp.csc_matrix, b: np.ndarray
    ) -> np.ndarray:
        """A solve on the technosphere's one factorisation. The CSC matrix built on the
        technosphere's own arrays is its transpose, which pypardiso answers as PARDISO's
        transposed solve and recognises as already factorised."""
        if not self._factorised:
            pardiso.factorize(self._t)
            self._factorised = True
        return np.asarray(pardiso.solve(matrix, b)).reshape(b.shape)
