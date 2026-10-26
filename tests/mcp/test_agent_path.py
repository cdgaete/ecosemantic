from __future__ import annotations

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import ProductSystem
from tests.fixture_data import FIXTURE_DB


async def test_search_then_calculate_then_drill_down(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    async with Client(build_server(context)) as client:
        hits = (
            await client.call_tool("search_methods", {"database": FIXTURE_DB, "query": "climate"})
        ).structured_content
        method_id = hits["items"][0]["id"]
        assert method_id.startswith("m_")

        impact = (
            await client.call_tool(
                "calculate_impact", {"product_system_id": system_id, "method_id": method_id}
            )
        ).structured_content["value"]
        total = impact["scores"][0]["value"]
        assert total == pytest.approx(4.158)

        flat = (
            await client.call_tool(
                "contribution_analysis",
                {"product_system_id": system_id, "method_id": method_id, "by": "process"},
            )
        ).structured_content["value"]
        assert flat["total"]["value"] == pytest.approx(total)
        assert sum(p["score"] for p in flat["processes"]) == pytest.approx(total)


async def test_a_wrong_method_string_corrects_itself_in_one_step(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    async with Client(build_server(context)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": system_id, "method_id": "climate change"},
            )
        suggestions = json.loads(str(caught.value))["details"]["suggestions"]
        assert suggestions

        retry = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": system_id, "method_id": suggestions[0]["id"]},
            )
        ).structured_content["value"]
        assert retry["scores"][0]["value"] == pytest.approx(4.158)


async def test_the_vocabulary_answers_what_a_filter_needs(context: ServerContext) -> None:
    async with Client(build_server(context)) as client:
        units = (
            await client.call_tool("list_vocabulary", {"database": FIXTURE_DB, "kind": "units"})
        ).structured_content["value"]
        unit = next(t["value"] for t in units if t["value"] == "kilowatt hour")
        hits = (
            await client.call_tool(
                "search_processes",
                {"database": FIXTURE_DB, "query": "production", "unit": unit},
            )
        ).structured_content
        assert [h["name"] for h in hits["items"]] == ["electricity production"]
