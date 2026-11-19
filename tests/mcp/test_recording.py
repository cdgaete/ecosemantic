from __future__ import annotations

import asyncio
import dataclasses
import uuid
from pathlib import Path

import pytest
import uvicorn
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.base import ToolResult
from mcp.types import Implementation

from ecosemantic.errors import Invalid
from ecosemantic.mcp.calls import InProgress, current
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import envelope_of
from ecosemantic.mcp.recording import VIEW, agent_named, recorded
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Actor, ProductSystem, method_id
from ecosemantic.ports.types import Call, CallDraft, trail
from ecosemantic.serve import ViewSettings, listener_for
from tests.fixture_data import FIXTURE_DB, GWP

GWP_ID = method_id(" > ".join(GWP))


def named(server: FastMCP, name: str) -> Client:
    return Client(server, client_info=Implementation(name=name, version="1"))


def test_the_name_is_the_urls_then_the_servers_then_the_clients() -> None:
    assert agent_named("electricity", "configured", "claude-code") == "electricity"
    assert agent_named(None, "configured", "claude-code") == "configured"
    assert agent_named(None, None, "Claude Desktop") == "claude-desktop"


def test_a_name_that_is_not_one_and_the_pages_name_are_refused() -> None:
    for on_url, client in (("has space", "claude-code"), (None, "!!!"), ("view", "claude-code")):
        with pytest.raises(Invalid):
            agent_named(on_url, None, client)
    assert agent_named(None, None, "view") == "view"


async def test_a_read_is_recorded_with_what_it_held(
    context: ServerContext, full_server: FastMCP
) -> None:
    async with named(full_server, "reader-one") as client:
        answered = await client.call_tool(
            "search_processes", {"database": FIXTURE_DB, "query": "a"}
        )
    (call,) = await context.activity.list_calls(agent="reader-one")
    assert (call.tool, call.effect, call.origin, call.outcome) == (
        "search_processes",
        "read",
        "agent",
        "ok",
    )
    assert call.client == "reader-one"
    assert call.arguments == {"database": FIXTURE_DB, "query": "a"}
    assert call.summary is not None
    assert call.summary.count == len(answered.structured_content["items"])
    assert call.product_system_id is None and call.entry_seq is None


async def test_a_write_names_its_agent_its_entry_its_system_and_its_hash(
    context: ServerContext, full_server: FastMCP
) -> None:
    async with named(full_server, "writer-one") as client:
        made = await client.call_tool(
            "create_product_system", {"name": "recorded", "database": FIXTURE_DB}
        )
    system_id = uuid.UUID(made.structured_content["value"]["id"])
    (call,) = await context.activity.list_calls(agent="writer-one")
    entry = (await context.storage.log(system_id))[-1]
    assert (call.effect, call.product_system_id, call.entry_seq) == ("write", system_id, entry.seq)
    assert call.at_hash == entry.result_hash
    assert entry.actor == Actor(kind="agent", id="writer-one", name="writer-one")


async def test_a_failed_call_is_recorded_with_its_envelope(
    context: ServerContext, full_server: FastMCP
) -> None:
    async with named(full_server, "failing-one") as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_product_system", {"product_system_id": str(uuid.uuid4())})
        with pytest.raises(ToolError):
            await client.call_tool("search_processes", {"database": FIXTURE_DB})
    missing, invalid = await context.activity.list_calls(agent="failing-one")
    assert missing.outcome == "error" and missing.error is not None
    assert missing.error.error == "not_found"
    assert invalid.outcome == "error" and invalid.error is not None
    assert invalid.error.error == "invalid"


async def test_a_read_about_a_system_carries_the_hash_it_read(
    context: ServerContext, full_server: FastMCP, bottle: str
) -> None:
    async with named(full_server, "reader-two") as client:
        await client.call_tool("get_product_system", {"product_system_id": bottle})
    (call,) = await context.activity.list_calls(agent="reader-two")
    log = await context.storage.log(uuid.UUID(bottle))
    assert call.product_system_id == uuid.UUID(bottle) and call.at_hash == log[-1].result_hash


async def test_a_call_about_a_system_nobody_stored_is_recorded_without_a_hash(
    context: ServerContext,
) -> None:
    served = build_server(dataclasses.replace(context, view_url="http://127.0.0.1:1"))
    unstored = uuid.uuid4()
    async with named(served, "linker-one") as client:
        with pytest.raises(ToolError, match="not_found"):
            await client.call_tool("view_link", {"product_system_id": str(unstored)})
    (call,) = await context.activity.list_calls(agent="linker-one")
    assert (call.outcome, call.product_system_id, call.at_hash) == ("error", unstored, None)


async def test_two_agents_keep_their_trails_apart(
    context: ServerContext, full_server: FastMCP, bottle: str
) -> None:
    async with named(full_server, "trail-a") as a, named(full_server, "trail-b") as b:
        await a.call_tool("search_processes", {"database": FIXTURE_DB, "query": "a"})
        await b.call_tool("search_processes", {"database": FIXTURE_DB, "query": "b"})
        await a.call_tool(
            "update_product_system", {"product_system_id": bottle, "description": "by a"}
        )
    entry = (await context.storage.log(uuid.UUID(bottle)))[-1]
    found = trail(await context.activity.list_calls(), uuid.UUID(bottle), entry.seq)
    assert [(c.agent, c.tool) for c in found] == [
        ("trail-a", "search_processes"),
        ("trail-a", "update_product_system"),
    ]


async def test_a_call_is_published_on_the_bus(context: ServerContext, full_server: FastMCP) -> None:
    everything = context.events.subscribe_all()
    try:
        async with named(full_server, "published-one") as client:
            await client.call_tool("list_databases", {})
        calls = []
        while not everything.empty():
            event = everything.get_nowait()
            if event.kind == "call" and event.call.agent == "published-one":
                calls.append(event.call.tool)
        assert calls == ["list_databases"]
    finally:
        context.events.unsubscribe_all(everything)


async def _ids(context: ServerContext) -> set[uuid.UUID]:
    return {call.id for call in await context.activity.list_calls()}


async def _since(context: ServerContext, before: set[uuid.UUID]) -> list[Call]:
    return [call for call in await context.activity.list_calls() if call.id not in before]


class _DiskFull:
    """An activity whose record cannot write."""

    async def record(self, draft: CallDraft) -> Call:
        raise OSError("disk full")


async def test_a_calculation_a_person_started_is_recorded_under_view(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    tool = await full_server.get_tool("calculate_impact")
    assert tool is not None
    arguments = {"product_system_id": str(fixture_system_stored.id), "method_id": GWP_ID}
    before = await _ids(context)
    await recorded(
        context,
        tool,
        arguments,
        InProgress(agent=VIEW, client=VIEW),
        True,
        lambda: tool.run(arguments),
    )
    (call,) = await _since(context, before)
    assert (call.agent, call.origin, call.outcome, call.tool) == (
        "view",
        "view",
        "ok",
        "calculate_impact",
    )


async def test_a_page_read_is_recorded_nowhere(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    tool = await full_server.get_tool("get_product_system")
    assert tool is not None
    arguments = {"product_system_id": str(fixture_system_stored.id)}
    before = await _ids(context)
    await recorded(
        context,
        tool,
        arguments,
        InProgress(agent=VIEW, client=VIEW),
        False,
        lambda: tool.run(arguments),
    )
    assert await _since(context, before) == []


async def test_a_calculation_the_tool_refuses_is_recorded_with_its_envelope(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    tool = await full_server.get_tool("calculate_impact")
    assert tool is not None
    arguments = {"product_system_id": str(fixture_system_stored.id), "method_id": "no such method"}
    before = await _ids(context)
    with pytest.raises(ToolError) as refused:
        await recorded(
            context,
            tool,
            arguments,
            InProgress(agent=VIEW, client=VIEW),
            True,
            lambda: tool.run(arguments),
        )
    (call,) = await _since(context, before)
    assert call.outcome == "error" and call.error == envelope_of(refused.value)


async def test_a_record_that_fails_raises_although_the_tool_ran(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    tool = await full_server.get_tool("calculate_impact")
    assert tool is not None
    arguments = {"product_system_id": str(fixture_system_stored.id), "method_id": GWP_ID}
    unrecorded = dataclasses.replace(context, activity=_DiskFull())
    with pytest.raises(OSError, match="disk full"):
        await recorded(
            unrecorded,
            tool,
            arguments,
            InProgress(agent=VIEW, client=VIEW),
            True,
            lambda: tool.run(arguments),
        )


async def test_the_call_runs_as_the_call_in_progress(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    tool = await full_server.get_tool("get_product_system")
    assert tool is not None
    arguments = {"product_system_id": str(fixture_system_stored.id)}
    seen: list[Actor] = []

    async def run() -> ToolResult:
        seen.append(context.acting())
        return await tool.run(arguments)

    await recorded(context, tool, arguments, InProgress(agent=VIEW, client=VIEW), False, run)
    assert seen == [Actor(kind="agent", id="view", name="view")]
    assert current() is None


async def test_a_tool_with_no_annotations_runs_unrecorded_from_the_page(
    context: ServerContext,
) -> None:
    probe = FastMCP("probe")

    @probe.tool(name="answers")
    def answers() -> str:
        return "answered"

    tool = await probe.get_tool("answers")
    assert tool is not None
    before = await _ids(context)
    result = await recorded(
        context,
        tool,
        {},
        InProgress(agent=VIEW, client=VIEW),
        False,
        lambda: tool.run({}),
    )
    assert result.content[0].text == "answered"
    assert await _since(context, before) == []


async def _wait_until_started(web: uvicorn.Server) -> None:
    while not web.started:
        await asyncio.sleep(0.05)


async def test_over_http_the_name_on_the_url_names_the_agent(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the announced host is read from os.environ, as tests/view/test_serve.py:38 states
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    listener = listener_for(context, ViewSettings(transport="http"), systems_dir)
    web = uvicorn.Server(
        uvicorn.Config(listener.app, log_config=None, access_log=False, lifespan="on")
    )
    serving = asyncio.create_task(web.serve(sockets=[listener.socket]))
    try:
        await asyncio.wait_for(_wait_until_started(web), 10)
        async with (
            Client(f"{listener.url}/mcp?agent=http-electricity") as one,
            Client(f"{listener.url}/mcp?agent=http-packaging") as two,
        ):
            await one.call_tool("list_databases", {})
            await two.call_tool("list_databases", {})
            await one.call_tool("list_databases", {})
        with pytest.raises(ToolError, match="not an agent name"):
            async with Client(f"{listener.url}/mcp?agent=has%20space") as bad:
                await bad.call_tool("list_databases", {})
    finally:
        web.should_exit = True
        await serving
    assert len(await context.activity.list_calls(agent="http-electricity")) == 2
    assert len(await context.activity.list_calls(agent="http-packaging")) == 1
