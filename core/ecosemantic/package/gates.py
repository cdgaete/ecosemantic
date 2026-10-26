"""The product systems a database build carries, and the checks every build passes before it
writes anything."""

from __future__ import annotations

from pathlib import Path

from ecosemantic.compute.links import held_pins, pins
from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.validation import validate
from ecosemantic.ports.storage import StoragePort


async def gathered(storage: StoragePort) -> list[ProductSystem]:
    """Every stored product system at its current state."""
    return [await storage.get_product_system(s.id) for s in await storage.list_product_systems()]


def refuse_existing(destination: Path) -> None:
    """Nothing, or Conflict when the destination exists."""
    if destination.exists():
        raise Conflict(f"{destination.name} exists; a version is built once")


async def gate(
    storage: StoragePort, systems: list[ProductSystem], base: str, *, render: bool
) -> None:
    """Nothing, or the first refusal: a system on another database, a system that fails
    validation, a link to a case its system lacks, or, where every system is rendered per case,
    a link naming no case of a system that has cases."""
    elsewhere = sorted(s.name for s in systems if s.database.name != base)
    if elsewhere:
        raise Invalid(f"{elsewhere} are not on {base!r}")
    failing = []
    for system in systems:
        report = validate(system, pins=await held_pins(system, storage))
        if not report.is_valid:
            issues = "; ".join(f"{c.id}: {c.detail}" for c in report.cases if not c.passed)
            failing.append(f"{system.name} ({issues})")
    if failing:
        raise Invalid(f"systems that do not validate: {failing}")
    by_id = {s.id: s for s in systems}
    for system in systems:
        for ref in pins(system):
            target = by_id.get(ref.product_system_id)
            if target is None:
                raise NotFound(
                    f"{system.name} links {ref.product_system_id}, which the build lacks"
                )
            names = [c.name for c in target.cases]
            if (render and ref.case is None and names) or (
                ref.case is not None and ref.case not in names
            ):
                raise NotFound(
                    f"{system.name} links {target.name} under case {ref.case!r}; "
                    f"a release renders {target.name} under {names or ['base']}"
                )
