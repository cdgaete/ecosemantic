"""A server over one context whose calls are recorded on a port of its own, for the suites that
need no caller."""

from __future__ import annotations

import dataclasses
from types import ModuleType

from fastmcp import FastMCP

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.recording import Recorder
from tests.memory_activity import MemoryActivity


def registered(context: ServerContext, *modules: ModuleType) -> FastMCP:
    """A server recording each call on an activity port of its own, with each module's tools
    registered."""
    server = FastMCP(
        name="ecosemantic",
        middleware=[Recorder(dataclasses.replace(context, activity=MemoryActivity()))],
    )
    for module in modules:
        module.register(server)
    return server
