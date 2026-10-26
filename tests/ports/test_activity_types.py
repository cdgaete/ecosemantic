from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from ecosemantic.errors import Invalid
from ecosemantic.ports.types import Call, checked_agent, open_trail, trail
from tests.conformance.activity import OTHER, SYSTEM, draft


def call(agent: str, tool: str, minute: int, **fields: object) -> Call:
    return Call(id=uuid.uuid4(), **draft(agent, tool, minute, **fields).model_dump())


def test_a_name_follows_the_rule_or_is_refused() -> None:
    assert checked_agent("electricity-2.a_b") == "electricity-2.a_b"
    for bad in ("", "-leading", "has space", "a/b", "x" * 65):
        with pytest.raises(Invalid):
            checked_agent(bad)


def test_a_draft_refuses_a_name_that_is_not_one() -> None:
    with pytest.raises(ValidationError):
        draft("../elsewhere", "a", 1)


def test_a_trail_is_the_agents_calls_since_its_preceding_write() -> None:
    calls = [
        call("electricity", "create_process", 1, product_system_id=SYSTEM, entry_seq=2),
        call("electricity", "search_processes", 2),
        call("packaging", "search_processes", 3),
        call("electricity", "get_background_process", 4),
        call("electricity", "create_exchange", 5, product_system_id=SYSTEM, entry_seq=3),
        call("electricity", "search_processes", 6),
    ]
    found = trail(calls, SYSTEM, 3)
    assert [c.tool for c in found] == [
        "search_processes",
        "get_background_process",
        "create_exchange",
    ]


def test_the_first_write_of_an_agent_takes_every_call_before_it() -> None:
    calls = [
        call("electricity", "search_processes", 1),
        call("electricity", "create_process", 2, product_system_id=SYSTEM, entry_seq=2),
    ]
    assert [c.tool for c in trail(calls, SYSTEM, 2)] == ["search_processes", "create_process"]


def test_an_entry_no_recorded_call_appended_has_no_trail() -> None:
    calls = [call("electricity", "create_process", 1, product_system_id=SYSTEM, entry_seq=2)]
    assert trail(calls, SYSTEM, 9) == [] and trail(calls, OTHER, 2) == []


def test_an_open_trail_is_the_agents_calls_after_its_latest_write() -> None:
    calls = [
        call("electricity", "search_processes", 1),
        call("electricity", "create_exchange", 2, product_system_id=SYSTEM, entry_seq=3),
        call("packaging", "search_processes", 3),
        call("electricity", "search_processes", 4),
        call("electricity", "get_background_process", 5),
    ]
    assert [c.tool for c in open_trail(calls, "electricity")] == [
        "search_processes",
        "get_background_process",
    ]
    assert [c.tool for c in open_trail(calls, "packaging")] == ["search_processes"]


def test_an_agent_whose_latest_call_wrote_has_no_open_trail() -> None:
    calls = [call("electricity", "create_process", 1, product_system_id=SYSTEM, entry_seq=2)]
    assert open_trail(calls, "electricity") == []
    assert open_trail(calls, "nobody") == []


def test_an_open_trail_under_a_system_keeps_the_calls_that_name_it_or_none() -> None:
    calls = [
        call("electricity", "create_exchange", 1, product_system_id=SYSTEM, entry_seq=3),
        call("electricity", "search_processes", 2),
        call("electricity", "validate_product_system", 3, product_system_id=OTHER),
        call("electricity", "get_product_system", 4, product_system_id=SYSTEM),
    ]
    assert [c.tool for c in open_trail(calls, "electricity", SYSTEM)] == [
        "search_processes",
        "get_product_system",
    ]
    assert len(open_trail(calls, "electricity")) == 3
