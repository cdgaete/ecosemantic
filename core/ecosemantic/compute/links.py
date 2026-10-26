"""The systems a product system links through their functional units: the pins its base
exchanges carry, the closure they reach, and the systems that pin one."""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from ecosemantic.compute.overrides import apply_case, case_pin
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import ProductSystem, state_of
from ecosemantic.model.refs import SystemRef
from ecosemantic.model.validation import Pin, credit_loops
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import LinkedLoop

Reader = Callable[[uuid.UUID, str], Awaitable[ProductSystem]]


def pins(system: ProductSystem) -> list[SystemRef]:
    """The links on the system's exchanges, each once, in the order they appear."""
    found: list[SystemRef] = []
    for process in system.processes:
        for exchange in process.exchanges:
            if isinstance(exchange.input, SystemRef) and exchange.input not in found:
                found.append(exchange.input)
    return found


def pinned(ref: SystemRef) -> str:
    """The hash a stored link names."""
    if ref.at_hash is None:
        raise Invalid(f"the link to {ref.product_system_id} names no hash")
    return ref.at_hash


@dataclass(frozen=True)
class Closure:
    """The systems a root reaches through its links, each read at its one pin, the case of it
    the links name, and the system whose link reached each first."""

    documents: dict[uuid.UUID, ProductSystem]
    cases: dict[uuid.UUID, str | None]
    reached_from: dict[uuid.UUID, uuid.UUID]


def _chain(root: ProductSystem, found: Closure, last: uuid.UUID) -> str:
    names = {root.id: root.name, **{k: d.name for k, d in found.documents.items()}}
    path = [last]
    while path[-1] != root.id:
        path.append(found.reached_from[path[-1]])
    return " → ".join(names[i] for i in [*reversed(path), root.id])


async def closure(root: ProductSystem, read: Reader) -> Closure:
    """The systems the root reaches through its links, each read at its pin. Invalid when a link
    leads back to the root, naming the chain, or when one system is reached at two hashes or
    under two cases, naming both links."""
    found = Closure(documents={}, cases={}, reached_from={})
    names = {root.id: root.name}
    queue = deque((root.id, ref) for ref in pins(root))
    while queue:
        owner, ref = queue.popleft()
        target = ref.product_system_id
        if target == root.id:
            raise Invalid(f"a link closes a cycle: {_chain(root, found, owner)}")
        held = found.documents.get(target)
        if held is not None:
            if held.hash != ref.at_hash:
                raise Invalid(
                    f"{held.name} is reached at {held.hash} and at {ref.at_hash}; "
                    "rebase_links so every link names one state of it"
                )
            if found.cases[target] != ref.case:
                first = names[found.reached_from[target]]
                raise Invalid(
                    f"{held.name} is reached under case {found.cases[target]!r} from {first!r} "
                    f"and under case {ref.case!r} from {names[owner]!r}; a calculation merges "
                    "one case of a system"
                )
            continue
        document = await read(target, pinned(ref))
        found.documents[target] = document
        found.cases[target] = ref.case
        found.reached_from[target] = owner
        names[target] = document.name
        queue.extend((target, onward) for onward in pins(document))
    return found


async def linked_documents(root: ProductSystem, read: Reader) -> dict[uuid.UUID, ProductSystem]:
    """Every system the root reaches, at its pin and materialised under the case its links name,
    or its own parameters when they name none, for a calculation."""
    found = await closure(root, read)
    return {k: _resolved(d, found.cases[k]) for k, d in found.documents.items()}


def _resolved(document: ProductSystem, case: str | None) -> ProductSystem:
    if case is None:
        return materialize(document)
    return apply_case(document, document.case(case))


async def pinned_documents(root: ProductSystem, read: Reader) -> dict[uuid.UUID, ProductSystem]:
    """Every system the root reaches, each at its pin as stored, for a writer of the root and of
    the model package that carries them."""
    return (await closure(root, read)).documents


def linked_credit_loops(linked: Iterable[ProductSystem]) -> list[LinkedLoop]:
    """The loops holding a credit inside each linked system, named with the system and its pin."""
    return [
        LinkedLoop(product_system_id=d.id, at_hash=state_of(d), codes=codes)
        for d in linked
        for codes in credit_loops(d)
    ]


def link_pin(document: ProductSystem, ref: SystemRef) -> str | None:
    """The pin a link holds on the document it links: what the linking system merges of it, the
    case the link names or the base; None when the document does not carry that case."""
    if ref.case is None:
        return base_pin(document)
    if all(c.name != ref.case for c in document.cases):
        return None
    return case_pin(document, document.case(ref.case))


def pinning(
    target: uuid.UUID, systems: Iterable[ProductSystem], case: str | None = None
) -> list[str]:
    """The names of the systems whose links name the target, at any of its versions, and under
    the case when one is given."""
    return sorted(
        s.name
        for s in systems
        if any(r.product_system_id == target and (case is None or r.case == case) for r in pins(s))
    )


async def held_pins(system: ProductSystem, storage: StoragePort) -> list[Pin]:
    """Each link of the system with what the store holds for it."""
    held = {s.id: s for s in await storage.list_product_systems()}
    found: list[Pin] = []
    for ref in pins(system):
        summary = held.get(ref.product_system_id)
        if summary is None:
            found.append(Pin(ref=ref))
            continue
        now = await storage.get_product_system(ref.product_system_id)
        reached = {e.result_hash for e in await storage.log(ref.product_system_id)}
        document = (
            await storage.get_version(ref.product_system_id, pinned(ref))
            if ref.at_hash in reached
            else None
        )
        found.append(
            Pin(
                ref=ref,
                name=summary.name,
                current=link_pin(now, ref),
                at=None if document is None else link_pin(document, ref),
                document=document,
            )
        )
    return found
