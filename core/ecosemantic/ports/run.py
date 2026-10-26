"""A calculation that outlives its request: the record, and who may change it."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from ecosemantic.ports.types import Run, RunDraft, RunPatch, StoreChange


@runtime_checkable
class RunPort(Protocol):
    async def post_run(self, draft: RunDraft) -> Run: ...

    async def get_run(self, run_id: uuid.UUID) -> Run: ...

    async def list_runs(self, product_system_id: uuid.UUID | None = None) -> list[Run]: ...

    async def cancel_run(self, run_id: uuid.UUID) -> Run: ...

    async def update_run(self, run_id: uuid.UUID, patch: RunPatch) -> Run: ...

    async def delete_runs(self, product_system_id: uuid.UUID) -> None: ...

    def slot(self) -> AbstractAsyncContextManager[object]: ...

    def changes(self) -> AsyncIterator[StoreChange]: ...


class RunLauncher(Protocol):
    """Starts the process that carries a run, and says whether that process still carries it."""

    def start(self, run_id: uuid.UUID) -> int: ...

    def alive(self, run_id: uuid.UUID) -> bool: ...
