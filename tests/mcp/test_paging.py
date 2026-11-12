from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.model.entities import ProductSystem
from tests.fixture_data import FIXTURE_DB


def valid_calls(system_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """One valid call per tool that takes a limit, without the limit."""
    system = {"product_system_id": str(system_id)}
    return {
        "search_processes": {"database": FIXTURE_DB, "query": "steel"},
        "search_elementary_flows": {"database": FIXTURE_DB, "query": "fossil"},
        "search_methods": {"database": FIXTURE_DB, "query": "fixture"},
        "get_product_system_log": system,
        "calculate_inventory": system,
    }


async def test_every_tool_taking_a_limit_refuses_one_below_one(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    calls = valid_calls(fixture_system_stored.id)
    async with Client(full_server) as client:
        listed = await client.list_tools()
        assert {t.name for t in listed if "limit" in t.input_schema.get("properties", {})} == set(
            calls
        )
        for name, arguments in calls.items():
            for limit in (0, -1):
                with pytest.raises(ToolError) as caught:
                    await client.call_tool(name, {**arguments, "limit": limit})
                payload = json.loads(str(caught.value))
                assert payload["error"] == "invalid", name
                assert "limit is at least 1" in payload["message"], name


async def test_a_limit_of_one_pages_to_the_end(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = {"product_system_id": str(fixture_system_stored.id)}
    async with Client(full_server) as client:

        async def page(**extra: Any) -> dict[str, Any]:
            return (
                await client.call_tool("calculate_inventory", {**system, **extra})
            ).structured_content

        whole = await page(limit=100)
        every = [row["name"] for row in whole["items"]]
        assert len(every) > 1 and whole["has_more"] is False
        seen: list[str] = []
        cursor = None
        while True:
            answer = await page(limit=1, cursor=cursor)
            assert len(answer["items"]) == 1
            seen.extend(row["name"] for row in answer["items"])
            if not answer["has_more"]:
                break
            cursor = answer["next_cursor"]
        assert seen == every
