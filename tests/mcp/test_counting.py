from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams, Implementation
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.counting import TOOL_CALLS, Counting
from ecosemantic.mcp.server import build_server


def counted(reader: InMemoryMetricReader) -> list[tuple[dict[str, str], int]]:
    data = reader.get_metrics_data()
    if data is None:
        return []
    return [
        (dict(point.attributes), point.value)
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == TOOL_CALLS
        for point in metric.data.data_points
    ]


def served(context: ServerContext) -> tuple[FastMCP, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    return build_server(context, meter_provider=MeterProvider(metric_readers=[reader])), reader


def named(server: FastMCP, name: str) -> Client:
    return Client(server, client_info=Implementation(name=name, version="1"))


async def test_a_call_counts_its_tool_name(context: ServerContext) -> None:
    server, reader = served(context)
    async with named(server, "agent") as client:
        await client.call_tool("list_databases", {})
    assert counted(reader) == [({"tool": "list_databases"}, 1)]


async def test_a_refused_call_counts(context: ServerContext) -> None:
    server, reader = served(context)
    async with named(server, "agent") as client:
        with pytest.raises(ToolError):
            await client.call_tool("list_databases", {"unknown": 1})
    assert counted(reader) == [({"tool": "list_databases"}, 1)]


async def test_a_name_outside_the_roster_counts_as_other(context: ServerContext) -> None:
    server, reader = served(context)
    async with named(server, "agent") as client:
        with pytest.raises(ToolError):
            await client.call_tool("no_such_tool", {})
    assert counted(reader) == [({"tool": "other"}, 1)]


async def test_the_page_calls_are_not_counted(context: ServerContext) -> None:
    server, reader = served(context)
    async with named(server, "view") as client:
        await client.call_tool("list_databases", {})
    assert counted(reader) == []


def test_counting_comes_first(context: ServerContext) -> None:
    server, _ = served(context)
    assert type(server.middleware[0]) is Counting


async def test_without_a_provider_nothing_is_counted(context: ServerContext) -> None:
    server = build_server(context)
    async with named(server, "agent") as client:
        await client.call_tool("list_databases", {})
    assert not isinstance(metrics.get_meter_provider(), MeterProvider)


async def test_a_call_whose_client_is_unknown_counts() -> None:
    reader = InMemoryMetricReader()
    counting = Counting(["list_databases"], MeterProvider(metric_readers=[reader]))
    message = CallToolRequestParams(name="list_databases", arguments={})
    context = MiddlewareContext(message=message, fastmcp_context=None)

    async def answered(_: MiddlewareContext[CallToolRequestParams]) -> ToolResult:
        return ToolResult(content="ok")

    await counting.on_call_tool(context, answered)
    assert counted(reader) == [({"tool": "list_databases"}, 1)]
