"""The storage port over dictionaries: a second implementation that proves the port's consumers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from ecosemantic.errors import Conflict, NotFound, NotSupported
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.log import next_entry
from ecosemantic.package.requests import next_request, resolve
from ecosemantic.ports.types import (
    Layout,
    LogEntry,
    Outcome,
    ProductSystemSummary,
    Request,
    RequestDraft,
    Restored,
    Source,
    StoreChange,
)


class MemoryStorage:
    """Product systems, their version snapshots and their logs, held in memory."""

    def __init__(self) -> None:
        self._current: dict[uuid.UUID, ProductSystem] = {}
        self._versions: dict[uuid.UUID, dict[str, ProductSystem]] = {}
        self._logs: dict[uuid.UUID, list[LogEntry]] = {}
        self._requests: dict[uuid.UUID, list[Request]] = {}
        self._layouts: dict[uuid.UUID, Layout] = {}
        self._watchers: set[asyncio.Queue[StoreChange]] = set()

    def _announce(self, product_system_id: uuid.UUID, gone: bool = False) -> None:
        change = StoreChange(product_system_id=product_system_id, gone=gone)
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

    def _held(self, product_system_id: uuid.UUID) -> ProductSystem:
        if product_system_id not in self._current:
            raise NotFound(f"no product_system {product_system_id} in memory")
        return self._current[product_system_id]

    async def list_product_systems(self) -> list[ProductSystemSummary]:
        return [
            ProductSystemSummary.of(s)
            for s in sorted(self._current.values(), key=lambda s: str(s.id))
        ]

    async def get_product_system(self, product_system_id: uuid.UUID) -> ProductSystem:
        return self._held(product_system_id).model_copy(deep=True)

    async def get_version(self, product_system_id: uuid.UUID, content_hash: str) -> ProductSystem:
        versions = self._versions.get(product_system_id, {})
        if content_hash not in versions:
            raise NotFound(f"no version {content_hash} of {product_system_id}")
        return versions[content_hash].model_copy(deep=True)

    async def put_product_system(
        self, product_system: ProductSystem, actor: Actor, message: str, source: Source = "mcp"
    ) -> LogEntry:
        before = self._current.get(product_system.id)
        if (before is None and product_system.hash is not None) or (
            before is not None and product_system.hash != before.hash
        ):
            raise Conflict(f"the write of {product_system.id} is based on {product_system.hash}")
        log = self._logs.get(product_system.id, [])
        entry = next_entry(log, actor, source, before, product_system, message)
        stored = product_system.model_copy(deep=True, update={"hash": entry.result_hash})
        self._current[product_system.id] = stored
        self._versions.setdefault(product_system.id, {})[entry.result_hash] = stored
        self._logs[product_system.id] = [*log, entry]
        self._announce(product_system.id)
        return entry

    async def delete_product_system(self, product_system_id: uuid.UUID, actor: Actor) -> None:
        self._held(product_system_id)
        del self._current[product_system_id]
        del self._versions[product_system_id]
        del self._logs[product_system_id]
        self._requests.pop(product_system_id, None)
        self._layouts.pop(product_system_id, None)
        self._announce(product_system_id, gone=True)

    async def log(self, product_system_id: uuid.UUID) -> list[LogEntry]:
        self._held(product_system_id)
        return list(self._logs[product_system_id])

    async def get_layout(self, product_system_id: uuid.UUID) -> Layout:
        self._held(product_system_id)
        return self._layouts.get(product_system_id, Layout()).model_copy(deep=True)

    async def put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout:
        self._held(product_system_id)
        self._layouts[product_system_id] = layout.model_copy(deep=True)
        self._announce(product_system_id)
        return layout

    async def post_request(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request:
        self._held(product_system_id)
        queue = self._requests.get(product_system_id, [])
        request = next_request(queue, draft)
        self._requests[product_system_id] = [*queue, request]
        self._announce(product_system_id)
        return request

    async def list_requests(
        self, product_system_id: uuid.UUID, open_only: bool = False
    ) -> list[Request]:
        self._held(product_system_id)
        queue = list(self._requests.get(product_system_id, []))
        return [r for r in queue if r.open] if open_only else queue

    async def resolve_request(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request:
        self._held(product_system_id)
        queue = resolve(self._requests.get(product_system_id, []), request_id, outcome)
        self._requests[product_system_id] = queue
        self._announce(product_system_id)
        return next(r for r in queue if r.id == request_id)

    async def return_package(
        self,
        product_system_id: uuid.UUID,
        exported_root: Path,
        actor: Actor,
        at_entry: int | None = None,
    ) -> LogEntry:
        self._held(product_system_id)
        raise NotSupported("a memory store retains no sidecar to read a returned package against")

    async def export_package(self, product_system_id: uuid.UUID, destination: Path) -> None:
        raise NotSupported("memory storage holds no package; it keeps documents, not directories")

    async def restore_package(self, source: Path) -> Restored:
        raise NotSupported("memory storage holds no package; it keeps documents, not directories")
