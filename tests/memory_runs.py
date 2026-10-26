"""The run port over a dictionary: a second implementation that proves the port's consumers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.ports.types import Run, RunDraft, RunPatch, StoreChange, refuse_open


class MemoryRuns:
    """Run records held in memory, newest first."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, Run] = {}
        self._slot = asyncio.Lock()
        self._watchers: set[asyncio.Queue[StoreChange]] = set()

    def _announce(self, run: Run) -> None:
        change = StoreChange(product_system_id=run.product_system_id, run_id=run.id)
        for queue in self._watchers:
            queue.put_nowait(change)

    def changes(self) -> AsyncIterator[StoreChange]:
        queue: asyncio.Queue[StoreChange] = asyncio.Queue()
        self._watchers.add(queue)

        async def iterate() -> AsyncIterator[StoreChange]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._watchers.discard(queue)

        return iterate()

    def read_record(self, run_id: uuid.UUID) -> Run:
        """One run, read synchronously, as the filesystem store reads one."""
        if run_id not in self._runs:
            raise NotFound(f"no run {run_id}")
        return self._runs[run_id]

    def apply_patch(self, run_id: uuid.UUID, patch: RunPatch) -> Run:
        """The record with the patch's named fields applied."""
        self._runs[run_id] = patch.applied_to(self.read_record(run_id))
        return self._runs[run_id]

    async def post_run(self, draft: RunDraft) -> Run:
        run = Run(id=uuid.uuid4(), posted_at=datetime.now(UTC), **draft.model_dump())
        self._runs[run.id] = run
        self._announce(run)
        return run

    async def get_run(self, run_id: uuid.UUID) -> Run:
        return self.read_record(run_id)

    async def list_runs(self, product_system_id: uuid.UUID | None = None) -> list[Run]:
        runs = sorted(self._runs.values(), key=lambda r: (r.posted_at, str(r.id)), reverse=True)
        if product_system_id is None:
            return runs
        return [run for run in runs if run.product_system_id == product_system_id]

    async def delete_runs(self, product_system_id: uuid.UUID) -> None:
        owned = [r for r in self._runs.values() if r.product_system_id == product_system_id]
        refuse_open(owned)
        for run in owned:
            del self._runs[run.id]

    async def cancel_run(self, run_id: uuid.UUID) -> Run:
        asked = self.apply_patch(run_id, self.read_record(run_id).cancellation())
        self._announce(asked)
        return asked

    async def update_run(self, run_id: uuid.UUID, patch: RunPatch) -> Run:
        run = self.apply_patch(run_id, patch)
        self._announce(run)
        return run

    def slot(self) -> asyncio.Lock:
        """The one-run slot, which only this process shares."""
        return self._slot


class MemoryLauncher:
    """A launcher with no worker: it refuses to start a run, and no run it is asked about has a
    live worker."""

    def start(self, run_id: uuid.UUID) -> int:
        raise Unavailable(f"run {run_id} has no worker in memory")

    def alive(self, run_id: uuid.UUID) -> bool:
        return False
