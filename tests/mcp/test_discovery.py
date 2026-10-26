from __future__ import annotations

import json

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.mcp import discovery
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    built = build_server()
    discovery.register(built, context)
    return built


async def test_the_roster_is_the_seven_in_order(server: FastMCP) -> None:
    async with Client(server) as client:
        assert [t.name for t in await client.list_tools()] == [
            "list_databases",
            "search_processes",
            "search_elementary_flows",
            "search_methods",
            "get_background_process",
            "get_elementary_flow",
            "list_vocabulary",
        ]


async def test_list_databases(server: FastMCP) -> None:
    async with Client(server) as client:
        out = (await client.call_tool("list_databases", {})).structured_content
        assert FIXTURE_DB in [d["name"] for d in out["value"]]


async def test_search_processes_pages_and_hints(server: FastMCP) -> None:
    async with Client(server) as client:
        first = (
            await client.call_tool(
                "search_processes", {"database": FIXTURE_DB, "query": "production", "limit": 4}
            )
        ).structured_content
        assert len(first["items"]) == 4 and first["has_more"] is True
        assert "cursor" in first["hint"]
        empty = (
            await client.call_tool(
                "search_processes",
                {"database": FIXTURE_DB, "query": "production", "location": "CH"},
            )
        ).structured_content
        assert empty["items"] == [] and "location" in empty["hint"]


async def test_get_background_process_and_flow(server: FastMCP) -> None:
    async with Client(server) as client:
        steel = (
            await client.call_tool(
                "get_background_process",
                {"database": FIXTURE_DB, "process_id": CODES["steel"], "exchanges": True},
            )
        ).structured_content["value"]
        assert steel["name"] == "steel production"
        assert {e["type"] for e in steel["exchanges"]} == {"product", "elementary"}
        flow = (
            await client.call_tool(
                "get_elementary_flow",
                {"database": FIXTURE_DB, "flow_id": FLOW_IDS["water_in"]},
            )
        ).structured_content["value"]
        # a bundle files a natural resource under openLCA's "Resource"
        assert flow["compartment"] == "Resource"


async def test_list_vocabulary_answers_the_four_original_kinds(server: FastMCP) -> None:
    async with Client(server) as client:

        async def kind(k: str) -> list[dict[str, object]]:
            out = await client.call_tool("list_vocabulary", {"database": FIXTURE_DB, "kind": k})
            return out.structured_content["value"]

        assert [t["value"] for t in await kind("units")] == [
            "kilogram",
            "kilowatt hour",
            "ton kilometer",
        ]
        assert [t["value"] for t in await kind("locations")] == ["GLO"]
        air = next(t for t in await kind("compartments") if t["value"] == "air")
        assert air["detail"] == "3 flows"
        # a bundle's category name "climate change > GWP100" holds the indicator after " > "
        categories = [t["value"] for t in await kind("impact_categories")]
        assert "gwp > climate change" in categories


async def test_a_typed_error_arrives_as_the_envelope(server: FastMCP) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("list_vocabulary", {"database": "nothing", "kind": "units"})
        payload = json.loads(str(caught.value))
        assert payload["error"] == "not_found" and "nothing" in payload["message"]


async def test_a_search_on_a_database_the_store_does_not_serve_is_not_found(
    server: FastMCP,
) -> None:
    async with Client(server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("search_processes", {"database": "nowhere", "query": "widget"})
        payload = json.loads(str(caught.value))
        assert payload["error"] == "not_found" and "'nowhere'" in payload["message"]


async def test_the_elementary_flows_database_is_addressable(server: FastMCP) -> None:
    async with Client(server) as client:
        hits = (
            await client.call_tool(
                "search_elementary_flows", {"database": "fixture-biosphere", "query": "carbon"}
            )
        ).structured_content["items"]
        assert [h["name"] for h in hits] == ["Carbon dioxide, fossil"]
        flow = (
            await client.call_tool(
                "get_elementary_flow",
                {"database": "fixture-biosphere", "flow_id": FLOW_IDS["co2"]},
            )
        ).structured_content["value"]
        assert flow["ref"]["database"] == "fixture-biosphere"


async def test_list_vocabulary_names_the_impact_methods(server: FastMCP) -> None:
    async with Client(server) as client:
        out = await client.call_tool(
            "list_vocabulary", {"database": FIXTURE_DB, "kind": "impact_methods"}
        )
        assert [(t["value"], t["detail"]) for t in out.structured_content["value"]] == [
            ("gwp", "1 method"),
            ("water", "1 method"),
        ]


async def test_an_empty_method_search_names_the_vocabulary(server: FastMCP) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool("search_methods", {"database": FIXTURE_DB, "query": "nothing"})
        ).structured_content
        assert out["items"] == [] and "list_vocabulary" in out["hint"]


async def test_search_elementary_flows_filters_by_the_port_vocabulary(server: FastMCP) -> None:
    async with Client(server) as client:
        hits = (
            await client.call_tool(
                "search_elementary_flows",
                {"database": FIXTURE_DB, "query": "water", "flow_type": "natural resource"},
            )
        ).structured_content["items"]
        assert [h["name"] for h in hits] == ["Water, river"]
        with pytest.raises(ToolError):
            await client.call_tool(
                "search_elementary_flows",
                {"database": FIXTURE_DB, "query": "water", "flow_type": "resource"},
            )


async def test_a_filtered_search_whose_words_match_blames_the_filter(server: FastMCP) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "search_processes",
                {"database": FIXTURE_DB, "query": "production", "location": "CH"},
            )
        ).structured_content
        assert out["items"] == []
        assert "location" in out["hint"] and "the words alone match" in out["hint"]


async def test_a_filtered_search_whose_words_match_nothing_says_to_name_fewer_words(
    server: FastMCP,
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "search_processes",
                {"database": FIXTURE_DB, "query": "unobtainium", "location": "CH"},
            )
        ).structured_content
        assert out["items"] == []
        assert "location" not in out["hint"]
        assert "name fewer words" in out["hint"]


async def test_an_unfiltered_search_that_matches_nothing_says_to_name_fewer_words(
    server: FastMCP,
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "search_processes", {"database": FIXTURE_DB, "query": "unobtainium"}
            )
        ).structured_content
        assert out["items"] == []
        assert out["hint"] is not None and "name fewer words" in out["hint"]


async def test_a_flow_search_whose_words_match_blames_the_flow_type(server: FastMCP) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "search_elementary_flows",
                {"database": FIXTURE_DB, "query": "water", "flow_type": "emission"},
            )
        ).structured_content
        assert out["items"] == []
        assert "flow_type" in out["hint"] and "the words alone match" in out["hint"]


async def test_a_flow_search_whose_words_match_nothing_says_to_name_fewer_words(
    server: FastMCP,
) -> None:
    async with Client(server) as client:
        out = (
            await client.call_tool(
                "search_elementary_flows",
                {"database": FIXTURE_DB, "query": "unobtainium", "flow_type": "emission"},
            )
        ).structured_content
        assert out["items"] == []
        assert "flow_type" not in out["hint"]
        assert "name fewer words" in out["hint"]
