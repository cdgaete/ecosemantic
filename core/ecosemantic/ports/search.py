"""Text search over one background database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.ports.terms import tokens
from ecosemantic.ports.types import ElementaryFlowHit, FlowType, Page, ProcessHit


@dataclass(frozen=True)
class Phrase:
    """A query term's tokens, matched adjacent and in order within one field; with `prefix`, the
    last token matches any token that begins with it."""

    tokens: tuple[str, ...]
    prefix: bool


def phrases(query: str) -> list[Phrase]:
    """The phrases of a query: terms split on whitespace with double quotes dropped, a term
    ending in `*` a prefix, a term that is only `*` dropped; Invalid when no term is left. A term
    with no token matches nothing and is left out, so a query of such terms only matches
    nothing."""
    terms = [t.replace('"', "") for t in query.split()]
    terms = [t for t in terms if t.strip("*")]
    if not terms:
        raise Invalid("a search needs at least one term")
    found = []
    for term in terms:
        prefix = term.endswith("*")
        words = tokens(term[:-1] if prefix else term)
        if words:
            found.append(Phrase(tokens=tuple(words), prefix=prefix))
    return found


@runtime_checkable
class SearchPort(Protocol):
    async def processes(
        self,
        database: str,
        query: str,
        location: str | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[ProcessHit]: ...

    async def elementary_flows(
        self,
        database: str,
        query: str,
        compartment: str | None = None,
        sub_compartment: str | None = None,
        flow_type: FlowType | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[ElementaryFlowHit]: ...

    async def methods(
        self, database: str, query: str, limit: int = 20, cursor: str | None = None
    ) -> Page[Method]: ...
