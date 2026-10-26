from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.mcp import modelling, requests, systems
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Actor
from ecosemantic.ports.types import RequestDraft

PERSON = Actor(kind="person", name="Carlos")


@pytest.fixture(scope="module")
def server(context: ServerContext) -> FastMCP:
    built = build_server()
    systems.register(built, context)
    requests.register(built, context)
    modelling.register(built, context)
    return built


async def test_a_request_rides_on_the_next_write_and_resolves_once(
    server: FastMCP, context: ServerContext, bottle: str
) -> None:
    system_id = uuid.UUID(bottle)
    stored = await context.storage.get_product_system(system_id)
    await context.storage.post_request(
        system_id,
        RequestDraft(
            actor=PERSON, kind="return", at_hash=stored.hash or "", message="name the location"
        ),
    )
    async with Client(server) as client:
        made = (
            await client.call_tool(
                "create_process",
                {
                    "product_system_id": bottle,
                    "code": "cap",
                    "name": "cap production",
                    "unit": "unit",
                    "reference_product": "cap",
                },
            )
        ).structured_content
        assert made["open_requests"] == 1 and made["view_url"] is None
        listed = (
            await client.call_tool("list_requests", {"product_system_id": bottle})
        ).structured_content["value"]
        assert len(listed) == 1 and listed[0]["kind"] == "return" and listed[0]["outcome"] is None
        resolved = (
            await client.call_tool(
                "resolve_request",
                {
                    "product_system_id": bottle,
                    "request_id": listed[0]["id"],
                    "resolution": "overridden",
                    "message": "GLO is the supplier's own figure",
                },
            )
        ).structured_content["value"]
        assert resolved["outcome"]["resolution"] == "overridden"
        read = (
            await client.call_tool("get_product_system", {"product_system_id": bottle})
        ).structured_content
        assert read["open_requests"] == 0
        assert (
            await client.call_tool("list_requests", {"product_system_id": bottle})
        ).structured_content["value"] == []
        everything = (
            await client.call_tool(
                "list_requests", {"product_system_id": bottle, "open_only": False}
            )
        ).structured_content["value"]
        assert len(everything) == 1
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "resolve_request",
                {
                    "product_system_id": bottle,
                    "request_id": listed[0]["id"],
                    "resolution": "accepted",
                    "message": "again",
                },
            )
        assert json.loads(str(caught.value))["error"] == "conflict"


async def test_cards_carry_no_link_without_a_view(server: FastMCP, bottle: str) -> None:
    async with Client(server) as client:
        cards = (await client.call_tool("list_product_systems", {})).structured_content["value"]
    card = next(c for c in cards if c["id"] == bottle)
    assert card["view_url"] is None


def test_a_deep_link_keeps_the_token(context: ServerContext) -> None:
    system_id = uuid.uuid4()
    with_token = dataclasses.replace(context, view_url="http://lab.example:8765?token=abc")
    assert (
        with_token.deep_link(system_id) == f"http://lab.example:8765/systems/{system_id}?token=abc"
    )
    plain = dataclasses.replace(context, view_url="http://127.0.0.1:8765/")
    assert plain.deep_link(system_id) == f"http://127.0.0.1:8765/systems/{system_id}"
    assert context.deep_link(system_id) is None
