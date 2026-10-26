"""The loops of a background's technosphere that a sampled draw is checked on."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components


@dataclass(frozen=True)
class Loops:
    """Each activity's sign of net production on the stated technosphere, and each loop of
    several activities holding no credit, as the positions of its members."""

    signs: np.ndarray
    members: tuple[np.ndarray, ...]


def loops_of(technosphere: sp.csr_matrix) -> Loops:
    """The strongly connected groups of several activities, each row signed by its activity's net
    production so a waste treatment's row counts the waste it treats, leaving out a group with a
    positive entry inside it, which holds a credit."""
    signs = np.sign(technosphere.diagonal())
    signed = (sp.diags(signs) @ technosphere).tocsr()
    off = (signed - sp.diags(signed.diagonal())).tocoo()
    off.eliminate_zeros()
    structure = sp.csr_matrix((np.ones(off.nnz), (off.row, off.col)), shape=signed.shape)
    _, labels = connected_components(structure, directed=True, connection="strong")
    inside = labels[off.row] == labels[off.col]
    credited = set(labels[off.row[inside & (off.data > 0)]].tolist())
    sizes = np.bincount(labels)
    members = tuple(
        np.flatnonzero(labels == label)
        for label in np.flatnonzero(sizes > 1)
        if label not in credited
    )
    return Loops(signs=signs, members=members)
