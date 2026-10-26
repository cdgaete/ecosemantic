"""Exact results over a compiled background: one solve, and the scores, contributions,
intensities, supply, inventory and paths read from it."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import nimblend as nb
import numpy as np
import scipy.sparse as sp

from ecosemantic.engine.background import Background
from ecosemantic.engine.foreground import Foreground
from ecosemantic.engine.loops import Loops, loops_of
from ecosemantic.engine.paths import PathTree, Walked, walk
from ecosemantic.engine.solver import Solver, SolverName
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import DemandItem, Method, ProductSystem
from ecosemantic.model.refs import ForegroundRef

NOISE_FLOOR = 1e-34


def _csr(array: nb.SparseArray) -> sp.csr_matrix:
    """A two-dimensional array as a scipy CSR matrix over its buffers."""
    indices, values, indptr = array.to_csr()
    return sp.csr_matrix((values, indices, indptr), shape=array.shape)


def _over(dim: str, coord: nb.StoredCoord, values: np.ndarray) -> nb.SparseArray:
    """A value at every label of one coordinate."""
    return nb.Domain.full((dim,), {dim: coord}).array(np.asarray(values, dtype=np.float64))


@dataclass(frozen=True)
class Solution:
    """One solve: the foreground it solved, the supply of each foreground process over
    "process" and of each background activity over "activity", the inventory over "flow", the
    demand placed on background activities, and the solver that ran."""

    foreground: Foreground | None
    process_supply: nb.SparseArray
    activity_supply: nb.SparseArray
    inventory: nb.SparseArray
    background_demand: np.ndarray
    solver: SolverName


@dataclass(frozen=True)
class Contributions:
    """A score split over the processes that emit, each one's direct emissions characterised
    times its supply: the foreground's over "process", the background's over "activity"."""

    foreground: nb.SparseArray
    background: nb.SparseArray


@dataclass(frozen=True)
class Inventory:
    """The amount of every elementary flow over "flow", and for each flow with an amount the
    label of the foreground process whose own and upstream emissions of it are largest, None
    where a demanded background activity's are or where there is no foreground. An amount at or
    below `floor`, NOISE_FLOOR of the largest, is float64 residue: it is set to zero, and
    `dropped` counts it."""

    amounts: nb.SparseArray
    sources: dict[str, str | None]
    floor: float
    dropped: int


class Calculation:
    """Exact results over one background: its technosphere factorised once by the named solver,
    and per category the direct impact of each activity and the cradle-to-gate intensities, each
    built on first use."""

    def __init__(self, background: Background, solver: SolverName = "superlu") -> None:
        self.background = background
        self.technosphere = _csr(background.technosphere)
        self.biosphere = _csr(background.biosphere)
        self.characterization = _csr(background.characterization)
        self.solver = Solver(solver, self.technosphere)
        self._direct: dict[int, np.ndarray] = {}
        self._intensities: dict[int, np.ndarray] = {}
        self._loops: Loops | None = None

    def foreground(
        self, product_system: ProductSystem, linked: Mapping[uuid.UUID, ProductSystem]
    ) -> Foreground:
        """The foreground of a product system and the systems it links."""
        return Foreground.of(self.background, product_system, linked)

    def loops(self) -> Loops:
        """The background's loops a sampled draw is checked on, found on first use."""
        if self._loops is None:
            self._loops = loops_of(self.technosphere)
        return self._loops

    def _factors(self, position: int) -> np.ndarray:
        """The characterisation factor of every flow under one category."""
        return np.asarray(self.characterization[[position]].toarray()).ravel()

    def _direct_impacts(self, position: int) -> np.ndarray:
        """Each activity's direct emissions characterised under one category, per unit of its
        operation."""
        if position not in self._direct:
            self._direct[position] = (
                (self.characterization[[position]] @ self.biosphere).toarray().ravel()
            )
        return self._direct[position]

    def _intensity_rows(self, positions: Sequence[int]) -> np.ndarray:
        """The cradle-to-gate intensity of every activity under each category, one row each; the
        categories not yet held are solved together, one right-hand side each."""
        missing = sorted({p for p in positions if p not in self._intensities})
        if missing:
            direct = np.column_stack([self._direct_impacts(p) for p in missing])
            solved = self.solver.adjoint(direct)
            for at, p in enumerate(missing):
                self._intensities[p] = solved[:, at]
        return np.vstack([self._intensities[p] for p in positions])

    def placed(
        self, foreground: Foreground | None, demand: Sequence[DemandItem]
    ) -> tuple[np.ndarray, np.ndarray]:
        """The demand on foreground processes and on background activities."""
        background = self.background
        d_fg = np.zeros(len(foreground.columns) if foreground is not None else 0)
        d_bg = np.zeros(len(background.coords["activity"]))
        for item in demand:
            if isinstance(item.ref, ForegroundRef):
                if foreground is None:
                    raise Invalid(
                        f"the demand names foreground process {item.ref.code!r} "
                        "and the calculation has no product system"
                    )
                host = foreground.product_system.id
                d_fg[foreground.column_of(host, item.ref.code, "the demand")] += item.amount
                continue
            if item.ref.database != background.database.name:
                raise Invalid(f"the demand names database {item.ref.database!r}")
            at = background.position("activity", item.ref.id)
            if at is None:
                raise NotFound(
                    f"the demand names background dataset {item.ref.id!r}, "
                    f"which {background.database.name!r} does not hold"
                )
            d_bg[at] += item.amount
        return d_fg, d_bg

    def _process_coord(self, foreground: Foreground | None) -> nb.StoredCoord:
        labels = foreground.labels if foreground is not None else np.array([], dtype=str)
        return nb.StoredCoord(labels)

    def solve(self, foreground: Foreground | None, demand: Sequence[DemandItem]) -> Solution:
        """The supply and the inventory that meet a demand: the foreground first, then the
        background with the foreground's uses added to its demand."""
        background = self.background
        d_fg, d_bg = self.placed(foreground, demand)
        rhs = d_bg.copy()
        s_fg = np.zeros(0)
        if foreground is not None:
            s_fg = foreground.solve(d_fg)
            rhs = rhs + foreground.uses @ s_fg
        s_bg = self.solver.forward(rhs) if rhs.any() else np.zeros_like(rhs)
        g = np.asarray(self.biosphere @ s_bg).ravel()
        if foreground is not None:
            g = g + np.asarray(foreground.direct @ s_fg).ravel()
        return Solution(
            foreground=foreground,
            process_supply=_over("process", self._process_coord(foreground), s_fg),
            activity_supply=_over("activity", background.coords["activity"], s_bg),
            inventory=_over("flow", background.coords["flow"], g),
            background_demand=d_bg,
            solver=self.solver.name,
        )

    def scores(self, solution: Solution, methods: Sequence[Method]) -> nb.SparseArray:
        """One score per method over "category", in the order given; NotFound naming every
        method the background does not hold."""
        positions = self.background.positions(methods)
        values = np.asarray(self.characterization[positions] @ solution.inventory.data).ravel()
        coord = nb.StoredCoord(np.array([method.id for method in methods]))
        return _over("category", coord, values)

    def by_process(self, solution: Solution, method: Method) -> Contributions:
        """The score of each foreground process and each background activity: its direct
        emissions characterised, times its supply."""
        [position] = self.background.positions([method])
        factors = self._factors(position)
        background = self._direct_impacts(position) * solution.activity_supply.data
        fg = solution.foreground
        own = np.zeros(0) if fg is None else np.asarray(factors @ fg.direct).ravel()
        return Contributions(
            foreground=_over(
                "process", self._process_coord(fg), own * solution.process_supply.data
            ),
            background=_over("activity", self.background.coords["activity"], background),
        )

    def by_flow(self, solution: Solution, method: Method) -> nb.SparseArray:
        """Each flow's characterised amount over "flow"."""
        [position] = self.background.positions([method])
        values = self._factors(position) * solution.inventory.data
        return _over("flow", self.background.coords["flow"], values)

    def intensities(self, methods: Sequence[Method]) -> nb.SparseArray:
        """The cradle-to-gate score of one unit of every activity's product under each method,
        over ("category", "activity")."""
        rows = self._intensity_rows(self.background.positions(methods))
        coords = {
            "category": nb.StoredCoord(np.array([method.id for method in methods])),
            "activity": self.background.coords["activity"],
        }
        return nb.Domain.full(("category", "activity"), coords).array(rows.ravel())

    def supply(self, foreground: Foreground, demand: Sequence[DemandItem]) -> nb.SparseArray:
        """The level of each foreground process that meets the demand, over "process", with no
        background solve."""
        d_fg, _ = self.placed(foreground, demand)
        return _over("process", self._process_coord(foreground), foreground.solve(d_fg))

    def inventory(self, solution: Solution) -> Inventory:
        """The inventory, and each flow's dominant source: per foreground process its own
        emissions plus those of the background it uses, one background solve each, and the
        demanded background activities together."""
        found = solution.inventory.data
        floor = NOISE_FLOOR * float(np.abs(found).max(initial=0.0))
        residue = (found != 0.0) & (np.abs(found) <= floor)
        g = np.where(residue, 0.0, found)
        amounts = _over("flow", self.background.coords["flow"], g)
        dropped = int(residue.sum())
        flows = self.background.coords["flow"].labels
        nonzero = np.flatnonzero(g)
        fg = solution.foreground
        if fg is None:
            sourced = {str(flows[row]): None for row in nonzero}
            return Inventory(amounts, sourced, floor, dropped)
        s_fg = solution.process_supply.data
        k = len(fg.columns)
        shares = np.zeros((k + 1, g.size))
        for j in range(k):
            own = np.asarray(fg.direct[:, [j]].toarray()).ravel() * s_fg[j]
            used = np.asarray(fg.uses[:, [j]].toarray()).ravel() * s_fg[j]
            upstream = self.biosphere @ self.solver.forward(used) if used.any() else 0.0
            shares[j] = own + upstream
        if solution.background_demand.any():
            shares[k] = self.biosphere @ self.solver.forward(solution.background_demand)
        labels = fg.labels
        sources: dict[str, str | None] = {}
        for row in nonzero:
            winner = int(np.argmax(np.abs(shares[:, row])))
            sources[str(flows[row])] = None if winner == k else str(labels[winner])
        return Inventory(amounts, sources, floor, dropped)

    def paths(
        self,
        foreground: Foreground,
        item: DemandItem,
        method: Method,
        max_level: int,
        max_nodes: int,
        cutoff: float,
    ) -> PathTree:
        """The paths under the one foreground process an item demands, walked best first."""
        if not isinstance(item.ref, ForegroundRef):
            raise Invalid("paths start at one foreground process")
        [position] = self.background.positions([method])
        factors = self._factors(position)
        background_intensity = self._intensity_rows([position])[0]
        foreground_intensity = foreground.solve_transposed(
            np.asarray(factors @ foreground.direct).ravel()
            + np.asarray(foreground.uses.T @ background_intensity).ravel()
        )
        solution = self.solve(foreground, [item])
        total = float(factors @ solution.inventory.data)
        root = foreground.column_of(foreground.product_system.id, item.ref.code, "the paths")
        walked = Walked(
            foreground_intensity=foreground_intensity,
            background_intensity=background_intensity,
            factors=factors,
            foreground=foreground.technosphere.tocsc(),
            uses=foreground.uses.tocsc(),
            direct=foreground.direct.tocsc(),
            technosphere=self.technosphere.tocsc(),
            biosphere=self.biosphere.tocsc(),
            process_labels=foreground.labels,
            activity_labels=self.background.coords["activity"].labels,
            flow_labels=self.background.coords["flow"].labels,
        )
        return walk(walked, root, item.amount, total, max_level, max_nodes, cutoff)
