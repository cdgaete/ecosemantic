from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import ROSTER, build_server

SYSTEM_ID = uuid.UUID("8289a613-03a3-40e2-8802-f1972beb4692")


async def test_view_link_answers_the_url_and_one_system(context: ServerContext) -> None:
    bound = dataclasses.replace(context, view_url="http://192.0.2.86:39029?token=abc")
    async with Client(build_server(bound)) as client:
        whole = await client.call_tool("view_link", {})
        assert whole.data.value == "http://192.0.2.86:39029?token=abc"
        one = await client.call_tool("view_link", {"product_system_id": str(SYSTEM_ID)})
        assert one.data.value == f"http://192.0.2.86:39029/systems/{SYSTEM_ID}?token=abc"


async def test_view_link_without_a_view_is_not_supported(context: ServerContext) -> None:
    async with Client(build_server(context)) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("view_link", {})
        assert json.loads(str(caught.value))["error"] == "not_supported"


def test_view_link_is_in_the_roster() -> None:
    assert "view_link" in ROSTER
    assert ROSTER[-1] == "view_link"
    assert len(ROSTER) == 48
