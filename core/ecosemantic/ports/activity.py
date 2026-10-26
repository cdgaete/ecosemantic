"""What agents did: every tool call, kept in the order it happened."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from ecosemantic.ports.types import AgentSummary, Call, CallDraft


@runtime_checkable
class ActivityPort(Protocol):
    async def record(self, draft: CallDraft) -> Call: ...

    async def list_calls(
        self,
        agent: str | None = None,
        product_system_id: uuid.UUID | None = None,
        after: datetime | None = None,
    ) -> list[Call]: ...

    async def get_call(self, call_id: uuid.UUID) -> Call: ...

    async def list_agents(self) -> list[AgentSummary]: ...
