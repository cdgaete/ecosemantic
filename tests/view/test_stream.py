from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

from fastmcp import Client, FastMCP
from mcp.types import Implementation
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.ports.types import RequestDraft
from ecosemantic.view.app import build_view

PERSON = Actor(kind="person", name="Carlos")


async def _frames_until(app: ASGIApp, path: str, wanted: int, trigger) -> list[str]:
    """Run the app on one GET, fire the trigger once the stream is open, return `wanted` data
    frames split into their blocks."""
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
            if b"".join(frames).decode().count("data:") >= wanted:
                enough.set()

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), 5)
    await trigger()
    await asyncio.wait_for(enough.wait(), 5)
    disconnect.set()
    await asyncio.wait_for(task, 5)
    return re.split(r"\r?\n\r?\n", b"".join(frames).decode())


async def _stream_until(app: ASGIApp, path: str, wanted: int, trigger) -> list[dict]:
    """The events `_frames_until` read, one per data frame."""
    events = []
    for block in await _frames_until(app, path, wanted, trigger):
        data = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if data:
            events.append(json.loads(data[0]))
    return events


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
        blocks = await _frames_until(app, path, 1, trigger)
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
        events = await _stream_until(app, f"/api/product-systems/{system_id}/events", 1, trigger)
    assert events[0]["kind"] == "entry"
    assert events[0]["entry"]["message"] == "outside"
