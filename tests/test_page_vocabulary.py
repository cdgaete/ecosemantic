from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from ecosemantic.events import EventKind
from ecosemantic.mcp.discovery import VocabularyKind
from ecosemantic.model.entities import ActorKind, ExchangeType, Scope, UncertaintyType
from ecosemantic.model.refs import Scheme
from ecosemantic.model.summary import SummaryKind
from ecosemantic.ports.types import (
    CallOutcome,
    ChangeOp,
    CredentialKind,
    Decomposition,
    Effect,
    Entity,
    FlowType,
    InstallStatus,
    Origin,
    RequestKind,
    Resolution,
    RunStatus,
    Side,
    Source,
    SourceName,
    Stopped,
    TreeKind,
)
from ecosemantic.troubles import TroubleKind

REPOSITORY = Path(__file__).resolve().parents[1]
TYPES = REPOSITORY / "page" / "src" / "api" / "types.ts"

VOCABULARIES: dict[str, object] = {
    "Scheme": Scheme,
    "ExchangeType": ExchangeType,
    "UncertaintyType": UncertaintyType,
    "ActorKind": ActorKind,
    "Source": Source,
    "Entity": Entity,
    "Effect": Effect,
    "Origin": Origin,
    "RequestKind": RequestKind,
    "Resolution": Resolution,
    "TroubleKind": TroubleKind,
    "Scope": Scope,
    "Stopped": Stopped,
    "RunStatus": RunStatus,
    "SourceName": SourceName,
    "CredentialKind": CredentialKind,
    "InstallStatus": InstallStatus,
    "TreeKind": TreeKind,
    "Decomposition": Decomposition,
    "FlowType": FlowType,
    "Side": Side,
    "VocabularyKind": VocabularyKind,
    "EventKind": EventKind,
    "ChangeOp": ChangeOp,
    "SummaryKind": SummaryKind,
    "CallOutcome": CallOutcome,
}

STRING_UNION = r"'[^']*'(?:\s*\|\s*'[^']*')+"
UNION = re.compile(
    rf"^export type (\w+) =\s*\|?\s*({STRING_UNION})(?:\s*\|\s*null)?[ \t]*(?://[^\n]*)?$",
    re.MULTILINE,
)
ANY_UNION = re.compile(STRING_UNION)
NULL = re.compile(r"\|\s*null\b|\bnull\s*\|")
QUOTED = re.compile(r'"[^"\n]*"')


def page_vocabularies(source: str | None = None) -> dict[str, set[str]]:
    if source is None:
        source = TYPES.read_text(encoding="utf-8")
    return {name: set(re.findall(r"'([^']*)'", body)) for name, body in UNION.findall(source)}


def inline_unions(source: str | None = None) -> list[str]:
    if source is None:
        source = TYPES.read_text(encoding="utf-8")
    return ANY_UNION.findall(NULL.sub("", UNION.sub("", source)))


def double_quoted(source: str | None = None) -> list[str]:
    if source is None:
        source = TYPES.read_text(encoding="utf-8")
    return QUOTED.findall(source)


def test_every_page_vocabulary_has_its_python_literal() -> None:
    assert set(page_vocabularies()) == set(VOCABULARIES)


def test_each_page_vocabulary_spells_the_values_python_spells() -> None:
    page = page_vocabularies()
    for name, literal in VOCABULARIES.items():
        assert page[name] == set(get_args(literal)), name


def test_no_string_union_is_spelled_inline() -> None:
    assert inline_unions() == []


def test_a_union_with_null_between_its_values_is_found_inline() -> None:
    assert len(inline_unions("  k: 'a' | null | 'b'\n")) == 1


def test_the_page_types_quote_with_single_quotes_only() -> None:
    assert double_quoted() == []


def test_a_double_quoted_literal_is_found() -> None:
    assert double_quoted('  k: "a" | "b"\n') == ['"a"', '"b"']


def test_a_nullable_or_commented_union_is_read() -> None:
    source = "export type A = 'x' | 'y' | null\nexport type B = 'p' | 'q' // note\n"
    assert page_vocabularies(source) == {"A": {"x", "y"}, "B": {"p", "q"}}
