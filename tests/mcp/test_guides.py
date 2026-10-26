from __future__ import annotations

import json
import re
from importlib import resources

import pytest
from fastmcp import Client, FastMCP

from ecosemantic.mcp.guides import GUIDES
from ecosemantic.mcp.server import INSTRUCTIONS

STEP = re.compile(r"```json\n(.*?)\n```", re.S)


def steps(name: str) -> list[dict]:
    text = (resources.files("ecosemantic.mcp") / "guides" / f"{name}.md").read_text()
    return [json.loads(block) for block in STEP.findall(text)]


def bound(value: object, saved: dict[str, object]) -> object:
    if isinstance(value, str) and value in saved:
        return saved[value]
    if isinstance(value, dict):
        return {key: bound(item, saved) for key, item in value.items()}
    if isinstance(value, list):
        return [bound(item, saved) for item in value]
    return value


def at(answer: object, path: str) -> object:
    for part in path.split("."):
        if isinstance(answer, list):
            answer = answer[int(part)]
        elif isinstance(answer, dict):
            answer = answer[part]
    return answer


async def test_the_server_serves_each_guide_as_markdown(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        listed = {str(r.uri): r for r in await client.list_resources()}
        for uri in GUIDES.values():
            assert listed[uri].mime_type == "text/markdown"
            text = (await client.read_resource(uri))[0].text
            assert text.startswith("# ")
            assert uri in INSTRUCTIONS


@pytest.mark.parametrize("name", list(GUIDES))
async def test_each_guide_s_worked_example_runs_on_the_fixture_database(
    full_server: FastMCP, name: str
) -> None:
    saved: dict[str, object] = {}
    expected = 0
    async with Client(full_server) as client:
        for step in steps(name):
            answer = await client.call_tool(step["tool"], bound(step["arguments"], saved))
            content = answer.structured_content
            if step["tool"] == "create_product_system":
                saved["{system}"] = content["value"]["id"]
            if step["tool"] in {"search_processes", "search_elementary_flows"}:
                saved[f"{{hit:{step['arguments']['query']}}}"] = content["items"][0]["ref"]
            if step["tool"] == "search_methods":
                saved[f"{{method:{step['arguments']['query']}}}"] = content["items"][0]["id"]
            if "expect" in step:
                expected += 1
                assert at(content, step["expect"]["path"]) == pytest.approx(
                    step["expect"]["equals"], rel=1e-9
                )
    assert expected
