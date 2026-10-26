from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import Actor
from ecosemantic.package.requests import (
    REQUESTS_FILE,
    next_request,
    read_requests,
    resolve,
    write_requests,
)
from ecosemantic.package.sidecar import SIDECAR_DIR
from ecosemantic.ports.types import Outcome, RequestDraft

PERSON = Actor(kind="person", name="Carlos")
AGENT = Actor(kind="agent", id="mcp")
HASH = "a" * 64


def _draft(kind: str, **extra: str) -> RequestDraft:
    return RequestDraft(actor=PERSON, kind=kind, at_hash=HASH, message="check this", **extra)


def _outcome(resolution: str = "accepted") -> Outcome:
    return Outcome(timestamp=datetime.now(UTC), actor=AGENT, resolution=resolution, message="done")


def test_next_request_counts_from_one_and_is_open() -> None:
    first = next_request([], _draft("return"))
    second = next_request([first], _draft("approve"))
    assert (first.seq, second.seq) == (1, 2)
    assert first.open and not second.open
    assert first.outcome is None and first.id != second.id


def test_an_edit_names_its_entity_and_nothing_else_does() -> None:
    edit = _draft("edit", entity="exchange", entity_id="abc")
    assert edit.entity == "exchange"
    with pytest.raises(ValueError, match="entity"):
        _draft("edit")
    with pytest.raises(ValueError, match="entity"):
        _draft("return", entity="process", entity_id="widget")


def test_a_request_is_posted_by_a_person() -> None:
    with pytest.raises(ValueError, match="person"):
        RequestDraft(actor=AGENT, kind="return", at_hash=HASH, message="x")


def test_resolve_sets_the_outcome_once() -> None:
    request = next_request([], _draft("return"))
    resolved = resolve([request], request.id, _outcome("overridden"))
    assert resolved[0].outcome is not None and resolved[0].outcome.resolution == "overridden"
    assert not resolved[0].open
    with pytest.raises(Conflict):
        resolve(resolved, request.id, _outcome())
    with pytest.raises(NotFound):
        resolve(resolved, uuid.uuid4(), _outcome())


def test_an_approval_is_never_resolved() -> None:
    approval = next_request([], _draft("approve"))
    with pytest.raises(Invalid, match="approval"):
        resolve([approval], approval.id, _outcome())


def test_the_file_round_trips_beside_the_log(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    assert read_requests(root) == []
    first = next_request([], _draft("return"))
    write_requests(root, [first])
    assert (root / SIDECAR_DIR / REQUESTS_FILE).is_file()
    assert read_requests(root) == [first]


def test_the_json_carries_open_and_the_file_does_not(tmp_path: Path) -> None:
    request = next_request([], _draft("return"))
    assert request.model_dump(mode="json")["open"] is True
    root = tmp_path / "pkg"
    write_requests(root, [request])
    assert '"open"' not in (root / SIDECAR_DIR / REQUESTS_FILE).read_text()
    assert read_requests(root)[0].open is True
