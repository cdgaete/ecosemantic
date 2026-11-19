"""The canonical shape an elementary flow is read into, applied to what a publisher wrote.

One module of rules that hold for a whole publisher convention: the compartment a category
path names, the CAS number a field holds, the category and indicator a method's name parts into,
and the JSON-LD record those rules rewrite. The publisher's spellings are read here and nowhere
else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ecosemantic.ports.types import FLOW_TYPE_OF, CompartmentName, FlowType

_ELEMENTARY_ROOT = "elementary flows"
_CATEGORY_ROOT = "Elementary flows"
_COMPARTMENT_OF: dict[str, CompartmentName] = {
    "air": "air",
    "water": "water",
    "soil": "soil",
    "immaterial": "immaterial",
    "natural resource": "natural resource",
    "economic": "economic",
    "inventory indicator": "inventory indicator",
    "emission to air": "air",
    "emissions to air": "air",
    "emission to water": "water",
    "emissions to water": "water",
    "emission to soil": "soil",
    "emissions to soil": "soil",
    "resource": "natural resource",
    "resources": "natural resource",
    "immaterial emission": "immaterial",
    "immaterial emissions": "immaterial",
}
_MEDIUM_OF: dict[str, CompartmentName] = {
    "air": "air",
    "water": "water",
    "ground": "soil",
    "soil": "soil",
    "economic": "economic",
}
_CAS = re.compile(r"0*(\d{2,7})-(\d{2})-(\d)")
_METHOD_SEPARATOR = " > "
UNSTATED = "UNSTATED"
UNSTATED_NAME = "Not stated by the publisher"


@dataclass(frozen=True)
class Placement:
    """The compartment a flow's category path names, the sub-compartment it keeps, and the flow
    type that compartment refines."""

    compartment: CompartmentName
    sub_compartment: str | None

    @property
    def flow_type(self) -> FlowType:
        """The flow type the compartment refines."""
        return FLOW_TYPE_OF[self.compartment]


def place(category: str | None) -> Placement | None:
    """The placement a flow's category path names, or None when no rule places it."""
    segments = _segments(category)
    if not segments:
        return None
    top, rest = segments[0], segments[1:]
    if top.casefold() == "ecosystem services":
        return Placement(compartment="natural resource", sub_compartment=", ".join([top, *rest]))
    compartment = _COMPARTMENT_OF.get(top.casefold())
    if compartment is not None:
        return Placement(compartment=compartment, sub_compartment=", ".join(rest) or None)
    if top.casefold() == "emission":
        return _medium_first(rest)
    return None


def unrooted_path(category: str | None) -> str:
    """The category path without the `Elementary flows` root, its segments joined by `/`."""
    return "/".join(_segments(category))


def category_path(placement: Placement) -> str:
    """The category path a placement is written as."""
    if placement.sub_compartment is None:
        return f"{_CATEGORY_ROOT}/{placement.compartment}"
    return f"{_CATEGORY_ROOT}/{placement.compartment}/{placement.sub_compartment}"


def cas_number(text: str | None) -> tuple[str | None, str | None]:
    """The CAS number the text is and the text as published: a number without leading zeros and
    nothing else, or no number and the text unchanged."""
    if text is None:
        return (None, None)
    published = text.strip()
    if not published:
        return (None, None)
    match = _CAS.fullmatch(published)
    if match is None:
        return (None, published)
    first, second, check = match.groups()
    weighted = sum(
        int(digit) * weight for weight, digit in enumerate(reversed(first + second), start=1)
    )
    if weighted % 10 != int(check):
        return (None, published)
    return (f"{int(first)}-{second}-{check}", None)


def method_parts(name: str) -> tuple[str, str]:
    """The category and the indicator a method's name holds, split at its first separator."""
    category, separator, indicator = name.partition(_METHOD_SEPARATOR)
    if not separator:
        return (name, name)
    return (category, indicator)


def canonical_flow_record(record: dict[str, object]) -> dict[str, object]:
    """The elementary flow record with its category placed and its CAS number valid, every other
    record and key as it was written."""
    canonical = dict(record)
    if canonical.get("@type") != "Flow" or canonical.get("flowType") != "ELEMENTARY_FLOW":
        return canonical
    placement = place(_text(canonical.get("category")))
    if placement is not None:
        canonical["category"] = category_path(placement)
    number, _ = cas_number(_text(canonical.get("cas")))
    if number is not None:
        canonical["cas"] = number
    return canonical


def _segments(category: str | None) -> list[str]:
    """The path's segments, trimmed, without an empty one and without a leading
    `Elementary flows` root."""
    if category is None:
        return []
    kept = [segment.strip() for segment in category.split("/") if segment.strip()]
    if kept and kept[0].casefold() == _ELEMENTARY_ROOT:
        return kept[1:]
    return kept


def _medium_first(segments: list[str]) -> Placement | None:
    """The placement of a type-first path, whose first segment naming a medium is its compartment
    and whose other segments are joined in order."""
    for position, segment in enumerate(segments):
        compartment = _MEDIUM_OF.get(segment.casefold())
        if compartment is not None:
            kept = [*segments[:position], *segments[position + 1 :]]
            return Placement(compartment=compartment, sub_compartment=", ".join(kept) or None)
    return None


def _text(value: object) -> str | None:
    """The value when it is a string, since a JSON-LD field may hold any JSON value."""
    return value if isinstance(value, str) else None
