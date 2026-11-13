"""The run port over a directory: one folder per run under the systems directory."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from pathlib import Path

from filelock import AsyncFileLock
from pydantic import model_validator

from ecosemantic.backends.filesystem.records import RecordFolder
from ecosemantic.backends.filesystem.run_folder import RECORD_FILE, RUNS_DIR
from ecosemantic.ports import posted
from ecosemantic.ports.types import Run, RunDraft, RunPatch, StoreChange, refuse_open


class StoredRun(Run):
    """A run as its record holds it, where a result naming each method by its whole record reads
    as one naming it by id."""

    @model_validator(mode="before")
    @classmethod
    def _methods_named_by_id(cls, value: object) -> object:
        """The record with its result naming each method by id, and any other value as it is."""
        if not isinstance(value, Mapping):
            return value
        result = value.get("result")
        if not isinstance(result, Mapping):
            return value
        named = dict(result)
        gating = named.get("gating_method")
        if isinstance(gating, Mapping):
            named["gating_method"] = gating["id"]
        categories = named.get("categories")
        if isinstance(categories, list):
            named["categories"] = [_category_named_by_id(category) for category in categories]
        return {**value, "result": named}


def _category_named_by_id(category: object) -> object:
    """One category naming its method by the id of the record it holds, or as it is when it holds
    no record."""
    if not isinstance(category, Mapping):
        return category
    method = category.get("method")
    if not isinstance(method, Mapping):
        return category
    named = {key: value for key, value in category.items() if key != "method"}
    named["method_id"] = method["id"]
    return named


class FilesystemRuns:
    """Run records as one JSON file per run, newest first by the time they were posted.

    The worker writes a record from its own process while the server reads it, so a record is
    replaced whole, never rewritten in place, and every change is read and written under a lock
    both processes take.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.records = RecordFolder[Run](root, RUNS_DIR, RECORD_FILE, StoredRun, "run")

    def read_record(self, run_id: uuid.UUID) -> Run:
        """One run, read synchronously; the worker's callback runs off the event loop."""
        return self.records.read(run_id)

    def apply_patch(self, run_id: uuid.UUID, patch: RunPatch) -> Run:
        """The record with the patch's named fields applied, written synchronously."""
        return self.records.patch(run_id, patch.applied_to)

    async def post_run(self, draft: RunDraft) -> Run:
        def construct(posted_at: datetime) -> Run:
            return StoredRun(id=uuid.uuid4(), posted_at=posted_at, **draft.model_dump())

        return await asyncio.to_thread(self.records.post, construct)

    async def get_run(self, run_id: uuid.UUID) -> Run:
        return await asyncio.to_thread(self.read_record, run_id)

    async def list_runs(self, product_system_id: uuid.UUID | None = None) -> list[Run]:
        runs = posted.newest_first(await asyncio.to_thread(self.records.all))
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
                self.records.remove(run.id)

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

    def sweep(self) -> None:
        """Remove the lock file of every run this store does not hold."""
        self.records.sweep()

    def slot(self) -> AsyncFileLock:
        """The workspace's one-run slot: a file lock every process over this directory takes,
        released when its holder's process ends."""
        return self.records.slot()
