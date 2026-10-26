from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.events import (
    Event,
    EventBus,
    NotifyingStorage,
    pump_installs,
    pump_storage,
)
from ecosemantic.local import build_context
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import (
    Call,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    Layout,
    Outcome,
    RequestDraft,
    Spot,
)
from tests.conformance.activity import draft
from tests.memory_installs import MemoryInstalls
from tests.memory_storage import MemoryStorage

AGENT = Actor(kind="agent", id="mcp")
PERSON = Actor(kind="person", name="Carlos")


def test_followers_counts_the_process_wide_queues() -> None:
    bus = EventBus()
    assert bus.followers() == 0
    bus.subscribe(uuid.uuid4())
    assert bus.followers() == 0
    one = bus.subscribe_all()
    other = bus.subscribe_all()
    assert bus.followers() == 2
    bus.unsubscribe_all(one)
    assert bus.followers() == 1
    bus.unsubscribe_all(other)
    assert bus.followers() == 0


def test_publish_reaches_only_the_subscribers_of_that_system() -> None:
    bus = EventBus()
    a, b = uuid.uuid4(), uuid.uuid4()
    queue = bus.subscribe(a)
    bus.publish(Event(kind="deleted", product_system_id=b))
    assert queue.empty()
    bus.publish(Event(kind="deleted", product_system_id=a))
    assert queue.get_nowait().kind == "deleted"
    bus.unsubscribe(a, queue)
    bus.publish(Event(kind="deleted", product_system_id=a))
    assert queue.empty()


def test_the_wrapper_satisfies_the_port() -> None:
    assert isinstance(NotifyingStorage(MemoryStorage(), EventBus()), StoragePort)


async def test_every_write_publishes(product_system: ProductSystem) -> None:
    bus = EventBus()
    storage = NotifyingStorage(MemoryStorage(), bus)
    queue = bus.subscribe(product_system.id)
    entry = await storage.put_product_system(product_system, AGENT, "created")
    written = queue.get_nowait()
    assert written.kind == "entry" and written.entry == entry
    request = await storage.post_request(
        product_system.id,
        RequestDraft(actor=PERSON, kind="return", at_hash=entry.result_hash, message="x"),
    )
    assert queue.get_nowait() == Event(
        kind="request", product_system_id=product_system.id, request=request
    )
    outcome = Outcome(timestamp=datetime.now(UTC), actor=AGENT, resolution="accepted", message="y")
    resolved = await storage.resolve_request(product_system.id, request.id, outcome)
    assert queue.get_nowait() == Event(
        kind="resolution", product_system_id=product_system.id, request=resolved
    )
    await storage.delete_product_system(product_system.id, AGENT)
    assert queue.get_nowait().kind == "deleted"
    assert queue.empty()


async def test_reads_publish_nothing(product_system: ProductSystem) -> None:
    bus = EventBus()
    storage = NotifyingStorage(MemoryStorage(), bus)
    await storage.put_product_system(product_system, AGENT, "created")
    queue = bus.subscribe(product_system.id)
    await storage.get_product_system(product_system.id)
    await storage.list_product_systems()
    await storage.log(product_system.id)
    await storage.list_requests(product_system.id)
    assert queue.empty()


async def test_placing_a_card_publishes_one_layout_event_and_a_read_publishes_nothing(
    product_system: ProductSystem,
) -> None:
    store = MemoryStorage()
    bus = EventBus()
    storage = NotifyingStorage(store, bus)
    await storage.put_product_system(product_system, AGENT, "created")
    queue = bus.subscribe(product_system.id)
    code = product_system.processes[0].code
    arrangement = Layout(held={code: Spot(x=10.0, y=20.0)})
    await storage.put_layout(product_system.id, arrangement)
    assert await store.get_layout(product_system.id) == arrangement
    assert queue.get_nowait() == Event(kind="layout", product_system_id=product_system.id)
    assert queue.empty()
    assert await storage.get_layout(product_system.id) == arrangement
    assert queue.empty()


def test_build_context_binds_a_notifying_storage(bundle_dir: Path, tmp_path: Path) -> None:
    systems = tmp_path / "systems"
    systems.mkdir()
    context = build_context(bundle_dir, systems)
    try:
        assert isinstance(context.storage, NotifyingStorage)
        assert isinstance(context.events, EventBus)
    finally:
        context.close()


def test_a_process_wide_queue_hears_every_event_and_a_system_queue_only_its_own() -> None:
    bus = EventBus()
    system = uuid.uuid4()
    everything = bus.subscribe_all()
    own = bus.subscribe(system)
    about = Call(
        id=uuid.uuid4(),
        **draft("electricity", "create_process", 1, product_system_id=system).model_dump(),
    )
    about_none = Call(id=uuid.uuid4(), **draft("electricity", "search_processes", 2).model_dump())
    bus.publish(Event(kind="call", product_system_id=system, call=about))
    bus.publish(Event(kind="call", call=about_none))
    assert [everything.get_nowait().call, everything.get_nowait().call] == [about, about_none]
    assert own.get_nowait().call == about and own.empty()
    bus.unsubscribe_all(everything)
    bus.publish(Event(kind="call", call=about_none))
    assert everything.empty()


async def test_the_pump_publishes_an_entry_written_through_another_bus(
    product_system: ProductSystem,
) -> None:
    store = MemoryStorage()
    writing = NotifyingStorage(store, EventBus())
    watching = EventBus()
    queue = watching.subscribe(product_system.id)
    pump = asyncio.create_task(pump_storage(store, watching))
    await asyncio.sleep(0)
    entry = await writing.put_product_system(product_system, AGENT, "created")
    published = await asyncio.wait_for(queue.get(), 5)
    pump.cancel()
    assert published.kind == "entry"
    assert published.entry is not None and published.entry.seq == entry.seq


async def test_the_pump_publishes_only_what_is_new(product_system: ProductSystem) -> None:
    store = MemoryStorage()
    writing = NotifyingStorage(store, EventBus())
    await writing.put_product_system(product_system, AGENT, "created")
    watching = EventBus()
    queue = watching.subscribe(product_system.id)
    pump = asyncio.create_task(pump_storage(store, watching))
    await asyncio.sleep(0.1)
    current = await store.get_product_system(product_system.id)
    current.parameters[1].value = 0.12
    second = await writing.put_product_system(current, AGENT, "waste rate")
    published = await asyncio.wait_for(queue.get(), 5)
    pump.cancel()
    # the entry the pump was primed past is not republished
    assert published.entry is not None and published.entry.seq == second.seq
    assert queue.empty()


async def test_the_pump_publishes_a_deletion(product_system: ProductSystem) -> None:
    store = MemoryStorage()
    writing = NotifyingStorage(store, EventBus())
    await writing.put_product_system(product_system, AGENT, "created")
    watching = EventBus()
    queue = watching.subscribe(product_system.id)
    pump = asyncio.create_task(pump_storage(store, watching))
    await asyncio.sleep(0.1)
    await writing.delete_product_system(product_system.id, AGENT)
    published = await asyncio.wait_for(queue.get(), 5)
    pump.cancel()
    assert published.kind == "deleted"


async def test_the_pump_publishes_a_request_then_its_resolution(
    product_system: ProductSystem,
) -> None:
    store = MemoryStorage()
    writing = NotifyingStorage(store, EventBus())
    entry = await writing.put_product_system(product_system, AGENT, "created")
    watching = EventBus()
    queue = watching.subscribe(product_system.id)
    pump = asyncio.create_task(pump_storage(store, watching))
    await asyncio.sleep(0.1)
    request = await writing.post_request(
        product_system.id,
        RequestDraft(actor=PERSON, kind="return", at_hash=entry.result_hash, message="x"),
    )
    posted = await asyncio.wait_for(queue.get(), 5)
    outcome = Outcome(timestamp=datetime.now(UTC), actor=AGENT, resolution="accepted", message="y")
    await writing.resolve_request(product_system.id, request.id, outcome)
    resolved = await asyncio.wait_for(queue.get(), 5)
    pump.cancel()
    assert posted.kind == "request" and posted.request is not None
    assert posted.request.id == request.id
    assert resolved.kind == "resolution" and resolved.request is not None
    assert resolved.request.id == request.id


async def test_pump_installs_publishes_an_install_another_process_moved() -> None:
    installs = MemoryInstalls()
    watching = EventBus()
    queue = watching.subscribe_all()
    ready = asyncio.Event()
    pump = asyncio.create_task(pump_installs(installs, watching, ready))
    await asyncio.wait_for(ready.wait(), 5)
    posted = await installs.post_install(InstallDraft(source="uslci", actor=AGENT, version="2024"))
    await installs.update_install(
        posted.id, InstallPatch(status="running", progress=InstallProgress(step="fetch", count=2))
    )
    published = await asyncio.wait_for(queue.get(), 5)
    pump.cancel()
    assert published.kind == "install"
    assert published.install is not None
    assert published.install.id == posted.id and published.install.status == "running"
