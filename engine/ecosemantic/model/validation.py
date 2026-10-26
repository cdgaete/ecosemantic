"""The structural cases a product system must pass before a calculation runs."""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Sequence
from typing import Literal

import numpy as np
import scipy.sparse as sp
from pydantic import BaseModel
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef, Database, ForegroundRef, SystemRef

Node = tuple[uuid.UUID, str]
Verdict = Literal["delivers", "short", "singular"]


class ValidationCase(BaseModel):
    id: str
    passed: bool
    detail: str | None = None


SOLVABLE = frozenset(
    {
        "reference_process_set",
        "no_dangling_references",
        "links_resolve",
        "same_database",
        "database_build",
        "loops_deliver",
    }
)
"""The cases without which the calculation engine cannot solve a stored system. A stored process
always carries a production exchange of a non-zero amount, and a production that evaluates to
zero is refused when the system is materialised, so the production cases never fail here."""


class Issue(BaseModel):
    """What a validation case found wrong, and the processes it names."""

    case: str
    code: str
    message: str
    process_codes: list[str]


class ValidationIssue(Issue):
    """An issue with the remedy `validate_product_system` proposes for it."""

    suggestion: str

    def stated(self) -> Issue:
        """The issue without its remedy, as a write answers it: a model still being written
        is told what is unfinished, and a remedy proposed then, such as deleting a process
        nothing reaches yet, would undo the build."""
        return Issue(
            case=self.case, code=self.code, message=self.message, process_codes=self.process_codes
        )


class Pin(BaseModel):
    """What the store holds for one link of a system: the linked system's name and the link's
    pin as that system now stands when it holds that system, and the system as it stood at the
    link's version with the link's pin there when its log reaches it. A pin is None where the
    system does not carry the case the link names."""

    ref: SystemRef
    name: str | None = None
    current: str | None = None
    at: str | None = None
    document: ProductSystem | None = None


class ValidationReport(BaseModel):
    is_valid: bool
    target: str | None
    roots: list[str]
    cases: list[ValidationCase]
    errors: list[ValidationIssue]


def _edges(product_system: ProductSystem) -> list[tuple[Node, ForegroundRef]]:
    return [
        ((product_system.id, a.code), e.input)
        for a in product_system.processes
        for e in a.exchanges
        if e.type == "product" and isinstance(e.input, ForegroundRef)
    ]


def roots(product_system: ProductSystem) -> list[str]:
    """Codes of the processes no other process in this product system consumes."""
    consumed = {ref.code for (_, code), ref in _edges(product_system) if ref.code != code}
    return sorted(a.code for a in product_system.processes if a.code not in consumed)


def anchors(product_system: ProductSystem) -> list[str]:
    """What a drawing counts its columns from: the reference process, or while none is set the
    roots, which then mark no process as the reference."""
    if product_system.reference_process is not None:
        return [product_system.reference_process]
    return roots(product_system)


class Loop(BaseModel):
    """Processes that feed each other, or one process that uses its own product."""

    codes: list[str]
    credit: bool


def loops(product_system: ProductSystem) -> list[Loop]:
    """Every loop among the processes, through inputs local to the system. An input runs
    against its loop, a credit, when its sign differs from its provider's production, as an
    avoided product's does; waste sent to a treatment, whose production is negative, runs with
    it. An input naming no process is in no loop."""
    processes = product_system.processes
    index = {p.code: i for i, p in enumerate(processes)}
    production = [sum(e.amount for e in p.exchanges if e.type == "production") for p in processes]
    net: dict[tuple[int, int], float] = {}
    for j, process in enumerate(processes):
        for e in process.exchanges:
            ref = e.input
            if (
                e.type != "production"
                and e.amount != 0
                and isinstance(ref, ForegroundRef)
                and ref.code in index
            ):
                net[(index[ref.code], j)] = net.get((index[ref.code], j), 0.0) + e.amount
    fed = np.zeros((len(processes), len(processes)), dtype=bool)
    for i, j in net:
        fed[i, j] = True
    _, labels = connected_components(sp.csr_matrix(fed), directed=True, connection="strong")
    found: list[Loop] = []
    for label in np.unique(labels):
        members = {int(m) for m in np.flatnonzero(labels == label)}
        if len(members) == 1 and not fed[next(iter(members)), next(iter(members))]:
            continue
        credit = any(
            i != j and i in members and j in members and np.sign(production[i]) * amount < 0
            for (i, j), amount in net.items()
        )
        found.append(Loop(codes=sorted(processes[m].code for m in members), credit=credit))
    return sorted(found, key=lambda loop: loop.codes)


def verdict(block: np.ndarray) -> Verdict:
    """Whether a loop's supply meeting a unit of each of its products is positive throughout, or
    its block singular."""
    try:
        supply = splu(sp.csc_matrix(block)).solve(np.ones(block.shape[0]))
    except RuntimeError:
        return "singular"
    return "delivers" if (supply > 0).all() else "short"


def undelivered(block: np.ndarray, credit: bool) -> Verdict | None:
    """Why a loop's signed block delivers none of what the loop makes: singular, or short for a
    loop without a credit; None when it delivers, or when a credit leaves a short loop to its
    amounts. Validation and the calculation engine both refuse a loop by this verdict."""
    found = verdict(block)
    if found == "singular" or (found == "short" and not credit):
        return found
    return None


def loop_block(product_system: ProductSystem, loop: Loop) -> np.ndarray:
    """A loop's square block as the engine solves it: each member's production less what it uses
    of its own product on the diagonal, what it uses of another member's product off it, every
    row signed by its production."""
    index = {code: i for i, code in enumerate(loop.codes)}
    block = np.zeros((len(index), len(index)))
    production = np.zeros(len(index))
    for code, j in index.items():
        for e in product_system.process(code).exchanges:
            if e.type == "production":
                block[j, j] += e.amount
                production[j] += e.amount
            elif isinstance(e.input, ForegroundRef) and e.input.code in index:
                block[index[e.input.code], j] -= e.amount
    return np.sign(production)[:, None] * block


class Stuck(BaseModel):
    """A loop that delivers nothing: its codes, how a message names them, and why."""

    codes: list[str]
    named: str
    message: str


def _undelivering(product_system: ProductSystem, owner: str | None) -> list[Stuck]:
    """Each loop of the system that delivers nothing."""
    found: list[Stuck] = []
    for loop in loops(product_system):
        if undelivered(loop_block(product_system, loop), loop.credit) is None:
            continue
        named = ", ".join(c if owner is None else f"{c} of {owner}" for c in loop.codes)
        if len(loop.codes) > 1:
            message = f"{named} feed each other and deliver none of what they make"
            found.append(Stuck(codes=loop.codes, named=named, message=message))
            continue
        process = product_system.process(loop.codes[0])
        made = sum(e.amount for e in process.exchanges if e.type == "production")
        own = sum(
            e.amount
            for e in process.exchanges
            if e.type != "production"
            and isinstance(e.input, ForegroundRef)
            and e.input.code == process.code
        )
        message = f"{named} uses {own:g} of its own product and makes {made:g}; it delivers none"
        found.append(Stuck(codes=loop.codes, named=named, message=message))
    return found


def credit_loops(product_system: ProductSystem) -> list[list[str]]:
    """The codes of each loop holding a credit, whose delivery a calculation does not decide."""
    return [loop.codes for loop in loops(product_system) if loop.credit]


def reference_of(product_system: ProductSystem, parameter: str) -> str:
    """The reference process's code; Invalid names the parameter to set when there is none."""
    if product_system.reference_process is None:
        raise Invalid(
            f"{product_system.name} has no reference process; set one with "
            f"update_product_system or name a {parameter}"
        )
    return product_system.reference_process


def off_build(documents: Sequence[ProductSystem], installed: Database) -> list[ProductSystem]:
    """The documents that name a build of their database other than the installed one, or
    none: a calculation over the installed build refuses them."""
    return [d for d in documents if d.database.fingerprint != installed.fingerprint]


class Backwards(BaseModel):
    """A product exchange sending a positive amount to a treatment, and the system holding it
    when that is not the one asked about."""

    owner: str | None
    code: str
    exchange: str
    amount: float

    @property
    def named(self) -> str:
        """The process, its system when another, the exchange and its amount."""
        where = self.code if self.owner is None else f"{self.code} of {self.owner}"
        return f"{where} · {self.exchange} at {self.amount:g}"


def sent_backwards(
    documents: Sequence[tuple[str | None, ProductSystem]], treatments: frozenset[BackgroundRef]
) -> list[Backwards]:
    """Each product exchange of these documents, each with the name of the system holding it or
    None for the one asked about, that sends a positive amount to a treatment: a treatment takes
    its waste in, so waste goes to it as a negative input, and a positive one runs it
    backwards."""
    return [
        Backwards(owner=owner, code=process.code, exchange=exchange.name, amount=exchange.amount)
        for owner, document in documents
        for process in document.processes
        for exchange in process.exchanges
        if exchange.type == "product"
        and isinstance(exchange.input, BackgroundRef)
        and exchange.input in treatments
        and exchange.amount > 0
    ]


def validate(
    product_system: ProductSystem,
    target_code: str | None = None,
    pins: Sequence[Pin] = (),
    installed: Database | None = None,
    treatments: frozenset[BackgroundRef] | None = None,
) -> ValidationReport:
    """Run every structural case against the target, the reference process unless one is named,
    and report each one; the cases that read a target run only when there is one, the case of
    the database build only when `installed` names the build the store holds, and the case of
    waste sent to a treatment only when `treatments` names the background processes whose
    reference is the waste they take in. `pins` holds what the store holds for each link of the
    system."""
    code = target_code if target_code is not None else product_system.reference_process
    root_codes = roots(product_system)
    cases: list[ValidationCase] = []
    errors: list[ValidationIssue] = []

    def record(
        case_id: str,
        passed: bool,
        code: str,
        message: str,
        codes: list[str],
        hint: str,
        detail: str | None = None,
    ) -> None:
        named = detail or ", ".join(codes) or message
        cases.append(ValidationCase(id=case_id, passed=passed, detail=None if passed else named))
        if not passed:
            errors.append(
                ValidationIssue(
                    case=case_id,
                    code=code,
                    message=message,
                    process_codes=codes,
                    suggestion=hint,
                )
            )

    record(
        "reference_process_set",
        product_system.reference_process is not None,
        "reference_process_missing",
        f"{product_system.name} names no reference process",
        [],
        f"set reference_process to {root_codes[0]!r}"
        if len(root_codes) == 1
        else "set reference_process to the process whose product is the functional unit",
    )
    if code is not None:
        target = product_system.process(code)
        technosphere = [e for e in target.exchanges if e.type == "product"]
        elementary_flows = [e for e in target.exchanges if e.type == "elementary"]
        production = [e for e in target.exchanges if e.type == "production"]
        record(
            "target_has_exchanges",
            bool(technosphere or elementary_flows),
            "target_has_no_exchanges",
            f"{code} has no product or elementary inputs",
            [code],
            "add at least one input before calculating",
        )
        record(
            "target_has_technosphere_input",
            bool(technosphere),
            "target_has_no_technosphere_input",
            f"{code} has no product inputs, so there is no supply chain to solve",
            [code],
            "add at least one product input",
        )
        record(
            "target_has_production",
            bool(production),
            "target_missing_production",
            f"{code} has no production exchange",
            [code],
            "add a production exchange stating the output amount",
        )
        record(
            "production_amount_nonzero",
            not target.produces_nothing(),
            "production_amount_zero",
            f"{code} produces zero",
            [code],
            "set a non-zero production amount",
        )

    nodes: set[Node] = {(product_system.id, a.code) for a in product_system.processes}
    edges = _edges(product_system)
    dangling = [ref.code for _, ref in edges if (product_system.id, ref.code) not in nodes]
    record(
        "no_dangling_references",
        not dangling,
        "dangling_reference",
        f"exchanges reference processes that do not exist: {sorted(set(dangling))}",
        sorted(set(dangling)),
        "create the missing process or remove the exchange",
    )
    other_databases = sorted(
        {
            p.document.database.name
            for p in pins
            if p.document is not None and p.document.database.name != product_system.database.name
        }
    )
    record(
        "same_database",
        not other_databases,
        "database_mismatch",
        f"linked systems use {other_databases}, this one uses {product_system.database.name}",
        [],
        "link only systems on the same database",
        detail=", ".join(other_databases),
    )

    if installed is not None:
        held = [product_system, *(p.document for p in pins if p.document is not None)]
        off = [d.name for d in off_build(held, installed)]
        record(
            "database_build",
            not off,
            "database_build_differs",
            f"{off} name a build of {installed.name} other than the installed "
            f"{str(installed.fingerprint)[:12]}",
            [],
            "install the build it names, or rebase_database moves it onto the installed build",
            detail=", ".join(off),
        )

    if treatments is not None:
        documents = [
            (None, product_system),
            *((p.name or p.document.name, p.document) for p in pins if p.document is not None),
        ]
        backwards = sent_backwards(documents, treatments)
        named = [b.named for b in backwards]
        record(
            "treatments_take_waste",
            not backwards,
            "treatment_runs_backwards",
            "positive inputs to a treatment run it backwards, its emissions counted as credits: "
            + "; ".join(named),
            sorted({b.code for b in backwards if b.owner is None}),
            "negate the amount: waste sent to a treatment is a negative input",
            detail="; ".join(named),
        )

    def _named(pin: Pin) -> str:
        return f"{pin.name or pin.ref.product_system_id} at {str(pin.ref.at_hash)[:12]}"

    unresolved = [
        _named(p)
        for p in pins
        if p.document is None
        or p.document.reference_process is None
        or (p.ref.case is not None and all(c.name != p.ref.case for c in p.document.cases))
    ]
    record(
        "links_resolve",
        not unresolved,
        "link_unresolved",
        "links name no stored state, a system without a reference process, or a case that "
        f"state does not carry: {unresolved}",
        [],
        "link a stored system that names its reference process, under a case it carries",
        detail=", ".join(unresolved),
    )
    behind = [_named(p) for p in pins if p.name is not None and p.current != p.at]
    record(
        "links_current",
        not behind,
        "link_behind",
        f"links name an older state than their system's current one: {behind}",
        [],
        "rebase_links moves them to the current state",
        detail=", ".join(behind),
    )
    base = base_pin(product_system)
    stale = [s.name for s in product_system.scenarios if s.base_hash != base]
    record(
        "scenarios_current",
        not stale,
        "scenario_behind",
        f"scenarios are pinned to a base the system has moved past: {stale}",
        [],
        "rebase_scenario pins each to the base as it now stands",
        detail=", ".join(stale),
    )

    own_stuck = _undelivering(product_system, None)
    stuck = own_stuck + [
        found
        for p in pins
        if p.document is not None
        for found in _undelivering(p.document, p.name or p.document.name)
    ]
    record(
        "loops_deliver",
        not stuck,
        "loop_delivers_nothing",
        "; ".join(s.message for s in stuck),
        sorted({c for s in own_stuck for c in s.codes}),
        "make each loop, and each process using its own product, make more than it uses",
        detail="; ".join(s.named for s in stuck),
    )

    if code is not None:
        out: dict[Node, list[Node]] = {}
        for source, ref in edges:
            out.setdefault(source, []).append((product_system.id, ref.code))
        reachable: set[Node] = {(product_system.id, code)}
        queue: deque[Node] = deque(reachable)
        while queue:
            node = queue.popleft()
            for nxt in out.get(node, []):
                if nxt not in reachable:
                    reachable.add(nxt)
                    queue.append(nxt)
        islands = sorted(
            c for pid, c in nodes if pid == product_system.id and (pid, c) not in reachable
        )
        record(
            "no_islands",
            not islands,
            "island_activities_detected",
            f"processes not reachable from {code}: {islands}",
            islands,
            "connect them to the supply chain of the target or delete them",
        )

    ordered = sorted(cases, key=lambda c: c.id)
    return ValidationReport(
        is_valid=all(c.passed for c in cases),
        target=code,
        roots=root_codes,
        cases=ordered,
        errors=errors,
    )
