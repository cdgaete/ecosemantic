from __future__ import annotations

import dataclasses

from fastmcp import Client, FastMCP
from mcp.types import Implementation

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import INSTRUCTIONS, build_server


async def test_server_builds_and_serves_no_tools_yet() -> None:
    server = build_server()
    assert isinstance(server, FastMCP)
    async with Client(server) as client:
        assert await client.list_tools() == []


async def test_server_names_itself() -> None:
    server = build_server()
    assert server.name == "ecosemantic"
    assert server.version


def test_the_instructions_name_the_install_tools() -> None:
    assert "list_sources" in INSTRUCTIONS
    assert "install_database" in INSTRUCTIONS


async def test_the_server_keeps_the_client_that_introduced_itself(
    context: ServerContext,
) -> None:
    held = dataclasses.replace(context, client={})
    introducing = Implementation(name="Claude Desktop", version="1.2.3")
    # a client that introduces itself with the initialize handshake rather than by discovering
    async with Client(build_server(held), client_info=introducing, mode="legacy"):
        pass
    assert held.client == {"name": "Claude Desktop", "version": "1.2.3"}
