"""The run port over a directory: one folder per run under the systems directory."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from filelock import AsyncFileLock

from ecosemantic.backends.filesystem.records import RecordFolder, newest_first
from ecosemantic.backends.filesystem.run_folder import RECORD_FILE, RUNS_DIR
from ecosemantic.ports.types import Run, RunDraft, RunPatch, StoreChange, refuse_open


class FilesystemRuns:
    """Run records as one JSON file per run, newest first by the time they were posted.

    The worker writes a record from its own process while the server reads it, so a record is
    replaced whole, never rewritten in place, and every change is read and written under a lock
    both processes take.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.records = RecordFolder(root, RUNS_DIR, RECORD_FILE, Run, "run")

    def read_record(self, run_id: uuid.UUID) -> Run:
        """One run, read synchronously; the worker's callback runs off the event loop."""
        return self.records.read(run_id)

    def apply_patch(self, run_id: uuid.UUID, patch: RunPatch) -> Run:
        """The record with the patch's named fields applied, written synchronously."""
        with self.records.lock(run_id):
            return self.records.write(run_id, patch.applied_to(self.read_record(run_id)))

    async def post_run(self, draft: RunDraft) -> Run:
        run = Run(id=uuid.uuid4(), posted_at=datetime.now(UTC), **draft.model_dump())
        return await asyncio.to_thread(self.records.write, run.id, run)

    async def get_run(self, run_id: uuid.UUID) -> Run:
        return await asyncio.to_thread(self.read_record, run_id)

    async def list_runs(self, product_system_id: uuid.UUID | None = None) -> list[Run]:
        runs = newest_first(await asyncio.to_thread(self.records.all))
        if product_system_id is None:
            return runs
        return [run for run in runs if run.product_system_id == product_system_id]

    async def cancel_run(self, run_id: uuid.UUID) -> Run:
        def ask() -> Run:
            return self.records.patch(run_id, lambda run: run.cancellation().applied_to(run))

        return await asyncio.to_thread(ask)

    async def update_run(self, run_id: uuid.UUID, patch: RunPatch) -> Run:
        return await asyncio.to_thread(self.apply_patch, run_id, patch)

    async def delete_runs(self, product_system_id: uuid.UUID) -> None:
        """Remove every run of a product system, record and folder; Conflict while one is
        open, since its worker still writes it."""

        def remove() -> None:
            owned = [r for r in self.records.all() if r.product_system_id == product_system_id]
            refuse_open(owned)
            for run in owned:
                with self.records.lock(run.id):
                    shutil.rmtree(self.records.folder(run.id))

        await asyncio.to_thread(remove)

    def changes(self) -> AsyncIterator[StoreChange]:
        """What any process wrote under the runs directory, from the moment this is called: the
        watch is armed eagerly, so a write between this call and the first read is announced."""
        found = self.records.changed()

        async def iterate() -> AsyncIterator[StoreChange]:
            try:
                async for run_id in found:
                    run = await asyncio.to_thread(self.read_record, run_id)
                    yield StoreChange(product_system_id=run.product_system_id, run_id=run.id)
            finally:
                await found.aclose()

        return iterate()

    def slot(self) -> AsyncFileLock:
        """The workspace's one-run slot: a file lock every process over this directory takes,
        released when its holder's process ends."""
        return self.records.slot()
