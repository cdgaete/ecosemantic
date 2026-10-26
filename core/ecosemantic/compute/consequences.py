"""What a write left stale: the scenarios it staled, the links it left behind, and the issues
validation reports on the document it wrote, stated without their remedies."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from ecosemantic.compute.links import link_pin, pins
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef, SystemRef
from ecosemantic.model.validation import Issue, validate


class LinkBehind(BaseModel):
    """A stored system whose link to the written one no longer buys what the system offers."""

    product_system_id: uuid.UUID
    name: str


class Consequences(BaseModel):
    """What a write left for its author to do: rebase the scenarios it staled, rebase the links
    it left behind, and finish what the issues name; `validate_product_system` carries their
    remedies."""

    scenarios_staled: list[str] = Field(default_factory=list)
    links_behind: list[LinkBehind] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)


def _stated(after: ProductSystem, treatments: frozenset[BackgroundRef] | None) -> list[Issue]:
    return [issue.stated() for issue in validate(after, treatments=treatments).errors]


def consequences(
    before: ProductSystem | None,
    after: ProductSystem,
    linking: Sequence[ProductSystem],
    at_pins: Mapping[SystemRef, str | None],
    treatments: frozenset[BackgroundRef] | None = None,
) -> Consequences:
    """The consequences of writing `after` over `before`, given the stored systems that link it
    and each of their links' pins at the version it names: the scenarios pinned to the base
    before and not after, the systems a link of which is behind after the write and was not
    before, and the issues of `after`, the case of waste sent to a treatment among them when
    `treatments` names the background's treatments."""
    if before is None:
        return Consequences(issues=_stated(after, treatments))
    was, now = base_pin(before), base_pin(after)
    staled = sorted(s.name for s in after.scenarios if s.base_hash == was != now)
    behind = [
        LinkBehind(product_system_id=system.id, name=system.name)
        for system in linking
        if any(
            link_pin(after, ref) != at_pins[ref] == link_pin(before, ref)
            for ref in pins(system)
            if ref.product_system_id == after.id
        )
    ]
    return Consequences(
        scenarios_staled=staled, links_behind=behind, issues=_stated(after, treatments)
    )
