"""Contributions by path: the supply chain under one foreground process, walked best first, each
node's cradle-to-gate score read from the intensities, expansion bounded."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import scipy.sparse as sp

PathKind = Literal["process", "activity", "flow", "remainder"]


@dataclass
class PathNode:
    """One node of the walk: a foreground process, a background activity, an elementary flow or
    the share of its parent left unexpanded, with its label, the amount of it the root uses, its
    score and its depth. `position` is its column or row; -1 for a remainder."""

    kind: PathKind
    label: str | None
    amount: float
    score: float
    level: int
    position: int
    children: list[PathNode] = field(default_factory=list)
    truncated: bool = False


@dataclass(frozen=True)
class PathTree:
    """The walk's root, the total score its fractions are of, and whether any node was left
    unexpanded."""

    root: PathNode
    total: float
    truncated: bool


@dataclass(frozen=True)
class Walked:
    """What the walk reads: each foreground process's and background activity's cradle-to-gate
    score per unit of its product, the characterisation factors, the matrices, and the labels."""

    foreground_intensity: np.ndarray
    background_intensity: np.ndarray
    factors: np.ndarray
    foreground: sp.csc_matrix
    uses: sp.csc_matrix
    direct: sp.csc_matrix
    technosphere: sp.csc_matrix
    biosphere: sp.csc_matrix
    process_labels: np.ndarray
    activity_labels: np.ndarray
    flow_labels: np.ndarray


def walk(
    walked: Walked,
    root: int,
    amount: float,
    total: float,
    max_level: int,
    max_nodes: int,
    cutoff: float,
) -> PathTree:
    """The paths under one foreground process demanded at an amount. A child is kept when its
    score exceeds `cutoff` of the total; a node at `max_level` is not expanded; the walk stops
    once `max_nodes` nodes are kept. Every off-diagonal input is a child, a credit with a
    negative score among them; a node's unexpanded share is a remainder child."""
    w = walked
    start = PathNode(
        kind="process",
        label=str(w.process_labels[root]),
        amount=amount,
        score=amount * float(w.foreground_intensity[root]),
        level=0,
        position=root,
    )
    frontier: list[tuple[float, int, PathNode]] = []
    counter = 0
    truncated = False

    def push(node: PathNode) -> None:
        nonlocal counter, truncated
        if node.level >= max_level:
            node.truncated = True
            truncated = True
            return
        counter += 1
        heapq.heappush(frontier, (-abs(node.score), counter, node))

    def above_cutoff(score: float) -> bool:
        return abs(score) > abs(total * cutoff)

    def flows(
        node: PathNode, matrix: sp.csc_matrix, column: int, per_unit: float
    ) -> list[PathNode]:
        found: list[PathNode] = []
        start, end = matrix.indptr[column], matrix.indptr[column + 1]
        for row, value in zip(matrix.indices[start:end], matrix.data[start:end], strict=True):
            flow_amount = per_unit * float(value)
            score = flow_amount * float(w.factors[row])
            if score and above_cutoff(score):
                found.append(
                    PathNode(
                        kind="flow",
                        label=str(w.flow_labels[row]),
                        amount=flow_amount,
                        score=score,
                        level=node.level + 1,
                        position=int(row),
                    )
                )
        return found

    def suppliers(
        node: PathNode,
        matrix: sp.csc_matrix,
        column: int,
        per_unit: float,
        kind: PathKind,
        sign: float,
        skip: int,
    ) -> list[PathNode]:
        intensity = w.foreground_intensity if kind == "process" else w.background_intensity
        labels = w.process_labels if kind == "process" else w.activity_labels
        found: list[PathNode] = []
        start, end = matrix.indptr[column], matrix.indptr[column + 1]
        for row, value in zip(matrix.indices[start:end], matrix.data[start:end], strict=True):
            if row == skip or not value:
                continue
            supplied = per_unit * sign * float(value)
            score = supplied * float(intensity[row])
            if above_cutoff(score):
                found.append(
                    PathNode(
                        kind=kind,
                        label=str(labels[row]),
                        amount=supplied,
                        score=score,
                        level=node.level + 1,
                        position=int(row),
                    )
                )
        return found

    push(start)
    count = 1
    while frontier:
        _, _, node = heapq.heappop(frontier)
        c = node.position
        if node.kind == "process":
            per_unit = node.amount / float(w.foreground[c, c])
            children = flows(node, w.direct, c, per_unit)
            children += suppliers(node, w.foreground, c, per_unit, "process", -1.0, c)
            children += suppliers(node, w.uses, c, per_unit, "activity", 1.0, -1)
        else:
            per_unit = node.amount / float(w.technosphere[c, c])
            children = flows(node, w.biosphere, c, per_unit)
            children += suppliers(node, w.technosphere, c, per_unit, "activity", -1.0, c)
        children.sort(key=lambda child: -abs(child.score))
        kept: list[PathNode] = []
        for child in children:
            if count >= max_nodes:
                break
            kept.append(child)
            count += 1
        remainder = node.score - sum(child.score for child in kept)
        node.children = kept
        if abs(remainder) > abs(node.score) * 1e-9:
            node.children.append(
                PathNode(
                    kind="remainder",
                    label=None,
                    amount=0.0,
                    score=remainder,
                    level=node.level + 1,
                    position=-1,
                )
            )
            node.truncated = True
            truncated = True
        for child in kept:
            if child.kind in ("process", "activity"):
                push(child)
    return PathTree(root=start, total=total, truncated=truncated)
