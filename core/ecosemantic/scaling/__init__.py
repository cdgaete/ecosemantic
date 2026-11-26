"""Each card's exchanges scaled to one unit of the functional unit, from the activity levels the
calculation engine answers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from pydantic import BaseModel

from ecosemantic.errors import Invalid
from ecosemantic.geometry import linked_code
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import ForegroundRef, LinkedProcessRef, SystemRef
from ecosemantic.model.validation import linked_reference
from ecosemantic.ports.types import Activity


class Scaled(BaseModel):
    """How many times a card's process runs, and each of its exchanges at that level."""

    activity: float
    amounts: dict[uuid.UUID, float]


class ScaledRow(BaseModel):
    """One exchange of a card as its scaled amount: which exchange, what it is called, how much
    of it at the card's activity, and its unit."""

    exchange_id: uuid.UUID
    name: str
    amount: float
    unit: str


def _production(reference: Process, other: ProductSystem) -> Exchange:
    """The production exchange of a linked system's reference process; Invalid naming both when
    it has none."""
    productions = [x for x in reference.exchanges if x.type == "production"]
    if not productions:
        raise Invalid(f"{reference.code} of {other.name} has no production exchange")
    return productions[0]


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
            reference = linked_reference(other, system.name)
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
            level, production = levels[0], _production(reference, other)
            found[linked_code(e.input)] = Scaled(
                activity=level, amounts={production.id: level * production.amount}
            )
    return found


def scaled_rows(
    system: ProductSystem,
    linked: Mapping[uuid.UUID, ProductSystem],
    scaled: Mapping[str, Scaled],
    code: str,
) -> list[ScaledRow]:
    """The rows of one card scaled: a process's exchanges in their order, production included, and
    a linked system's single row, the production of the reference process it links."""
    for process in system.processes:
        if process.code == code:
            amounts = scaled[code].amounts
            return [
                ScaledRow(
                    exchange_id=exchange.id,
                    name=exchange.name,
                    amount=amounts[exchange.id],
                    unit=exchange.unit,
                )
                for exchange in process.exchanges
            ]
    for process in system.processes:
        for exchange in process.exchanges:
            if not isinstance(exchange.input, SystemRef):
                continue
            if linked_code(exchange.input) != code:
                continue
            other = linked[exchange.input.product_system_id]
            reference = linked_reference(other, system.name)
            production = _production(reference, other)
            return [
                ScaledRow(
                    exchange_id=production.id,
                    name=production.name,
                    amount=scaled[code].amounts[production.id],
                    unit=production.unit,
                )
            ]
    raise Invalid(f"this drawing has no card {code!r}: read the drawing for the cards it draws")
