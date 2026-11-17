"""Text search over one background database."""

from __future__ import annotations

from collections.abc import Sequence
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


CAS_PADDED = 6
"""The digits ecoinvent writes a CAS number's first group in, zeros leading it."""

NO_TERM = "a search needs at least one term"
"""What a query with no term is refused with."""


def spellings(phrase: Phrase) -> tuple[str, ...]:
    """Every spelling a phrase's first token is matched under: the token itself, and for a CAS
    number, three groups of two to seven digits, two digits and one, its first group bare and
    padded with zeros to six digits, so the number finds its flow however a source writes it."""
    first = phrase.tokens[0]
    if phrase.prefix or [len(token) for token in phrase.tokens[1:]] != [2, 1]:
        return (first,)
    bare = first.lstrip("0")
    if not all(token.isdecimal() for token in phrase.tokens) or not 2 <= len(bare) <= 7:
        return (first,)
    return tuple(dict.fromkeys((first, bare, bare.zfill(CAS_PADDED))))


def _terms(query: str) -> list[str]:
    """A query's terms: split on whitespace, double quotes dropped, a term that is only `*`
    dropped."""
    terms = [term.replace('"', "") for term in query.split()]
    return [term for term in terms if term.strip("*")]


def require_term(query: str) -> None:
    """Invalid when the query has no term."""
    if not _terms(query):
        raise Invalid(NO_TERM)


def phrases(query: str) -> list[Phrase]:
    """The phrases of a query, a term ending in `*` a prefix, Invalid when no term is left. A
    term with no token matches nothing and is left out, so a query of such terms only matches
    nothing."""
    require_term(query)
    found = []
    for term in _terms(query):
        prefix = term.endswith("*")
        words = tokens(term[:-1] if prefix else term)
        if words:
            found.append(Phrase(tokens=tuple(words), prefix=prefix))
    return found


def browsed(query: str, filtered: bool) -> list[Phrase] | None:
    """The phrases a query is ranked by, or None when it has no term and a browsing filter is
    given, so the caller lists every row the filter matches; Invalid when it has no term and no
    browsing filter."""
    if filtered and not _terms(query):
        return None
    return phrases(query)


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
        classifications: Sequence[str] | None = None,
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
