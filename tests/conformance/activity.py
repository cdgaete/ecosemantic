"""The activity port's contract. Subclass with an `activity` fixture that yields an empty one."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.summary import Summary
from ecosemantic.ports.types import CallDraft

SYSTEM = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)


def at(minute: int) -> datetime:
    return datetime(2030, 1, 1, 12, minute, tzinfo=UTC)


def draft(agent: str, tool: str, minute: int, **fields: object) -> CallDraft:
    return CallDraft(
        agent=agent,
        client="claude-code",
        origin="agent",
        tool=tool,
        effect="read",
        started_at=at(minute),
        duration_ms=12,
        outcome="ok",
        **fields,
    )


class ActivityConformance:
    async def test_a_recorded_call_reads_back_whole(self, activity) -> None:
        recorded = await activity.record(
            draft(
                "electricity",
                "search_processes",
                1,
                arguments={"database": "fixture", "query": "electricity"},
                summary=Summary(count=3, more=True),
            )
        )
        read = await activity.get_call(recorded.id)
        assert read == recorded and read.summary == Summary(count=3, more=True)
        assert read.arguments == {"database": "fixture", "query": "electricity"}

    async def test_an_unknown_call_is_not_found(self, activity) -> None:
        with pytest.raises(NotFound):
            await activity.get_call(uuid.uuid4())

    async def test_calls_list_in_the_order_they_started(self, activity) -> None:
        late = await activity.record(draft("electricity", "b", 5))
        early = await activity.record(draft("packaging", "a", 2))
        assert [c.id for c in await activity.list_calls()] == [early.id, late.id]

    async def test_calls_filter_by_agent_system_and_time(self, activity) -> None:
        one = await activity.record(draft("electricity", "a", 1, product_system_id=SYSTEM))
        two = await activity.record(draft("electricity", "b", 2, product_system_id=OTHER))
        three = await activity.record(draft("packaging", "c", 3, product_system_id=SYSTEM))
        assert [c.id for c in await activity.list_calls(agent="electricity")] == [one.id, two.id]
        listed = await activity.list_calls(product_system_id=SYSTEM)
        assert [c.id for c in listed] == [one.id, three.id]
        assert [c.id for c in await activity.list_calls(after=at(1))] == [two.id, three.id]

    async def test_an_agent_name_that_is_not_one_is_refused(self, activity) -> None:
        with pytest.raises(Invalid):
            await activity.list_calls(agent="../elsewhere")

    async def test_agents_list_latest_first_with_their_latest_system(self, activity) -> None:
        await activity.record(draft("electricity", "a", 1, product_system_id=SYSTEM))
        await activity.record(draft("electricity", "b", 4))
        await activity.record(draft("packaging", "c", 2, product_system_id=OTHER))
        electricity, packaging = await activity.list_agents()
        assert (electricity.agent, electricity.calls) == ("electricity", 2)
        assert electricity.product_system_id == SYSTEM and electricity.last_call_at == at(4)
        assert (packaging.agent, packaging.product_system_id) == ("packaging", OTHER)
        assert packaging.client == "claude-code" and packaging.origin == "agent"
