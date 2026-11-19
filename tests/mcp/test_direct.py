from __future__ import annotations

import asyncio
import dataclasses
import uuid

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.direct import run_tool
from ecosemantic.mcp.envelopes import envelope_of
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import Call


async def _ids(context: ServerContext) -> set[uuid.UUID]:
    return {call.id for call in await context.activity.list_calls()}


async def _since(context: ServerContext, before: set[uuid.UUID]) -> list[Call]:
    return [call for call in await context.activity.list_calls() if call.id not in before]


async def test_a_tool_run_in_process_answers_what_the_mcp_path_answers(
    ports_only_server: FastMCP, ports_only: ServerContext, cup: tuple[str, str]
) -> None:
    system_id, method_id = cup
    asked = [
        ("get_product_system", {"product_system_id": system_id}),
        ("get_product_system_log", {"product_system_id": system_id}),
        ("validate_product_system", {"product_system_id": system_id}),
        ("calculate_impact", {"product_system_id": system_id, "method_id": method_id}),
    ]
    async with Client(ports_only_server) as client:
        for name, arguments in asked:
            over_mcp = (await client.call_tool(name, arguments)).structured_content
            assert await run_tool(ports_only_server, ports_only, name, arguments) == over_mcp


async def test_arguments_that_do_not_validate_answer_the_envelope_an_agent_reads(
    ports_only_server: FastMCP, ports_only: ServerContext, cup: tuple[str, str]
) -> None:
    system_id, _ = cup
    asked = [
        ("get_product_system", {"product_system_id": system_id, "bogus": 1}),
        ("get_product_system_log", {"product_system_id": system_id, "limit": "x"}),
    ]
    async with Client(ports_only_server) as client:
        for name, arguments in asked:
            with pytest.raises(ToolError) as over_mcp:
                await client.call_tool(name, arguments)
            with pytest.raises(ToolError) as direct:
                await run_tool(ports_only_server, ports_only, name, arguments)
            assert envelope_of(direct.value) == envelope_of(over_mcp.value)


async def test_a_typed_error_answers_its_envelope(
    ports_only_server: FastMCP, ports_only: ServerContext
) -> None:
    arguments = {"product_system_id": str(uuid.uuid4())}
    async with Client(ports_only_server) as client:
        with pytest.raises(ToolError) as over_mcp:
            await client.call_tool("get_product_system", arguments)
    with pytest.raises(ToolError) as direct:
        await run_tool(ports_only_server, ports_only, "get_product_system", arguments)
    assert envelope_of(direct.value) == envelope_of(over_mcp.value)
    assert envelope_of(direct.value).error == "not_found"


async def test_an_unknown_tool_answers_what_the_mcp_path_answers(
    ports_only_server: FastMCP, ports_only: ServerContext
) -> None:
    async with Client(ports_only_server) as client:
        with pytest.raises(ToolError) as over_mcp:
            await client.call_tool("no_such_tool", {})
    with pytest.raises(ToolError) as direct:
        await run_tool(ports_only_server, ports_only, "no_such_tool", {})
    assert envelope_of(direct.value) == envelope_of(over_mcp.value)


async def test_a_tool_failing_its_own_validation_answers_invalid(
    ports_only: ServerContext,
) -> None:
    probe = FastMCP("probe")

    @probe.tool(name="broken")
    def broken() -> str:
        Method.model_validate({})
        return "unreachable"

    with pytest.raises(ToolError) as direct:
        await run_tool(probe, ports_only, "broken", {})
    refused = envelope_of(direct.value)
    assert refused.error == "invalid" and refused.message.startswith("broken: ")


async def test_a_tool_answering_no_structured_content_raises(
    ports_only: ServerContext,
) -> None:
    probe = FastMCP("probe")

    @probe.tool(name="plain", output_schema=None)
    def plain() -> str:
        return "hello"

    with pytest.raises(RuntimeError, match="'plain' answered no structured content"):
        await run_tool(probe, ports_only, "plain", {})


async def test_a_persons_calculation_is_recorded_under_view_whatever_agent_the_server_names(
    ports_only: ServerContext, cup: tuple[str, str]
) -> None:
    system_id, method_id = cup
    configured = dataclasses.replace(ports_only, agent="configured")
    before = await _ids(ports_only)
    await run_tool(
        build_server(configured),
        configured,
        "calculate_impact",
        {"product_system_id": system_id, "method_id": method_id},
        started=True,
    )
    (call,) = await _since(ports_only, before)
    assert (call.tool, call.agent, call.origin) == ("calculate_impact", "view", "view")


async def test_two_calls_at_once_each_run_as_their_own(
    ports_only_server: FastMCP, ports_only: ServerContext, cup: tuple[str, str]
) -> None:
    system_id, method_id = cup
    before = await _ids(ports_only)
    await asyncio.gather(
        run_tool(
            ports_only_server,
            ports_only,
            "calculate_impact",
            {"product_system_id": system_id, "method_id": method_id},
            started=True,
        ),
        run_tool(
            ports_only_server,
            ports_only,
            "get_product_system",
            {"product_system_id": system_id},
        ),
    )
    (call,) = await _since(ports_only, before)
    assert call.tool == "calculate_impact"
