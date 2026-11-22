from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from ecosemantic.model.entities import Actor, Person
from ecosemantic.ports.types import Call, trail
from tests.conformance.activity import SYSTEM, draft


def a_call(agent: str, minute: int, **fields: object) -> Call:
    return Call(id=uuid.uuid4(), **draft(agent, "create_process", minute, **fields).model_dump())


def test_an_actor_without_a_person_dumps_as_before() -> None:
    before = '{"kind":"agent","id":"mcp","name":null}'
    assert Actor(kind="agent", id="mcp").model_dump_json() == before


def test_an_agent_names_who_it_acts_for() -> None:
    actor = Actor(kind="agent", id="mcp", on_behalf_of=Person(id="p"))
    dumped = actor.model_dump_json()
    assert dumped.endswith('"on_behalf_of":{"id":"p","name":null}}')
    assert Actor.model_validate_json(dumped) == actor


def test_a_person_acts_for_no_one() -> None:
    with pytest.raises(ValidationError):
        Actor(kind="person", on_behalf_of=Person(id="p"))


def test_a_person_has_an_id() -> None:
    with pytest.raises(ValidationError):
        Person(id="")


def test_a_call_without_a_person_dumps_no_person() -> None:
    assert "person" not in draft("claude", "search_processes", 1).model_dump()


def test_a_trail_keeps_two_people_s_agents_apart() -> None:
    ana, ben = Person(id="a"), Person(id="b")
    calls = [
        a_call("claude", 1, person=ana),
        a_call("claude", 2, person=ben),
        a_call("claude", 3, person=ana, product_system_id=SYSTEM, entry_seq=1),
        a_call("claude", 4, person=ben, product_system_id=SYSTEM, entry_seq=2),
    ]
    assert [one.person for one in trail(calls, SYSTEM, 1)] == [ana, ana]
    assert [one.person for one in trail(calls, SYSTEM, 2)] == [ben, ben]


def test_a_trail_follows_a_person_s_id_through_a_new_name() -> None:
    calls = [
        a_call("claude", 1, person=Person(id="a", name="Ana")),
        a_call(
            "claude",
            2,
            person=Person(id="a", name="Ana G."),
            product_system_id=SYSTEM,
            entry_seq=1,
        ),
    ]
    assert len(trail(calls, SYSTEM, 1)) == 2
