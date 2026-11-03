from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from ecosemantic.events import EventKind
from ecosemantic.mcp.discovery import VocabularyKind
from ecosemantic.model.entities import ActorKind, ExchangeType, Scope, UncertaintyType
from ecosemantic.model.refs import Scheme
from ecosemantic.ports.types import (
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
}

UNION = re.compile(r"^export type (\w+) =((?:\s*\|?\s*'[^']*')+)\s*$", re.MULTILINE)


def page_vocabularies() -> dict[str, set[str]]:
    source = TYPES.read_text(encoding="utf-8")
    return {name: set(re.findall(r"'([^']*)'", body)) for name, body in UNION.findall(source)}


def test_every_page_vocabulary_has_its_python_literal() -> None:
    assert set(page_vocabularies()) == set(VOCABULARIES)


def test_each_page_vocabulary_spells_the_values_python_spells() -> None:
    page = page_vocabularies()
    for name, literal in VOCABULARIES.items():
        assert page[name] == set(get_args(literal)), name
