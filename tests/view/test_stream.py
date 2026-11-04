from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path

from fastmcp import Client, FastMCP
from mcp.types import Implementation
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.events import Event
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.ports.types import RequestDraft
from ecosemantic.view.app import build_view

PERSON = Actor(kind="person", name="Carlos")


def _counted(wanted: int) -> Callable[[str], bool]:
    """Done once the stream holds `wanted` data frames."""
    return lambda text: text.count("data:") >= wanted


def _holding(kind: str) -> Callable[[str], bool]:
    """Done once the stream holds an event of this kind."""
    return lambda text: any(event["kind"] == kind for event in _events(_blocks(text)))


def _blocks(text: str) -> list[str]:
    return re.split(r"\r?\n\r?\n", text)


def _events(blocks: list[str]) -> list[dict]:
    """The event each block's data frame carries."""
    events = []
    for block in blocks:
        data = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if data:
            events.append(json.loads(data[0]))
    return events


async def _frames_until(app: ASGIApp, path: str, done: Callable[[str], bool], trigger) -> list[str]:
    """Run the app on one GET, fire the trigger once the stream is open, return the frames read
    until `done` holds of them, split into their blocks."""
    frames: list[bytes] = []
    enough = asyncio.Event()
    started = asyncio.Event()
    disconnect = asyncio.Event()
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"view")],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }

    async def receive() -> dict:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            assert message["status"] == 200
            started.set()
        if message["type"] == "http.response.body":
            frames.append(message.get("body", b""))
            if done(b"".join(frames).decode()):
                enough.set()

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), 5)
    await trigger()
    await asyncio.wait_for(enough.wait(), 5)
    disconnect.set()
    await asyncio.wait_for(task, 5)
    return _blocks(b"".join(frames).decode())


async def _stream_until(app: ASGIApp, path: str, wanted: int, trigger) -> list[dict]:
    """The first `wanted` events the stream sends after the trigger, and any that came with
    them."""
    return _events(await _frames_until(app, path, _counted(wanted), trigger))


async def _stream_until_kind(app: ASGIApp, path: str, kind: str, trigger) -> list[dict]:
    """The events the stream sends after the trigger, up to the first of this kind."""
    events = _events(await _frames_until(app, path, _holding(kind), trigger))
    return events[: next(i for i, event in enumerate(events) if event["kind"] == kind) + 1]


async def test_a_write_and_a_request_reach_the_stream(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    app = build_view(context, full_server, static=Path("/nonexistent-static"))
    system_id = fixture_system_stored.id

    async def trigger() -> None:
        current = await context.storage.get_product_system(system_id)
        await context.storage.post_request(
            system_id,
            RequestDraft(actor=PERSON, kind="approve", at_hash=current.hash or "", message="ok"),
        )
        current.description = "described"
        await context.storage.put_product_system(current, context.actor, "described")

    events = await _stream_until(app, f"/api/product-systems/{system_id}/events", 2, trigger)
    assert [e["kind"] for e in events[:2]] == ["request", "entry"]
    assert events[1]["entry"]["message"] == "described"


def test_an_unknown_system_has_no_stream(context: ServerContext, full_server: FastMCP) -> None:
    with TestClient(build_view(context, full_server, static=Path("/nonexistent-static"))) as c:
        response = c.get(f"/api/product-systems/{uuid.uuid4()}/events")
        assert response.status_code == 404 and response.json()["error"] == "not_found"


async def test_each_stream_tells_the_page_to_retry_every_second(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    app = build_view(context, full_server, static=Path("/nonexistent-static"))
    system_id = fixture_system_stored.id

    async def trigger() -> None:
        current = await context.storage.get_product_system(system_id)
        current.description = "retried"
        await context.storage.put_product_system(current, context.actor, "retried")

    for path in (f"/api/product-systems/{system_id}/events", "/api/events"):
        blocks = await _frames_until(app, path, _counted(1), trigger)
        assert blocks[0].startswith("retry: 1000")


async def test_the_process_wide_stream_carries_a_call_that_names_no_system(
    context: ServerContext, full_server: FastMCP
) -> None:
    app = build_view(context, full_server, static=Path("/nonexistent-static"))

    async def trigger() -> None:
        agent = Client(full_server, client_info=Implementation(name="streamed-one", version="1"))
        async with agent as session:
            await session.call_tool("list_databases", {})

    events = await _stream_until(app, "/api/events", 1, trigger)
    assert events[0]["call"]["tool"] == "list_databases"
    assert events[0]["call"]["agent"] == "streamed-one"
    assert events[0]["product_system_id"] is None


async def test_a_write_by_another_storage_over_one_directory_reaches_the_stream(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    app = build_view(context, full_server, static=Path("/nonexistent-static"))
    outsider = FilesystemStorage(context.systems_dir, context.resolver)
    system_id = fixture_system_stored.id

    async def trigger() -> None:
        current = await outsider.get_product_system(system_id)
        current.description = "written by another process"
        await outsider.put_product_system(current, Actor(kind="agent", id="other"), "outside")

    async with app.router.lifespan_context(app):
        path = f"/api/product-systems/{system_id}/events"
        events = await _stream_until_kind(app, path, "entry", trigger)
    # a file noticed before the log is written publishes a layout first, as on Windows
    assert {event["kind"] for event in events[:-1]} <= {"layout"}
    assert events[-1]["entry"]["message"] == "outside"


async def test_a_layout_published_before_another_storages_write_does_not_hide_its_entry(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    app = build_view(context, full_server, static=Path("/nonexistent-static"))
    outsider = FilesystemStorage(context.systems_dir, context.resolver)
    system_id = fixture_system_stored.id

    async def trigger() -> None:
        context.events.publish(Event(kind="layout", product_system_id=system_id))
        current = await outsider.get_product_system(system_id)
        current.description = "written by another process"
        await outsider.put_product_system(current, Actor(kind="agent", id="other"), "outside")

    async with app.router.lifespan_context(app):
        path = f"/api/product-systems/{system_id}/events"
        events = await _stream_until_kind(app, path, "entry", trigger)
    assert events[0]["kind"] == "layout"
    assert {event["kind"] for event in events[:-1]} == {"layout"}
    assert events[-1]["entry"]["message"] == "outside"
