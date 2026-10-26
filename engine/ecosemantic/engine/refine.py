"""Residual refinement of a sparse solve."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import scipy.sparse as sp

RESOLUTION = 1e-14


def refined(
    solve: Callable[[np.ndarray], np.ndarray],
    system: sp.spmatrix,
    rhs: np.ndarray,
    limit: int = 10,
) -> np.ndarray:
    """Solve system·x = rhs from a factorisation's solve, applying each residual correction while
    it is smaller than the last, at most limit times. A correction below RESOLUTION of the
    solution's largest entry is applied and ends the refinement, since float64 holds nothing
    finer of that solution. An empty system has no correction to measure, so its solve is the
    answer."""
    x = solve(rhs)
    if x.size == 0:
        return x
    correction = solve(rhs - system @ x)
    size = float(np.abs(correction).max())
    for _ in range(limit):
        if size <= RESOLUTION * float(np.abs(x).max()):
            return x + correction
        candidate = x + correction
        next_correction = solve(rhs - system @ candidate)
        next_size = float(np.abs(next_correction).max())
        if next_size >= size:
            break
        x, correction, size = candidate, next_correction, next_size
    return x
