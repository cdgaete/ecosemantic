"""Plain Monte Carlo over a compiled background: each draw's amounts taken from the seed and the
draw's index alone, each loop without a credit judged in every draw, its scores solved through
one draw solve, and the draws run by one runner."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import scipy.sparse as sp

from ecosemantic.engine.background import Exchanges
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.foreground import Block, Entries, Foreground, OwnedLoop
from ecosemantic.engine.solver import Solver, SolverName, require_solver
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import DISTRIBUTION_IDS, DemandItem, Method, Scope
from ecosemantic.model.validation import verdict

LOGNORMAL = DISTRIBUTION_IDS["lognormal"]
NORMAL = DISTRIBUTION_IDS["normal"]
UNIFORM = DISTRIBUTION_IDS["uniform"]
TRIANGULAR = DISTRIBUTION_IDS["triangular"]
DENSE = 1000
STREAMS = {"technosphere": 0, "biosphere": 1}
FOREGROUND_STREAM = 2


def generator(seed: int, key: tuple[int, ...]) -> np.random.Generator:
    """The generator of one stream of one draw, keyed by the draw's index first."""
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=key))


def wide(rows: Exchanges) -> np.ndarray:
    """The normal rows whose standard deviation exceeds their amount, sampled at their amount."""
    kind = np.asarray(rows.uncertainty_type)
    return (kind == NORMAL) & (np.asarray(rows.scale) > np.abs(np.asarray(rows.amount)))


def drawn(rows: Exchanges, z: np.ndarray, u: np.ndarray, held: np.ndarray) -> np.ndarray:
    """Each row's amount in one draw, from a standard normal variate z and a standard uniform
    variate u per row: a lognormal exp(loc + scale z), negated where negative; a normal
    loc + scale z; a uniform minimum + (maximum - minimum) u; a triangular the inverse of its CDF
    at u, its mode at loc. A row with no distribution, and a row held, keep their amount."""
    amounts = np.array(rows.amount, dtype=np.float64)
    kind = np.asarray(rows.uncertainty_type)
    loc = np.asarray(rows.loc)
    scale = np.asarray(rows.scale)
    low = np.asarray(rows.minimum)
    high = np.asarray(rows.maximum)
    lognormal = (kind == LOGNORMAL) & ~held
    magnitude = np.exp(loc[lognormal] + scale[lognormal] * z[lognormal])
    amounts[lognormal] = np.where(np.asarray(rows.negative)[lognormal], -magnitude, magnitude)
    normal = (kind == NORMAL) & ~held
    amounts[normal] = loc[normal] + scale[normal] * z[normal]
    uniform = (kind == UNIFORM) & ~held
    amounts[uniform] = low[uniform] + (high[uniform] - low[uniform]) * u[uniform]
    triangular = (kind == TRIANGULAR) & ~held
    a, mode, b, p = low[triangular], loc[triangular], high[triangular], u[triangular]
    width = b - a
    amounts[triangular] = np.where(
        p < (mode - a) / width,
        a + np.sqrt(p * width * (mode - a)),
        b - np.sqrt((1.0 - p) * width * (b - mode)),
    )
    return amounts


def _anchored(entries: Entries) -> Exchanges:
    """A block's rows with each distribution moved onto its resolved amount."""
    return Exchanges.of(
        row=np.asarray(entries.rows, dtype=np.int64),
        column=np.asarray(entries.columns, dtype=np.int64),
        amounts=entries.amounts,
        flipped=entries.flipped,
        uncertainties=[
            None if uncertainty is None else uncertainty.anchored(amount)
            for uncertainty, amount in zip(entries.uncertainties, entries.amounts, strict=True)
        ],
    )


def _check_ranges(foreground: Foreground, own: Exchanges) -> None:
    """Invalid when a loop can use as much of its products as it makes within the uniform and
    triangular ranges stated on its amounts: each input taken at the end of its range that uses
    most, each production at the end that makes least. A loop without a credit that delivers at
    that corner delivers everywhere in the ranges; a loop holding a credit is not decided."""
    k = len(foreground.columns)
    kind = np.asarray(own.uncertainty_type)
    bounded = (kind == UNIFORM) | (kind == TRIANGULAR)
    low = np.where(bounded, own.minimum, own.amount)
    high = np.where(bounded, own.maximum, own.amount)
    production_span = np.zeros((k, 2))
    use_span = np.zeros((k, k, 2))
    for at in range(own.amount.size):
        i, j = int(own.row[at]), int(own.column[at])
        if own.flip[at]:
            use_span[i, j] += (low[at], high[at])
        else:
            production_span[j] += (low[at], high[at])
    signs = np.sign(foreground.production)
    for owned in foreground.owned_loops:
        if owned.loop.credit:
            continue
        members = [foreground.index_of[(owned.system, code)] for code in owned.loop.codes]
        used = np.max(signs[members][:, None, None] * use_span[np.ix_(members, members)], axis=2)
        made = np.min(signs[members][:, None] * production_span[members], axis=1)
        block = -used
        block[np.diag_indices(len(members))] = made - np.diag(used)
        if verdict(block) == "delivers":
            continue
        if len(members) == 1:
            sign = signs[members[0]]
            raise Invalid(
                f"{foreground.label(members[0])} can use as much of its own product as it makes "
                f"within the stated ranges: {sign * used[0, 0]:g} used against "
                f"{sign * made[0]:g} made; narrow the ranges so it always makes more than it uses"
            )
        raise Invalid(
            f"{', '.join(foreground.label(m) for m in members)} feed each other, and within the "
            "stated ranges they can use as much of their products as they make; narrow the "
            "ranges so the loop always makes more than it uses"
        )


def on_block(block: np.ndarray, signs: np.ndarray, k: int) -> np.ndarray:
    """A small loop's supply meeting a unit of each of its products, solved on its own block;
    Invalid when draw k leaves the block singular."""
    try:
        return np.linalg.solve(block, signs)
    except np.linalg.LinAlgError as error:
        raise Invalid(f"draw {k} leaves a loop of {signs.size} activities singular") from error


class DrawSolve(Protocol):
    """The supply meeting one or more right-hand sides over one draw's technosphere."""

    def solve(self, technosphere: sp.csr_matrix, b: np.ndarray) -> np.ndarray: ...


class Refactorised:
    """A draw solve that factorises each technosphere it is given with the named solver, and
    nothing before the first: one Solver, built on the first draw's technosphere and refitted
    when a later draw's is not the one it holds. A name the solvers do not know is refused here."""

    def __init__(self, name: SolverName) -> None:
        self._name = require_solver(name)
        self._solver: Solver | None = None
        self._factorised: sp.csr_matrix | None = None

    def solve(self, technosphere: sp.csr_matrix, b: np.ndarray) -> np.ndarray:
        """x with technosphere x = b, in the shape of b."""
        if self._solver is None:
            self._solver = Solver(self._name, technosphere)
        elif technosphere is not self._factorised:
            self._solver.refit(technosphere)
        self._factorised = technosphere
        return self._solver.forward(b)


@dataclass(frozen=True)
class Draw:
    """One draw: a score per method in method order, or None when it is dropped; the foreground
    loops that delivered nothing in it; and the labels of the background activities it failed
    on. A draw is dropped when either holds anything."""

    index: int
    scores: np.ndarray | None
    short: tuple[OwnedLoop, ...]
    failing: tuple[str, ...]


class MonteCarlo:
    """Plain Monte Carlo of one demand over one calculation's background, with a foreground or
    none. Under `full` a draw samples every distribution; under `biosphere_only` the elementary
    ones, with both technospheres at their amounts and the supplies solved once. Draw k takes its
    random numbers from the seed and k alone: the background's technosphere and biosphere each
    from a stream of their own, and each foreground exchange from a stream keyed by its system and
    its id. One sampler refits its draw solve on every draw, so it serves one worker."""

    def __init__(
        self,
        calculation: Calculation,
        foreground: Foreground | None,
        demand: Sequence[DemandItem],
        methods: Sequence[Method],
        *,
        scope: Scope,
        seed: int,
        solve: DrawSolve,
        dense: int = DENSE,
    ) -> None:
        background = calculation.background
        self.calculation = calculation
        self.foreground = foreground
        self.scope: Scope = scope
        self.seed = seed
        self._solve = solve
        self._positions = background.positions(methods)
        self._d_fg, self._d_bg = calculation.placed(foreground, demand)
        self._rows = {
            "technosphere": background.exchanges["technosphere"],
            "biosphere": background.exchanges["biosphere"],
        }
        self._held = {matrix: wide(rows) for matrix, rows in self._rows.items()}
        sampled = ("biosphere",) if scope == "biosphere_only" else ("technosphere", "biosphere")
        self.normals_at_amount = sum(int(self._held[matrix].sum()) for matrix in sampled)
        self._blocks: dict[Block, Exchanges] = (
            {}
            if foreground is None
            else {block: _anchored(entries) for block, entries in foreground.entries.items()}
        )
        n_activity = len(background.coords["activity"])
        self._shapes = {
            "technosphere": (n_activity, n_activity),
            "biosphere": (len(background.coords["flow"]), n_activity),
        }
        self._labels = background.coords["activity"].labels
        if scope == "biosphere_only":
            solution = calculation.solve(foreground, demand)
            self._s_fg = np.asarray(solution.process_supply.data)
            self._s_bg = np.asarray(solution.activity_supply.data)
            return
        if foreground is not None:
            _check_ranges(foreground, self._blocks["own"])
        loops = calculation.loops()
        self._signs = loops.signs
        self._small = tuple(m for m in loops.members if m.size <= dense)
        self._large = tuple(m for m in loops.members if m.size > dense)
        self._large_demand = np.zeros((n_activity, len(self._large)))
        for at, members in enumerate(self._large):
            self._large_demand[members, at] = loops.signs[members]

    def _background(self, k: int, matrix: str) -> sp.csr_matrix:
        """The background's technosphere or biosphere at draw k's amounts."""
        rows = self._rows[matrix]
        g = generator(self.seed, (k, STREAMS[matrix]))
        z = g.standard_normal(rows.amount.size)
        u = g.random(rows.amount.size)
        amounts = drawn(rows=rows, z=z, u=u, held=self._held[matrix])
        signed = np.where(rows.flip, -1.0, 1.0) * amounts
        return sp.csr_matrix(
            (signed, (np.asarray(rows.row), np.asarray(rows.column))), shape=self._shapes[matrix]
        )

    def _block(self, foreground: Foreground, k: int, block: Block) -> sp.csc_matrix:
        """One of the foreground's blocks at draw k's amounts, each exchange from its own
        stream."""
        rows = self._blocks[block]
        entries = foreground.entries[block]
        z = np.zeros(rows.amount.size)
        u = np.zeros(rows.amount.size)
        for at in np.flatnonzero(rows.uncertainty_type):
            g = generator(self.seed, (k, FOREGROUND_STREAM, *entries.keys[at]))
            z[at] = g.standard_normal()
            u[at] = g.random()
        amounts = drawn(rows=rows, z=z, u=u, held=np.zeros(rows.amount.size, dtype=bool))
        shapes = {
            "own": foreground.technosphere.shape,
            "uses": foreground.uses.shape,
            "direct": foreground.direct.shape,
        }
        return entries.matrix(amounts, shapes[block])

    def _scores(self, inventory: np.ndarray) -> np.ndarray:
        """The inventory characterised under each method, in method order."""
        return np.asarray(self.calculation.characterization[self._positions] @ inventory).ravel()

    def _short(self, foreground: Foreground, own: sp.csc_matrix) -> tuple[OwnedLoop, ...]:
        """Each foreground loop without a credit that delivers nothing in a drawn own block,
        signed by the stated production."""
        signed = np.sign(foreground.production)[:, None] * own.toarray()
        short: list[OwnedLoop] = []
        for owned in foreground.owned_loops:
            members = [foreground.index_of[(owned.system, code)] for code in owned.loop.codes]
            if not owned.loop.credit and verdict(signed[np.ix_(members, members)]) != "delivers":
                short.append(owned)
        return tuple(short)

    def _failing(self, k: int, technosphere: sp.csr_matrix) -> list[str]:
        """The activities a drawn technosphere fails on outside its large loops: each making no
        more than it uses of its own product, and for each small loop that delivers nothing, the
        member its supply of a unit of each of its products scales most negatively."""
        net = self._signs * technosphere.diagonal()
        failing = [str(self._labels[p]) for p in np.flatnonzero((net <= 0) & (self._signs != 0))]
        for members in self._small:
            block = technosphere[members][:, members].toarray()
            supply = on_block(block=block, signs=self._signs[members], k=k)
            if not (supply > 0).all():
                failing.append(str(self._labels[members[int(np.argmin(supply))]]))
        return failing

    def draw(self, k: int) -> Draw:
        """Draw k: its amounts from the seed and k alone, its loops judged, and when nothing
        fails its scores."""
        if self.scope == "biosphere_only":
            return self._fixed(k)
        foreground = self.foreground
        short: tuple[OwnedLoop, ...] = ()
        s_fg = np.zeros(0)
        rhs = self._d_bg
        direct: sp.csr_matrix | None = None
        if foreground is not None:
            own = self._block(foreground, k, "own")
            short = self._short(foreground, own)
            if not short:
                s_fg = foreground.solve_over(own, self._d_fg)
                uses = self._block(foreground, k, "uses").tocsr()
                direct = self._block(foreground, k, "direct").tocsr()
                rhs = rhs + uses @ s_fg
        technosphere = self._background(k, "technosphere")
        failing = self._failing(k, technosphere)
        solved = self._solve.solve(technosphere, np.column_stack([rhs, self._large_demand]))
        for at, members in enumerate(self._large):
            supply = solved[members, 1 + at]
            if not (supply > 0).all():
                failing.append(str(self._labels[members[int(np.argmin(supply))]]))
        if short or failing:
            return Draw(index=k, scores=None, short=short, failing=tuple(failing))
        biosphere = self._background(k, "biosphere")
        inventory = biosphere @ solved[:, 0]
        if direct is not None:
            inventory = inventory + direct @ s_fg
        return Draw(index=k, scores=self._scores(inventory), short=(), failing=())

    def _fixed(self, k: int) -> Draw:
        """Draw k under `biosphere_only`: the drawn elementary flows times the supplies solved
        once."""
        biosphere = self._background(k, "biosphere")
        inventory = biosphere @ self._s_bg
        if self.foreground is not None:
            direct = self._block(self.foreground, k, "direct").tocsr()
            inventory = inventory + direct @ self._s_fg
        return Draw(index=k, scores=self._scores(inventory), short=(), failing=())


class Runner(Protocol):
    """The draws of a sampler at the indices given, in their order."""

    def run(self, sampler: MonteCarlo, indices: Iterable[int]) -> Iterator[Draw]: ...


class Serial:
    """A runner that draws one index after another in the calling process."""

    def run(self, sampler: MonteCarlo, indices: Iterable[int]) -> Iterator[Draw]:
        """Each index's draw, in the order of the indices."""
        return (sampler.draw(k) for k in indices)
