"""A product system's processes, and those of each system it links, as the columns of a square
foreground over a compiled background."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from ecosemantic.engine.background import Background
from ecosemantic.engine.refine import refined
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import Exchange, Process, ProductSystem, Uncertainty, state_of
from ecosemantic.model.refs import (
    BackgroundRef,
    ElementaryFlowRef,
    ForegroundRef,
    LinkedProcessRef,
    SystemRef,
)
from ecosemantic.model.validation import Loop, loops, undelivered

Block = Literal["own", "uses", "direct"]


class _Entry(NamedTuple):
    row: int
    column: int
    amount: float
    flipped: bool
    uncertainty: Uncertainty | None
    key: tuple[int, int]


@dataclass(frozen=True)
class Entries:
    """One block's exchanges, one row each: its row and column in the block, its amount, whether
    it enters negated, its distribution as stated, and the ids of its system and of the exchange,
    which key its random numbers."""

    rows: tuple[int, ...]
    columns: tuple[int, ...]
    amounts: tuple[float, ...]
    flipped: tuple[bool, ...]
    uncertainties: tuple[Uncertainty | None, ...]
    keys: tuple[tuple[int, int], ...]

    @classmethod
    def of(cls, entries: list[_Entry]) -> Entries:
        """The entries of one block, in the order they were placed."""
        return cls(
            rows=tuple(e.row for e in entries),
            columns=tuple(e.column for e in entries),
            amounts=tuple(e.amount for e in entries),
            flipped=tuple(e.flipped for e in entries),
            uncertainties=tuple(e.uncertainty for e in entries),
            keys=tuple(e.key for e in entries),
        )

    def matrix(self, amounts: np.ndarray, shape: tuple[int, int]) -> sp.csc_matrix:
        """The block at the amounts given, an entry negated where it enters negated, the entries
        at one position added."""
        signed = np.where(np.asarray(self.flipped, dtype=bool), -1.0, 1.0) * amounts
        positions = (
            np.asarray(self.rows, dtype=np.int64),
            np.asarray(self.columns, dtype=np.int64),
        )
        return sp.csc_matrix((signed, positions), shape=shape)


@dataclass(frozen=True)
class Column:
    """One foreground process, with the system that holds it and, for a linked system, the hash
    it was read at."""

    system: uuid.UUID
    at_hash: str | None
    process: Process


@dataclass(frozen=True)
class OwnedLoop:
    """A loop among one system's processes, with that system."""

    system: uuid.UUID
    loop: Loop


class Foreground:
    """The foreground's own square technosphere, its uses of background products and its direct
    elementary flows, one column per process: the host's processes in document order, then each
    linked system's, the systems ordered by id. A host process is labelled by its code, a linked
    one by its system's id and its code."""

    def __init__(self, background: Background, product_system: ProductSystem) -> None:
        self.background = background
        self.product_system = product_system
        self.columns: list[Column] = []
        self.index_of: dict[tuple[uuid.UUID, str], int] = {}
        self.owned_loops: list[OwnedLoop] = []
        self.linked_names: dict[uuid.UUID, str] = {}
        self._lu: spla.SuperLU | None = None

    @classmethod
    def of(
        cls,
        background: Background,
        product_system: ProductSystem,
        linked: Mapping[uuid.UUID, ProductSystem],
    ) -> Foreground:
        """The foreground of a product system and the systems it links, each read at its pin
        and materialised; Invalid for a system on another database or a loop that delivers
        nothing."""
        name = background.database.name
        if product_system.database.name != name:
            raise Invalid(
                f"{product_system.name} is on {product_system.database.name!r}, "
                f"the background is {name!r}"
            )
        others = sorted(linked.values(), key=lambda other: str(other.id))
        for other in others:
            if other.database.name != name:
                raise Invalid(
                    f"{other.name} is on {other.database.name!r}, the background is {name!r}"
                )
        fg = cls(background, product_system)
        fg.columns = [Column(product_system.id, None, p) for p in product_system.processes]
        for other in others:
            fg.columns += [Column(other.id, state_of(other), p) for p in other.processes]
        fg.index_of = {(c.system, c.process.code): j for j, c in enumerate(fg.columns)}
        fg.linked_names = {other.id: other.name for other in others}
        fg._build(linked)
        fg.owned_loops = [OwnedLoop(product_system.id, loop) for loop in loops(product_system)]
        fg.owned_loops += [OwnedLoop(other.id, loop) for other in others for loop in loops(other)]
        fg._check_loops()
        return fg

    @property
    def labels(self) -> np.ndarray:
        """Each column's label: a host process's code, a linked process's system id and code."""
        return np.array(
            [
                c.process.code if c.at_hash is None else f"{c.system}/{c.process.code}"
                for c in self.columns
            ]
        )

    def ref(self, j: int) -> ForegroundRef | LinkedProcessRef:
        """How a result names the process in column j."""
        column = self.columns[j]
        if column.at_hash is None:
            return ForegroundRef(code=column.process.code)
        return LinkedProcessRef(
            product_system_id=column.system, at_hash=column.at_hash, code=column.process.code
        )

    def column_of(self, system: uuid.UUID, code: str, owner: str) -> int:
        """The column of a process inside the system that holds it; NotFound otherwise."""
        found = self.index_of.get((system, code))
        if found is None:
            raise NotFound(f"{owner} names foreground process {code!r}, which is not in the system")
        return found

    def _link(self, ref: SystemRef, linked: Mapping[uuid.UUID, ProductSystem], owner: str) -> int:
        """The column of the reference process of the system a link names, as given at the pin."""
        other = linked.get(ref.product_system_id)
        if other is None:
            raise NotFound(
                f"{owner} links product system {ref.product_system_id}, "
                "which the calculation was not given"
            )
        if other.hash != ref.at_hash:
            raise Invalid(
                f"{owner} links {other.name} at {ref.at_hash}; "
                f"the calculation was given {other.hash}"
            )
        if other.reference_process is None:
            raise Invalid(f"{owner} links {other.name}, which has no reference process")
        return self.index_of[(other.id, other.reference_process)]

    def _build(self, linked: Mapping[uuid.UUID, ProductSystem]) -> None:
        background = self.background
        k = len(self.columns)
        placed: dict[Block, list[_Entry]] = {"own": [], "uses": [], "direct": []}
        self.production = np.zeros(k)
        for j, column in enumerate(self.columns):
            for exchange in column.process.exchanges:
                block, at = self._place(j, column, exchange, linked)
                amount = float(exchange.amount)
                placed[block].append(
                    _Entry(
                        row=at,
                        column=j,
                        amount=amount,
                        flipped=block == "own" and exchange.type != "production",
                        uncertainty=exchange.uncertainty,
                        key=(column.system.int, exchange.id.int),
                    )
                )
                if exchange.type == "production":
                    self.production[j] += amount
        self.entries = {block: Entries.of(entries) for block, entries in placed.items()}
        n_activity = len(background.coords["activity"])
        n_flow = len(background.coords["flow"])
        self.technosphere = self._stated("own", (k, k))
        self.uses = self._stated("uses", (n_activity, k)).tocsr()
        self.direct = self._stated("direct", (n_flow, k)).tocsr()

    def _stated(self, block: Block, shape: tuple[int, int]) -> sp.csc_matrix:
        """A block at its stated amounts."""
        entries = self.entries[block]
        return entries.matrix(np.asarray(entries.amounts, dtype=np.float64), shape)

    def _place(
        self,
        j: int,
        column: Column,
        exchange: Exchange,
        linked: Mapping[uuid.UUID, ProductSystem],
    ) -> tuple[Block, int]:
        """Which block an exchange enters and its row there."""
        background = self.background
        code = column.process.code
        if exchange.type == "production":
            return "own", j
        ref = exchange.input
        if isinstance(ref, ForegroundRef):
            return "own", self.column_of(column.system, ref.code, code)
        if isinstance(ref, SystemRef):
            return "own", self._link(ref, linked, code)
        if isinstance(ref, BackgroundRef):
            if ref.database != background.database.name:
                raise Invalid(f"{code} references database {ref.database!r}")
            at = background.position("activity", ref.id)
            if at is None:
                raise NotFound(
                    f"{code} names background dataset {ref.id!r}, "
                    f"which {ref.database!r} does not hold"
                )
            return "uses", at
        if isinstance(ref, ElementaryFlowRef):
            if ref.database != background.database.elementary_flows:
                raise Invalid(f"{code} references elementary flows {ref.database!r}")
            at = background.position("flow", ref.id)
            if at is None:
                raise NotFound(
                    f"{code} names elementary flow {ref.id!r}, which {ref.database!r} does not hold"
                )
            return "direct", at
        raise Invalid(f"{code} has an exchange with no input")

    def label(self, j: int) -> str:
        """The code in column j, with its system's name when it is linked."""
        column = self.columns[j]
        if column.at_hash is None:
            return column.process.code
        return f"{column.process.code} of {self.linked_names[column.system]}"

    def _check_loops(self) -> None:
        """Invalid when a loop, or a process using its own product, uses as much of its products
        as it makes or more; a loop holding a credit is refused only when singular."""
        signed = np.sign(self.production)[:, None] * self.technosphere.toarray()
        for owned in self.owned_loops:
            members = [self.index_of[(owned.system, c)] for c in owned.loop.codes]
            refused = undelivered(signed[np.ix_(members, members)], owned.loop.credit)
            if refused is None:
                continue
            if len(members) == 1:
                j = members[0]
                made = self.production[j]
                used = made - self.technosphere[j, j]
                raise Invalid(
                    f"{self.label(j)} uses {used:g} of its own product and makes {made:g}; "
                    "it must make more than it uses to deliver any"
                )
            named = ", ".join(self.label(m) for m in members)
            if refused == "singular":
                raise Invalid(
                    f"{named} feed each other so that the loop delivers none of what it makes; a "
                    "calculation over it is singular"
                )
            raise Invalid(
                f"{named} feed each other and use more of their products than they make; a loop "
                "must make more than it uses to deliver any"
            )

    def _factorised(self) -> spla.SuperLU:
        """The foreground technosphere's one factorisation; Invalid when it is singular."""
        if self._lu is None:
            self._lu = self._factorise(self.technosphere)
        return self._lu

    def _factorise(self, technosphere: sp.csc_matrix) -> spla.SuperLU:
        """A factorisation of a technosphere of this foreground's shape; Invalid when it is
        singular."""
        try:
            return spla.splu(technosphere)
        except RuntimeError as error:
            raise Invalid(
                f"the foreground of {self.product_system.name} is singular: {error}"
            ) from error

    def solve(self, demand: np.ndarray) -> np.ndarray:
        """The level of each process that meets a demand on the foreground's products."""
        return refined(self._factorised().solve, self.technosphere, demand)

    def solve_over(self, technosphere: sp.csc_matrix, demand: np.ndarray) -> np.ndarray:
        """The level of each process that meets a demand over another technosphere of this
        foreground's shape, a sampled draw of it, factorised for this solve."""
        return refined(self._factorise(technosphere).solve, technosphere, demand)

    def solve_transposed(self, c: np.ndarray) -> np.ndarray:
        """y with the transposed foreground technosphere times y equal to c."""
        lu = self._factorised()
        return refined(lambda r: lu.solve(r, trans="T"), self.technosphere.T.tocsr(), c)
