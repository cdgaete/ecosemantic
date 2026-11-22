"""The registered tool run in the server's own process, as the page's call."""

from __future__ import annotations

from collections.abc import Mapping

from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError as ArgumentsInvalid
from fastmcp.tools.base import ToolResult
from pydantic import JsonValue, ValidationError

from ecosemantic.errors import Invalid
from ecosemantic.mcp.calls import InProgress
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import refused_arguments, tool_error
from ecosemantic.mcp.recording import VIEW, recorded


async def run_tool(
    server: FastMCP,
    context: ServerContext,
    name: str,
    arguments: Mapping[str, JsonValue],
    started: bool = False,
) -> dict[str, JsonValue]:
    """Run a registered tool in this process, with no MCP session: a caller inside the server
    pays for the tool alone, and its call is refused and recorded as an agent's is."""
    tool = await server.get_tool(name)
    if tool is None:
        raise tool_error(Invalid(f"Unknown tool: {name!r}"))

    async def run() -> ToolResult:
        try:
            return await server.call_tool(name, dict(arguments), run_middleware=False)
        except ArgumentsInvalid as error:
            raise refused_arguments(tool, error) from error
        except ValidationError as error:
            raise tool_error(Invalid(f"{name}: {error.title} does not validate")) from error

    result = await recorded(
        tool,
        dict(arguments),
        InProgress(context=context, agent=VIEW, client=VIEW, origin="view"),
        started,
        run,
    )
    content = result.structured_content
    if content is None:
        raise RuntimeError(f"{name!r} answered no structured content")
    return content
