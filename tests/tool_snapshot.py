"""What a server lists for each tool, in the form a recorded snapshot holds."""

from __future__ import annotations

from fastmcp import Client, FastMCP
from pydantic import JsonValue

FIELDS = {"name", "title", "description", "input_schema", "output_schema", "annotations"}


async def snapshot(server: FastMCP) -> list[dict[str, JsonValue]]:
    """Every tool's name, description, schemas and annotations, ordered by name."""
    async with Client(server) as client:
        tools = await client.list_tools()
    return sorted(
        (tool.model_dump(mode="json", include=FIELDS, exclude_none=True) for tool in tools),
        key=lambda tool: str(tool["name"]),
    )
