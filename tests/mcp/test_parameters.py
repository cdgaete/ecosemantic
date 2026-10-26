from __future__ import annotations

import json

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.model.entities import method_id
from tests.fixture_data import CODES, FIXTURE_DB, GWP

GWP_ID = method_id(" > ".join(GWP))


async def _error(client: Client, tool: str, args: dict[str, object]) -> dict[str, object]:
    with pytest.raises(ToolError) as caught:
        await client.call_tool(tool, args)
    return json.loads(str(caught.value))


async def _electricity_bottle(client: Client, system_id: str) -> str:
    """A bottle drawing elec_kwh kilowatt hours of electricity, the system's reference process;
    returns the exchange id."""
    await client.call_tool(
        "create_process",
        {
            "product_system_id": system_id,
            "code": "bottle",
            "name": "bottle",
            "unit": "unit",
            "reference_product": "bottle",
        },
    )
    await client.call_tool(
        "update_product_system", {"product_system_id": system_id, "reference_process": "bottle"}
    )
    await client.call_tool(
        "set_parameters",
        {"product_system_id": system_id, "parameters": [{"name": "elec_kwh", "value": 2.0}]},
    )
    made = await client.call_tool(
        "create_exchange",
        {
            "product_system_id": system_id,
            "code": "bottle",
            "type": "product",
            "formula": "elec_kwh",
            "input": {"kind": "background", "database": FIXTURE_DB, "id": CODES["elec"]},
        },
    )
    return made.structured_content["value"]["id"]


async def test_set_parameters_drives_a_formula_and_a_case(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        exchange_id = await _electricity_bottle(client, bottle)
        space = (
            await client.call_tool(
                "set_parameters",
                {
                    "product_system_id": bottle,
                    "parameters": [{"name": "elec_kwh", "value": 3.0}],
                    "cases": [{"name": "lean", "values": {"elec_kwh": 1.0}}],
                },
            )
        ).structured_content
        assert [p["name"] for p in space["value"]["parameters"]] == ["elec_kwh"]
        assert [c["name"] for c in space["value"]["cases"]] == ["lean"]
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": bottle})
        ).structured_content["value"]
        exchange = next(e for e in whole["processes"][0]["exchanges"] if e["id"] == exchange_id)
        assert exchange["amount"] == 3.0
        out = (
            await client.call_tool(
                "calculate_impact",
                {"product_system_id": bottle, "method_id": GWP_ID, "variants": ["lean"]},
            )
        ).structured_content["value"]
        assert out["scores"][0]["value"] == pytest.approx(3.0)
        assert out["variants"][0]["scores"][0]["value"] == pytest.approx(1.0)


async def test_set_parameters_refusals(full_server: FastMCP, bottle: str) -> None:
    async with Client(full_server) as client:
        await _electricity_bottle(client, bottle)
        used = await _error(
            client,
            "set_parameters",
            {"product_system_id": bottle, "delete_parameters": ["elec_kwh"]},
        )
        assert used["error"] == "invalid" and "bottle" in used["message"]
        empty = await _error(client, "set_parameters", {"product_system_id": bottle})
        assert empty["error"] == "invalid"
        derived = await _error(
            client,
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [{"name": "twice", "formula": "elec_kwh * 2"}],
                "cases": [{"name": "x", "values": {"twice": 1.0}}],
            },
        )
        assert derived["error"] == "invalid" and "twice" in derived["message"]


async def test_a_scenario_is_refused_when_stale_and_calculates_when_rebased(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        exchange_id = await _electricity_bottle(client, bottle)
        made = (
            await client.call_tool(
                "create_scenario",
                {
                    "product_system_id": bottle,
                    "name": "half",
                    "overrides": [
                        {"kind": "exchange", "exchange_id": exchange_id, "multiplier": 0.5}
                    ],
                },
            )
        ).structured_content
        assert made["value"]["name"] == "half" and len(made["value"]["base_hash"]) == 64
        args = {"product_system_id": bottle, "method_id": GWP_ID, "variants": ["half"]}
        out = (await client.call_tool("calculate_impact", args)).structured_content["value"]
        assert out["variants"][0]["scores"][0]["value"] == pytest.approx(1.0)

        await client.call_tool(
            "set_parameters",
            {"product_system_id": bottle, "parameters": [{"name": "elec_kwh", "value": 4.0}]},
        )
        stale = await _error(client, "calculate_impact", args)
        assert stale["error"] == "invalid" and "rebase_scenario" in stale["message"]

        rebased = (
            await client.call_tool("rebase_scenario", {"product_system_id": bottle, "name": "half"})
        ).structured_content
        assert rebased["value"]["base_hash"] != made["value"]["base_hash"]
        out = (await client.call_tool("calculate_impact", args)).structured_content["value"]
        assert out["variants"][0]["scores"][0]["value"] == pytest.approx(2.0)

        blocked = await _error(
            client, "delete_exchange", {"product_system_id": bottle, "exchange_id": exchange_id}
        )
        assert blocked["error"] == "invalid"
        deleted = (
            await client.call_tool("delete_scenario", {"product_system_id": bottle, "name": "half"})
        ).structured_content
        assert deleted["value"] == "half" and deleted["open_requests"] == 0
        entry = deleted["entry"]
        assert entry["changes"] == [
            {
                "op": "delete",
                "entity": "scenario",
                "id": "half",
                "field": None,
                "before": None,
                "after": None,
            }
        ]
        gone = await _error(
            client, "rebase_scenario", {"product_system_id": bottle, "name": "half"}
        )
        assert gone["error"] == "not_found"


async def test_get_parameters_answers_the_space_and_the_matrix(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [{"name": "transport_km", "value": 120.0, "unit": "km"}],
                "cases": [{"name": "lean", "values": {"transport_km": 80.0}}],
            },
        )
        out = await client.call_tool("get_parameters", {"product_system_id": bottle})
    space = out.structured_content["value"]
    assert [p["name"] for p in space["parameters"]] == ["transport_km"]
    assert [c["name"] for c in space["cases"]] == ["lean"]
    assert space["matrix"]["cases"] == ["lean"]
    assert space["matrix"]["rows"] == [{"parameter": "transport_km", "values": [80.0]}]


async def test_set_parameters_answers_the_matrix_too(full_server: FastMCP, bottle: str) -> None:
    async with Client(full_server) as client:
        out = await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [{"name": "yield_factor", "value": 0.9}],
                "cases": [{"name": "high", "values": {"yield_factor": 0.95}}],
            },
        )
    assert out.structured_content["value"]["matrix"]["cases"] == ["high"]


async def test_get_parameters_answers_a_past_version_when_given_its_hash(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        first = await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [{"name": "transport_km", "value": 120.0, "unit": "km"}],
                "cases": [{"name": "lean", "values": {"transport_km": 80.0}}],
            },
        )
        at = first.structured_content["entry"]["result_hash"]
        await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [{"name": "transport_km", "value": 500.0, "unit": "km"}],
            },
        )
        now = await client.call_tool("get_parameters", {"product_system_id": bottle})
        then = await client.call_tool(
            "get_parameters", {"product_system_id": bottle, "content_hash": at}
        )
    assert now.structured_content["value"]["parameters"][0]["value"] == 500.0
    assert then.structured_content["value"]["parameters"][0]["value"] == 120.0
    assert then.structured_content["value"]["matrix"]["rows"] == [
        {"parameter": "transport_km", "values": [80.0]}
    ]


async def test_get_parameters_refuses_a_hash_the_system_never_had(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        refused = await _error(
            client,
            "get_parameters",
            {"product_system_id": bottle, "content_hash": "0" * 64},
        )
    assert refused["error"] == "not_found"


async def test_a_scenario_that_zeroes_a_production_amount_is_refused_by_the_tool(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        await _electricity_bottle(client, bottle)
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": bottle})
        ).structured_content["value"]
        production = next(
            e for e in whole["processes"][0]["exchanges"] if e["type"] == "production"
        )
        refused = await _error(
            client,
            "create_scenario",
            {
                "product_system_id": bottle,
                "name": "empty",
                "overrides": [
                    {"kind": "exchange", "exchange_id": production["id"], "multiplier": 0}
                ],
            },
        )
        assert refused["error"] == "invalid" and "bottle" in refused["message"]


async def test_get_parameters_answers_each_derived_parameter_with_its_value(
    full_server: FastMCP, bottle: str
) -> None:
    async with Client(full_server) as client:
        await client.call_tool(
            "set_parameters",
            {
                "product_system_id": bottle,
                "parameters": [
                    {"name": "mass", "value": 0.2},
                    {"name": "waste", "value": 0.1},
                    {"name": "supplied", "formula": "mass * (1 + waste)"},
                ],
            },
        )
        space = await client.call_tool("get_parameters", {"product_system_id": bottle})
    values = space.structured_content["value"]["values"]
    # 0.2 × 1.1
    assert values["supplied"] == pytest.approx(0.22)
    assert values["mass"] == 0.2
