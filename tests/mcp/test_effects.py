from __future__ import annotations

import pytest
from fastmcp import FastMCP

from ecosemantic.mcp.effects import COMPUTE, DELETE, READ, WRITE, effect_of


def test_an_effect_is_read_from_the_tag_and_then_the_annotations() -> None:
    assert effect_of(READ, set()) == "read"
    assert effect_of(WRITE, set()) == "write"
    assert effect_of(DELETE, set()) == "delete"
    assert effect_of(READ, {COMPUTE}) == "compute"
    assert effect_of(WRITE, {COMPUTE}) == "compute"


def test_a_tool_registered_with_neither_is_refused() -> None:
    with pytest.raises(ValueError, match="READ, WRITE or DELETE"):
        effect_of(None, set())


async def test_the_computes_are_the_three_calculations_and_the_run(full_server: FastMCP) -> None:
    effects = {
        tool.name: effect_of(tool.annotations, tool.tags) for tool in await full_server.list_tools()
    }
    assert sorted(name for name, effect in effects.items() if effect == "compute") == [
        "calculate_impact",
        "calculate_inventory",
        "contribution_analysis",
        "start_monte_carlo",
    ]
    assert effects["search_processes"] == "read"
    assert effects["create_process"] == "write"
    assert effects["delete_process"] == "delete"
