from __future__ import annotations

import dataclasses
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from urllib.parse import parse_qs, urlsplit

from ecosemantic.events import EventKind
from ecosemantic.mcp.accounts import ACCOUNTS_PATH, Reach
from ecosemantic.mcp.calculation import result_link
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.discovery import VocabularyKind
from ecosemantic.mcp.installs import databases_link
from ecosemantic.mcp.runs import simulation_link
from ecosemantic.model.entities import (
    ActorKind,
    DemandItem,
    ExchangeType,
    ProductSystem,
    Scope,
    UncertaintyType,
)
from ecosemantic.model.refs import ForegroundRef, Scheme
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
    MonteCarloConfig,
    Origin,
    RequestKind,
    Resolution,
    Run,
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
PATHS = REPOSITORY / "page" / "src" / "lib" / "paths.ts"
STREAM = REPOSITORY / "page" / "src" / "api" / "streamKinds.ts"
RESULTS_EDITOR = REPOSITORY / "page" / "src" / "editors" / "results" / "ResultsEditor.tsx"
RESULT_PARAMS = REPOSITORY / "page" / "src" / "editors" / "results" / "params.ts"
CALCULATION = REPOSITORY / "mcp" / "ecosemantic" / "mcp" / "calculation.py"

VIEW = "http://127.0.0.1:8765"
RESULT_QUERY = {"method_id", "impact_method", "variants", "amount"}

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
    "Reach": Reach,
}

STRING_UNION = r"'[^']*'(?:\s*\|\s*'[^']*')+"
UNION = re.compile(
    rf"^export type (\w+) =\s*\|?\s*({STRING_UNION})(?:\s*\|\s*null)?[ \t]*(?://[^\n]*)?$",
    re.MULTILINE,
)
ANY_UNION = re.compile(STRING_UNION)
NULL = re.compile(r"\|\s*null\b|\bnull\s*\|")
QUOTED = re.compile(r'"[^"\n]*"')
STREAM_ARRAY = re.compile(r"STREAM_KINDS\s*=\s*\[([^\]]*)\]")
BUILDER = re.compile(r"(\w+):\s*\([^)]*\)\s*=>\s*[`']([^`']*)[`'],?[ \t]*$", re.MULTILINE)
PLACEHOLDERS = re.compile(r"(?:\$\{[^}]*\})+")
ROUTE = re.compile(r'path="([^"]+)"')
READ_KEY = re.compile(r"\.get\('([^']*)'\)")
RESULT_PAGE = re.compile(r'result_link\(\s*context,\s*[^,]+,\s*"([^"]+)"')
SINGLE_QUOTED = re.compile(r"'([^']*)'")


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


def stream_kinds(source: str | None = None) -> set[str]:
    """Every event kind the page's stream subscribes to."""
    if source is None:
        source = STREAM.read_text(encoding="utf-8")
    declared = STREAM_ARRAY.search(source)
    assert declared is not None
    return set(SINGLE_QUOTED.findall(declared.group(1)))


def page_builders(source: str | None = None) -> dict[str, re.Pattern[str]]:
    """The path each builder of `paths.ts` produces, its placeholders matching one segment."""
    if source is None:
        source = PATHS.read_text(encoding="utf-8")
    return {
        name: re.compile("[^/?#]+".join(re.escape(part) for part in PLACEHOLDERS.split(template)))
        for name, template in BUILDER.findall(source)
    }


def result_page_names(source: str | None = None) -> list[str]:
    """The result pages Python's calls of `result_link` write."""
    if source is None:
        source = CALCULATION.read_text(encoding="utf-8")
    return RESULT_PAGE.findall(source)


def test_the_page_subscribes_to_every_event_kind() -> None:
    assert stream_kinds() == set(get_args(EventKind))


def test_every_page_route_python_writes_is_one_the_page_serves(
    context: ServerContext, product_system: ProductSystem
) -> None:
    bound = dataclasses.replace(context, view_url=VIEW)
    builders = page_builders()
    routed = set(ROUTE.findall(RESULTS_EDITOR.read_text(encoding="utf-8")))
    read = set(READ_KEY.findall(RESULT_PARAMS.read_text(encoding="utf-8")))
    reference = product_system.reference_process
    assert reference is not None
    run = Run(
        id=uuid.uuid4(),
        product_system_id=product_system.id,
        at_hash="fixture",
        config=MonteCarloConfig(),
        posted_at=datetime.now(UTC),
    )
    for link in (
        bound.deep_link(product_system.id),
        simulation_link(bound, run),
        databases_link(bound),
        bound.page_at(ACCOUNTS_PATH),
    ):
        assert link is not None
        assert any(p.fullmatch(urlsplit(link).path) for p in builders.values()), link
    pages = result_page_names()
    assert pages
    for page in pages:
        link = result_link(
            bound,
            product_system,
            page,
            method_id="gwp",
            impact_method="gwp",
            variants=("a", "b"),
            demand=[DemandItem(ref=ForegroundRef(code=reference), amount=2.0)],
        )
        assert link is not None
        assert page in routed, page
        assert any(p.fullmatch(urlsplit(link).path) for p in builders.values()), link
        assert RESULT_QUERY <= set(parse_qs(urlsplit(link).query)) <= read, page
