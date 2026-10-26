from __future__ import annotations

import dataclasses

from fastmcp import Client

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.panels import PANELS
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import ProductSystem, method_id
from tests.fixture_data import GWP

GWP_ID = method_id(" > ".join(GWP))
CARRIERS = {
    "contribution_analysis": "contribution",
    "calculate_impact": "impact",
    "calculate_inventory": "inventory",
}


async def test_exactly_three_tools_name_a_panel(context: ServerContext) -> None:
    async with Client(build_server(context)) as client:
        tools = await client.list_tools()
    for tool in tools:
        ui = (tool.meta or {}).get("ui")
        if tool.name in CARRIERS:
            assert ui is not None and ui["resourceUri"] == PANELS[CARRIERS[tool.name]], tool.name
            assert ui["csp"] == {"connectDomains": [], "resourceDomains": []}
        else:
            assert ui is None, tool.name


async def test_the_resources_are_html_documents_speaking_the_protocol(
    context: ServerContext,
) -> None:
    async with Client(build_server(context)) as client:
        listed = {str(r.uri): r for r in await client.list_resources()}
        for uri in PANELS.values():
            assert listed[uri].mime_type == "text/html;profile=mcp-app"
            content = (await client.read_resource(uri))[0]
            assert content.mime_type == "text/html;profile=mcp-app"
            text = content.text
            assert text.lstrip().lower().startswith("<!doctype html>")
            for method in (
                "ui/initialize",
                "ui/notifications/initialized",
                "ui/notifications/tool-result",
                "ui/open-link",
            ):
                assert method in text, (uri, method)
            assert "<script src=" not in text and "<link " not in text


async def test_each_result_links_to_the_page_that_shows_it(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    bound = dataclasses.replace(context, view_url="http://127.0.0.1:1?token=abc")
    system_id = str(fixture_system_stored.id)
    async with Client(build_server(bound)) as client:
        contributions = await client.call_tool(
            "contribution_analysis", {"product_system_id": system_id, "method_id": GWP_ID}
        )
        impact = await client.call_tool(
            "calculate_impact",
            {
                "product_system_id": system_id,
                "impact_method": "gwp",
                "demand": [{"ref": {"kind": "foreground", "code": "widget"}, "amount": 2.0}],
            },
        )
        inventory = await client.call_tool(
            "calculate_inventory", {"product_system_id": system_id, "limit": 5}
        )
    base = f"http://127.0.0.1:1/systems/{system_id}/results"
    assert contributions.structured_content["view_url"] == (
        f"{base}/tree?method_id={GWP_ID}&token=abc"
    )
    assert impact.structured_content["view_url"] == (
        f"{base}/impact?impact_method=gwp&amount=2.0&token=abc"
    )
    assert inventory.structured_content["view_url"] == f"{base}/inventory?token=abc"


async def test_each_panel_says_it_is_a_figure_the_host_fills_from_its_call(
    context: ServerContext,
) -> None:
    async with Client(build_server(context)) as client:
        listed = {str(r.uri): r for r in await client.list_resources()}
    for tool, name in CARRIERS.items():
        description = listed[PANELS[name]].description or ""
        assert "carries no data" in description and tool in description, name
