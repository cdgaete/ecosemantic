"""What the stored systems' links hold on one system, read through the storage port."""

from __future__ import annotations

import uuid

from ecosemantic.compute.links import pinning
from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import ProductSystem
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import LogEntry


async def others(storage: StoragePort, product_system_id: uuid.UUID) -> list[ProductSystem]:
    """Every stored product system but this one, as it now stands."""
    return [
        await storage.get_product_system(summary.id)
        for summary in await storage.list_product_systems()
        if summary.id != product_system_id
    ]


async def refuse_dropped_cases(
    storage: StoragePort, before: ProductSystem, after: ProductSystem
) -> None:
    """Invalid when the write removes a case a stored link names, naming the linking systems."""
    kept = {c.name for c in after.cases}
    dropped = [c.name for c in before.cases if c.name not in kept]
    if not dropped:
        return
    stored = await others(storage, before.id)
    for case in dropped:
        linking = pinning(before.id, stored, case)
        if linking:
            raise Invalid(
                f"case {case!r} of {before.name} is linked by {linking}; move their links first"
            )


async def moved_by(
    storage: StoragePort, product_system_id: uuid.UUID, pin: str | None
) -> LogEntry | None:
    """The first entry of the log that moved the base away from the pin, after a state the pin
    names; None when no state of the log carries that pin."""
    seen = False
    for entry in await storage.log(product_system_id):
        at = base_pin(await storage.get_version(product_system_id, entry.result_hash))
        if at == pin:
            seen = True
        elif seen:
            return entry
    return None
