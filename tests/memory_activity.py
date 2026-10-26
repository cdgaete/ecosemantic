"""The activity port over a list: a second implementation that proves the port's consumers."""

from __future__ import annotations

import uuid
from datetime import datetime

from ecosemantic.errors import NotFound
from ecosemantic.ports.types import AgentSummary, Call, CallDraft, agents_of, selected


class MemoryActivity:
    """Recorded calls held in memory."""

    def __init__(self) -> None:
        self._calls: list[Call] = []

    async def record(self, draft: CallDraft) -> Call:
        call = Call(id=uuid.uuid4(), **draft.model_dump())
        self._calls.append(call)
        return call

    async def list_calls(
        self,
        agent: str | None = None,
        product_system_id: uuid.UUID | None = None,
        after: datetime | None = None,
    ) -> list[Call]:
        return selected(self._calls, agent, product_system_id, after)

    async def get_call(self, call_id: uuid.UUID) -> Call:
        for call in self._calls:
            if call.id == call_id:
                return call
        raise NotFound(f"no call {call_id}")

    async def list_agents(self) -> list[AgentSummary]:
        return agents_of(self._calls)
