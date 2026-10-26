"""Counts each agent's tool calls by name on a meter provider the server is handed."""

from __future__ import annotations

from collections.abc import Collection

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams
from opentelemetry.metrics import MeterProvider

from ecosemantic.mcp.recording import VIEW, client_name

TOOL_CALLS = "ecosemantic.tool.calls"
METER = "ecosemantic"
OTHER = "other"


class Counting(Middleware):
    """Adds one to the tool-call counter when a call ends, refused or not; the page's calls
    are not counted."""

    def __init__(self, roster: Collection[str], provider: MeterProvider) -> None:
        self.roster = frozenset(roster)
        self.calls = provider.get_meter(METER).create_counter(
            TOOL_CALLS, description="Tool calls by tool name"
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        finally:
            if client_name(context) != VIEW:
                name = context.message.name
                self.calls.add(1, {"tool": name if name in self.roster else OTHER})
