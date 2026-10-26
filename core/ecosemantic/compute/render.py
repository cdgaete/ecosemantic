"""A product system under one case as numbers only: the ids a release gives each dataset, and
the processes that carry them."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from ecosemantic.compute.overrides import apply_case, case_pin
from ecosemantic.compute.parameters import materialize
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import Process, ProductSystem

NAMESPACE = uuid.UUID("3f8a1c52-9d4e-4b7a-8e61-0c2d5b9f7a14")
BASE_CASE = "base"


def product_flow_id(product_system_id: uuid.UUID, code: str) -> str:
    """The id of the product a process of a system makes, the same under every case."""
    return str(uuid.uuid5(NAMESPACE, f"{product_system_id}/{code}"))


def dataset_id(product_system_id: uuid.UUID, code: str, case: str) -> str:
    """The id of a process of a system rendered under a case."""
    return str(uuid.uuid5(NAMESPACE, f"{product_system_id}/{code}/{case}"))


def case_label(case: str | None) -> str:
    """The name a rendering carries: the case's, or `base` for a system without cases."""
    return case if case is not None else BASE_CASE


def cases_of(system: ProductSystem) -> list[str | None]:
    """The cases a release renders a system under: each of its cases, or its base alone."""
    return [c.name for c in system.cases] or [None]


class Rendered(BaseModel):
    """A system's processes under one case, every amount a number and every zero left out."""

    model_config = ConfigDict(frozen=True)

    product_system_id: uuid.UUID
    case: str
    pin: str
    processes: list[Process]


def _numbers(process: Process) -> Process:
    kept = [
        e.model_copy(
            update={
                "formula": None,
                "uncertainty": e.uncertainty.anchored(e.amount) if e.uncertainty else None,
            }
        )
        for e in process.exchanges
        if e.type == "production" or e.amount != 0
    ]
    return process.model_copy(update={"exchanges": kept})


def render(system: ProductSystem, case: str | None) -> Rendered:
    """The system with the case's values set and every formula resolved, as numbers only."""
    if case is None:
        resolved, pin = materialize(system), base_pin(system)
    else:
        chosen = system.case(case)
        resolved, pin = apply_case(system, chosen), case_pin(system, chosen)
    return Rendered(
        product_system_id=system.id,
        case=case_label(case),
        pin=pin,
        processes=[_numbers(p) for p in resolved.processes],
    )
