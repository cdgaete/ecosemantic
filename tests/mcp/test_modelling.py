from __future__ import annotations

import json

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS


async def _error(client: Client, tool: str, args: dict[str, object]) -> dict[str, object]:
    with pytest.raises(ToolError) as caught:
        await client.call_tool(tool, args)
    return json.loads(str(caught.value))


async def test_create_update_delete_a_process(full_server: FastMCP, bottle: str) -> None:
    async with Client(full_server) as client:
        made = (
            await client.call_tool(
                "create_process",
                {
                    "product_system_id": bottle,
                    "code": "bottle",
                    "name": "bottle assembly",
                    "unit": "unit",
                    "reference_product": "bottle",
                },
            )
        ).structured_content
        assert made["entry"]["seq"] == 2
        assert [e["type"] for e in made["value"]["exchanges"]] == ["production"]
        assert {c["entity"] for c in made["entry"]["changes"]} == {"process", "exchange"}

        patched = (
            await client.call_tool(
                "update_process",
                {
                    "product_system_id": bottle,
                    "code": "bottle",
                    "location": "CH",
                    "unit": "kilogram",
                },
            )
        ).structured_content
        assert patched["value"]["location"] == "CH"
        assert patched["value"]["exchanges"][0]["unit"] == "kilogram"

        deleted = (
            await client.call_tool(
                "delete_process", {"product_system_id": bottle, "code": "bottle"}
            )
        ).structured_content
        # a delete answers as every write does: what it removed, the entry, the open requests
        assert deleted["value"] == "bottle" and deleted["open_requests"] == 0
        entry = deleted["entry"]
        assert entry["seq"] == 4 and entry["changes"][0]["op"] == "delete"
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": bottle})
        ).structured_content["value"]
        assert whole["processes"] == []


async def test_create_process_refuses_a_staging_argument(full_server: FastMCP, bottle: str) -> None:
    args = {
        "product_system_id": bottle,
        "code": "draft",
        "name": "draft",
        "unit": "kilogram",
        "reference_product": "draft",
        "staging": True,
    }
    async with Client(full_server) as client:
        with pytest.raises(ToolError, match="staging"):
            await client.call_tool("create_process", args)


async def test_refusals_arrive_as_their_envelopes(full_server: FastMCP, bottle: str) -> None:
    args = {
        "product_system_id": bottle,
        "code": "cap",
        "name": "cap",
        "unit": "kilogram",
        "reference_product": "cap",
    }
    async with Client(full_server) as client:
        await client.call_tool("create_process", args)
        assert (await _error(client, "create_process", args))["error"] == "conflict"
        assert (await _error(client, "create_process", {**args, "code": "a b"}))[
            "error"
        ] == "invalid"
        assert (
            await _error(client, "update_process", {"product_system_id": bottle, "code": "cap"})
        )["error"] == "invalid"
        assert (
            await _error(client, "delete_process", {"product_system_id": bottle, "code": "lid"})
        )["error"] == "not_found"


async def _process(client: Client, system_id: str, code: str, unit: str) -> None:
    await client.call_tool(
        "create_process",
        {
            "product_system_id": system_id,
            "code": code,
            "name": code,
            "unit": unit,
            "reference_product": code,
        },
    )


async def test_create_exchange_resolves_its_provider(full_server: FastMCP, bottle: str) -> None:
    async with Client(full_server) as client:
        await _process(client, bottle, "bottle", "unit")
        steel = (
            await client.call_tool(
                "create_exchange",
                {
                    "product_system_id": bottle,
                    "code": "bottle",
                    "type": "product",
                    "amount": 0.5,
                    "input": {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]},
                },
            )
        ).structured_content
        assert steel["value"]["unit"] == "kilogram" and steel["value"]["name"] == "steel"
        co2 = (
            await client.call_tool(
                "create_exchange",
                {
                    "product_system_id": bottle,
                    "code": "bottle",
                    "type": "elementary",
                    "amount": 0.1,
                    "input": {
                        "kind": "elementary_flow",
                        "database": FIXTURE_BIO,
                        "id": FLOW_IDS["co2"],
                    },
                },
            )
        ).structured_content
        assert co2["value"]["name"] == "Carbon dioxide, fossil"
        assert co2["value"]["unit"] == "kilogram"
        wrong = await _error(
            client,
            "create_exchange",
            {
                "product_system_id": bottle,
                "code": "bottle",
                "type": "product",
                "amount": 1.0,
                "unit": "kilowatt hour",
                "input": {"kind": "background", "database": FIXTURE_DB, "id": CODES["steel"]},
            },
        )
        assert wrong["error"] == "invalid" and "kilogram" in wrong["message"]
        missing = await _error(
            client,
            "create_exchange",
            {
                "product_system_id": bottle,
                "code": "bottle",
                "type": "product",
                "amount": 1.0,
                "input": {
                    "kind": "background",
                    "database": FIXTURE_DB,
                    "id": CODES["steel"][:-1] + "0",
                },
            },
        )
        assert missing["error"] == "not_found"


async def test_update_and_delete_an_exchange(full_server: FastMCP, bottle: str) -> None:
    async with Client(full_server) as client:
        await _process(client, bottle, "bottle", "unit")
        await _process(client, bottle, "cap", "kilogram")
        made = (
            await client.call_tool(
                "create_exchange",
                {
                    "product_system_id": bottle,
                    "code": "bottle",
                    "type": "product",
                    "formula": "2 * 0.01",
                    "input": {"kind": "foreground", "code": "cap"},
                },
            )
        ).structured_content["value"]
        assert made["unit"] == "kilogram" and made["amount"] == pytest.approx(0.02)
        blocked = await _error(
            client,
            "update_exchange",
            {"product_system_id": bottle, "exchange_id": made["id"], "amount": 0.03},
        )
        assert blocked["error"] == "invalid" and "formula" in blocked["message"]
        patched = (
            await client.call_tool(
                "update_exchange",
                {
                    "product_system_id": bottle,
                    "exchange_id": made["id"],
                    "amount": 0.03,
                    "clear": ["formula"],
                    "comment": "two caps",
                },
            )
        ).structured_content["value"]
        assert patched["amount"] == 0.03 and patched["formula"] is None
        assert patched["comment"] == "two caps"
        deleted = (
            await client.call_tool(
                "delete_exchange", {"product_system_id": bottle, "exchange_id": made["id"]}
            )
        ).structured_content
        assert deleted["value"] == made["id"] and deleted["open_requests"] == 0
        entry = deleted["entry"]
        assert entry["changes"] == [
            {
                "op": "delete",
                "entity": "exchange",
                "id": made["id"],
                "field": None,
                "before": None,
                "after": None,
            }
        ]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": bottle})
        ).structured_content["value"]
        assert [len(p["exchanges"]) for p in whole["processes"]] == [1, 1]


async def test_an_object_sent_as_its_json_text_is_refused_naming_what_to_send(
    full_server: FastMCP, bottle: str
) -> None:
    base = {"product_system_id": bottle, "code": "bottle", "type": "product"}
    async with Client(full_server) as client:
        as_text = await _error(
            client, "create_exchange", {**base, "input": '{"code": "bottle", "kind": "foreground"}'}
        )
        spread = await _error(
            client,
            "create_exchange",
            {**base, "amount": 1, "uncertainty": '{"type": "lognormal", "params": {}}'},
        )
        wrong = await _error(client, "create_exchange", {**base, "amount": "lots"})
    for payload, field in ((as_text, "'input'"), (spread, "'uncertainty'")):
        message = str(payload["message"])
        assert payload["error"] == "invalid" and field in message
        assert "does not take" not in message
        assert "a string holding JSON" in message and "the object itself" in message
    message = str(wrong["message"])
    assert "'amount'" in message and "got a string" in message
    assert "does not take" not in message and "holding JSON" not in message


async def test_an_unknown_argument_answers_the_typed_envelope_with_its_remedy(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        payload = await _error(
            client,
            "update_exchange",
            {
                "product_system_id": bottle,
                "exchange_id": "00000000-0000-0000-0000-000000000000",
                "input": {"kind": "foreground", "code": "x"},
            },
        )
    assert payload["error"] == "invalid"
    message = str(payload["message"])
    assert "'input'" in message and "exchange_id" in message and "formula" in message
    assert "delete_exchange" in message and "create_exchange" in message
    assert "rebase" in message and "errors.pydantic.dev" not in message
