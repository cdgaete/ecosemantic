"""What happens in a server process, told to whoever listens: one bus per process, fed by the
storage every write goes through, by the watcher of each run the process started and by what any
process writes to an install's record, and read by the stream the page follows."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.ports.install import InstallPort
from ecosemantic.ports.run import RunPort
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import (
    Call,
    Install,
    Layout,
    LogEntry,
    Outcome,
    ProductSystemSummary,
    Request,
    RequestDraft,
    Restored,
    Run,
    Source,
    StoreChange,
)


class Event(BaseModel):
    """One thing that happened: to a product system, an install, or a tool call that names
    neither."""

    kind: Literal["entry", "request", "resolution", "deleted", "layout", "run", "install", "call"]
    product_system_id: uuid.UUID | None = None
    entry: LogEntry | None = None
    request: Request | None = None
    run: Run | None = None
    install: Install | None = None
    call: Call | None = None


class EventBus:
    """Fan-out of events to the queues of their product system and to every process-wide
    queue."""

    def __init__(self) -> None:
        self._queues: dict[uuid.UUID, set[asyncio.Queue[Event]]] = {}
        self._everything: set[asyncio.Queue[Event]] = set()

    def subscribe(self, product_system_id: uuid.UUID) -> asyncio.Queue[Event]:
        """A queue that receives every event of one product system from now on."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._queues.setdefault(product_system_id, set()).add(queue)
        return queue

    def unsubscribe(self, product_system_id: uuid.UUID, queue: asyncio.Queue[Event]) -> None:
        """Stop delivering to a queue."""
        self._queues.get(product_system_id, set()).discard(queue)

    def subscribe_all(self) -> asyncio.Queue[Event]:
        """A queue that receives every event of the process from now on."""
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._everything.add(queue)
        return queue

    def unsubscribe_all(self, queue: asyncio.Queue[Event]) -> None:
        """Stop delivering to a process-wide queue."""
        self._everything.discard(queue)

    def followers(self) -> int:
        """How many process-wide queues the bus holds, a page's open stream among them."""
        return len(self._everything)

    def publish(self, event: Event) -> None:
        """Deliver an event to the queues of its product system and to every process-wide one."""
        named = self._queues.get(event.product_system_id, ()) if event.product_system_id else ()
        for queue in (*named, *self._everything):
            queue.put_nowait(event)


class NotifyingStorage:
    """The storage port over another, publishing an event after every write."""

    def __init__(self, inner: StoragePort, bus: EventBus) -> None:
        self.inner = inner
        self.bus = bus

    async def list_product_systems(self) -> list[ProductSystemSummary]:
        return await self.inner.list_product_systems()

    async def get_product_system(self, product_system_id: uuid.UUID) -> ProductSystem:
        return await self.inner.get_product_system(product_system_id)

    async def get_version(self, product_system_id: uuid.UUID, content_hash: str) -> ProductSystem:
        return await self.inner.get_version(product_system_id, content_hash)

    async def put_product_system(
        self, product_system: ProductSystem, actor: Actor, message: str, source: Source = "mcp"
    ) -> LogEntry:
        entry = await self.inner.put_product_system(product_system, actor, message, source)
        self.bus.publish(Event(kind="entry", product_system_id=product_system.id, entry=entry))
        return entry

    async def delete_product_system(self, product_system_id: uuid.UUID, actor: Actor) -> None:
        await self.inner.delete_product_system(product_system_id, actor)
        self.bus.publish(Event(kind="deleted", product_system_id=product_system_id))

    async def log(self, product_system_id: uuid.UUID) -> list[LogEntry]:
        return await self.inner.log(product_system_id)

    async def get_layout(self, product_system_id: uuid.UUID) -> Layout:
        return await self.inner.get_layout(product_system_id)

    async def put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout:
        stored = await self.inner.put_layout(product_system_id, layout)
        self.bus.publish(Event(kind="layout", product_system_id=product_system_id))
        return stored

    def changes(self) -> AsyncIterator[StoreChange]:
        return self.inner.changes()

    async def post_request(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request:
        request = await self.inner.post_request(product_system_id, draft)
        self.bus.publish(
            Event(kind="request", product_system_id=product_system_id, request=request)
        )
        return request

    async def list_requests(
        self, product_system_id: uuid.UUID, open_only: bool = False
    ) -> list[Request]:
        return await self.inner.list_requests(product_system_id, open_only)

    async def resolve_request(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request:
        request = await self.inner.resolve_request(product_system_id, request_id, outcome)
        self.bus.publish(
            Event(kind="resolution", product_system_id=product_system_id, request=request)
        )
        return request

    async def return_package(
        self,
        product_system_id: uuid.UUID,
        exported_root: Path,
        actor: Actor,
        at_entry: int | None = None,
    ) -> LogEntry:
        entry = await self.inner.return_package(product_system_id, exported_root, actor, at_entry)
        self.bus.publish(Event(kind="entry", product_system_id=product_system_id, entry=entry))
        return entry

    async def export_package(self, product_system_id: uuid.UUID, destination: Path) -> None:
        await self.inner.export_package(product_system_id, destination)

    async def restore_package(self, source: Path) -> Restored:
        held = {s.id for s in await self.inner.list_product_systems()}
        restored = await self.inner.restore_package(source)
        for summary in await self.inner.list_product_systems():
            if summary.id not in held:
                log = await self.inner.log(summary.id)
                self.bus.publish(Event(kind="entry", product_system_id=summary.id, entry=log[-1]))
        return restored


class _Cursor:
    """What a pump has already published, so a change publishes the difference."""

    def __init__(self) -> None:
        self.seq: dict[uuid.UUID, int] = {}
        self.requests: dict[uuid.UUID, set[uuid.UUID]] = {}
        self.resolved: dict[uuid.UUID, set[uuid.UUID]] = {}

    async def prime(self, storage: StoragePort) -> None:
        """Take the state of every stored product system as already published."""
        for summary in await storage.list_product_systems():
            await self.events_for(storage, StoreChange(product_system_id=summary.id))

    def forget(self, product_system_id: uuid.UUID) -> None:
        self.seq.pop(product_system_id, None)
        self.requests.pop(product_system_id, None)
        self.resolved.pop(product_system_id, None)

    async def events_for(self, storage: StoragePort, change: StoreChange) -> list[Event]:
        """The events one change is worth: the entries, requests and resolutions this cursor has
        not published yet, and nothing it has."""
        system = change.product_system_id
        if change.gone:
            self.forget(system)
            return [Event(kind="deleted", product_system_id=system)]
        events: list[Event] = []
        since = self.seq.get(system, 0)
        log = await storage.log(system)
        for entry in log:
            if entry.seq > since:
                events.append(Event(kind="entry", product_system_id=system, entry=entry))
        self.seq[system] = max([since, *(entry.seq for entry in log)])
        known = self.requests.setdefault(system, set())
        settled = self.resolved.setdefault(system, set())
        for request in await storage.list_requests(system):
            if request.id not in known:
                known.add(request.id)
                events.append(Event(kind="request", product_system_id=system, request=request))
            if request.outcome is not None and request.id not in settled:
                settled.add(request.id)
                events.append(Event(kind="resolution", product_system_id=system, request=request))
        if not events:
            events.append(Event(kind="layout", product_system_id=system))
        return events


async def pump_storage(
    storage: StoragePort, bus: EventBus, ready: asyncio.Event | None = None
) -> None:
    """Publish what any process wrote to the store, until cancelled.

    A process publishes its own writes as it makes them and sees them again here, so delivery is
    at-least-once; every consumer of an event is an idempotent refresh. `ready`, when given, is
    set once the stored state is taken as published, so a caller that waits for it knows a later
    write is one this pump will publish.
    """
    cursor = _Cursor()
    changes = storage.changes()
    await cursor.prime(storage)
    if ready is not None:
        ready.set()
    async for change in changes:
        for event in await cursor.events_for(storage, change):
            bus.publish(event)


async def pump_runs(runs: RunPort, bus: EventBus, ready: asyncio.Event | None = None) -> None:
    """Publish a run any process moved, until cancelled.

    `ready`, when given, is set once the watch is armed, so a caller that waits for it knows a
    later write is one this pump will publish.
    """
    changes = runs.changes()
    if ready is not None:
        ready.set()
    async for change in changes:
        if change.run_id is None:
            continue
        run = await runs.get_run(change.run_id)
        bus.publish(Event(kind="run", product_system_id=run.product_system_id, run=run))


async def pump_installs(
    installs: InstallPort, bus: EventBus, ready: asyncio.Event | None = None
) -> None:
    """Publish an install any process moved, until cancelled.

    `ready`, when given, is set once the watch is armed, so a caller that waits for it knows a
    later write is one this pump will publish.
    """
    changes = installs.changes()
    if ready is not None:
        ready.set()
    async for install_id in changes:
        bus.publish(Event(kind="install", install=await installs.get_install(install_id)))
