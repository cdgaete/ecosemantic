"""Each card's exchanges scaled to one unit of the functional unit, from the activity levels the
calculation engine answers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.geometry import linked_code
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import ForegroundRef, LinkedProcessRef, SystemRef
from ecosemantic.ports.types import Activity


class Scaled(BaseModel):
    """How many times a card's process runs, and each of its exchanges at that level."""

    activity: float
    amounts: dict[uuid.UUID, float]


def scale(
    system: ProductSystem,
    linked: Mapping[uuid.UUID, ProductSystem],
    activities: list[Activity],
) -> dict[str, Scaled]:
    """Every card of the drawing scaled: a process's exchanges times its activity level, and a
    linked system's card its reference process's production at that process's level."""
    own = {a.ref.code: a.level for a in activities if isinstance(a.ref, ForegroundRef)}
    for p in system.processes:
        if p.code not in own:
            raise Invalid(f"the engine answered no activity level for {p.code} of {system.name}")
    found = {
        p.code: Scaled(
            activity=own[p.code],
            amounts={e.id: own[p.code] * e.amount for e in p.exchanges},
        )
        for p in system.processes
    }
    for p in system.processes:
        for e in p.exchanges:
            if not isinstance(e.input, SystemRef):
                continue
            other = linked[e.input.product_system_id]
            if other.reference_process is None:
                raise Invalid(f"{other.name} has no reference process")
            reference = other.process(other.reference_process)
            levels = [
                a.level
                for a in activities
                if isinstance(a.ref, LinkedProcessRef)
                and a.ref.product_system_id == other.id
                and a.ref.code == reference.code
            ]
            if not levels:
                raise Invalid(
                    f"the engine answered no activity level for {reference.code} of {other.name}"
                )
            productions = [x for x in reference.exchanges if x.type == "production"]
            if not productions:
                raise Invalid(f"{reference.code} of {other.name} has no production exchange")
            level, production = levels[0], productions[0]
            found[linked_code(e.input)] = Scaled(
                activity=level, amounts={production.id: level * production.amount}
            )
    return found
