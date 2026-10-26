from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.model.entities import method_id
from ecosemantic.package.log import verify_chain
from ecosemantic.ports.types import LogEntry
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS, GWP

GWP_ID = method_id(" > ".join(GWP))


def _background(key: str) -> dict[str, str]:
    return {"kind": "background", "database": FIXTURE_DB, "id": CODES[key]}


async def _build_widget(client: Client) -> str:
    """The fixture's widget and frame, the widget its reference, through the tools alone; returns
    the product system id."""
    made = await client.call_tool(
        "create_product_system", {"name": "widget", "database": FIXTURE_DB}
    )
    system_id = made.structured_content["value"]["id"]
    for code, unit, product in (("widget", "unit", "widget"), ("frame", "kilogram", "frame")):
        await client.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": code,
                "name": f"{code} production",
                "unit": unit,
                "reference_product": product,
            },
        )
    await client.call_tool(
        "update_product_system", {"product_system_id": system_id, "reference_process": "widget"}
    )
    exchanges = [
        ("widget", "product", 0.5, _background("steel")),
        ("widget", "product", 1.0, _background("elec")),
        ("widget", "product", 0.25, {"kind": "foreground", "code": "frame"}),
        (
            "widget",
            "elementary",
            0.1,
            {"kind": "elementary_flow", "database": FIXTURE_BIO, "id": FLOW_IDS["co2"]},
        ),
        ("frame", "product", 2.4, _background("steel")),
    ]
    for process, type_, amount, input_ in exchanges:
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": process,
                "type": type_,
                "amount": amount,
                "input": input_,
            },
        )
    return system_id


async def _score(client: Client, system_id: str) -> float:
    out = await client.call_tool(
        "calculate_impact", {"product_system_id": system_id, "method_id": GWP_ID}
    )
    return out.structured_content["value"]["scores"][0]["value"]


async def test_the_widget_built_from_nothing_scores_the_fixture(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        system_id = await _build_widget(client)
        # the fixture's widget: 4.158 kg CO2-Eq
        assert await _score(client, system_id) == pytest.approx(4.158)
        report = (
            await client.call_tool("validate_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        assert report["is_valid"] is True and report["target"] == "widget"
        log = (
            await client.call_tool("get_product_system_log", {"product_system_id": system_id})
        ).structured_content["items"]
        verify_chain([LogEntry.model_validate(e) for e in log])
        assert [e["seq"] for e in log] == list(range(1, 10))


async def test_an_export_survives_deletion_and_import(full_server: FastMCP, tmp_path: Path) -> None:
    async with Client(full_server) as client:
        system_id = await _build_widget(client)
        zipped = tmp_path / "widget.zip"
        await client.call_tool(
            "export_product_system", {"product_system_id": system_id, "path": str(zipped)}
        )
        await client.call_tool("delete_product_system", {"product_system_id": system_id})
        back = (
            await client.call_tool("import_product_system", {"path": str(zipped)})
        ).structured_content
        assert back["value"]["id"] == system_id
        assert await _score(client, system_id) == pytest.approx(4.158)


async def test_a_delete_that_would_dangle_names_the_consumer(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        system_id = await _build_widget(client)
        with pytest.raises(ToolError, match="widget"):
            await client.call_tool(
                "delete_process", {"product_system_id": system_id, "code": "frame"}
            )


async def test_parallel_writes_both_persist(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        system_id = await _build_widget(client)
        whole = (
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        widget = next(p for p in whole["processes"] if p["code"] == "widget")
        steel, elec = widget["exchanges"][1]["id"], widget["exchanges"][2]["id"]
        first, second = await asyncio.gather(
            client.call_tool(
                "update_exchange",
                {"product_system_id": system_id, "exchange_id": steel, "amount": 1.0},
            ),
            client.call_tool(
                "update_exchange",
                {"product_system_id": system_id, "exchange_id": elec, "amount": 2.0},
            ),
        )
        seqs = sorted(r.structured_content["entry"]["seq"] for r in (first, second))
        assert seqs == [10, 11]
        stored = (
            await client.call_tool("get_product_system", {"product_system_id": system_id})
        ).structured_content["value"]
        amounts = {e["id"]: e["amount"] for p in stored["processes"] for e in p["exchanges"]}
        assert amounts[steel] == 1.0 and amounts[elec] == 2.0


async def _build_wall(client: Client) -> str:
    """A system the size of the worked wall: 41 parameters, four processes and eighteen formula
    exchanges written one call each; returns the product system id."""
    made = await client.call_tool("create_product_system", {"name": "wall", "database": FIXTURE_DB})
    system_id = made.structured_content["value"]["id"]
    await client.call_tool(
        "set_parameters",
        {
            "product_system_id": system_id,
            "parameters": [
                {"name": f"p{n:02d}", "value": 1.0 + n, "unit": "kg", "description": f"input {n}"}
                for n in range(41)
            ],
        },
    )
    for code in ("mortar", "boiler", "pump", "wall"):
        await client.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": code,
                "name": f"{code} module",
                "unit": "unit",
                "reference_product": code,
                "metadata": {"life_cycle_stage": "A1-A3", "supply_chain_tier": 1},
            },
        )
    for n in range(18):
        code = ("mortar", "boiler", "pump", "wall")[n % 4]
        await client.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": code,
                "type": "product",
                "formula": f"p{n:02d}",
                "input": _background(("steel", "elec")[n % 2]),
            },
        )
    return system_id


async def test_a_write_answer_carries_its_entity_once_and_the_reads_stay_bounded(
    full_server: FastMCP,
) -> None:
    bound = 25_000
    async with Client(full_server) as client:
        system_id = await _build_wall(client)
        created = await client.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": "extra",
                "name": "extra module",
                "unit": "unit",
                "reference_product": "extra",
            },
        )
        whole = await client.call_tool("get_product_system", {"product_system_id": system_id})
        log = await client.call_tool("get_product_system_log", {"product_system_id": system_id})
    answer = created.structured_content
    assert all(change["after"] is None for change in answer["entry"]["changes"])
    header = {k: v for k, v in answer["entry"].items() if k != "changes"}
    assert (
        len(json.dumps(answer))
        <= len(json.dumps(answer["value"]))
        + len(json.dumps(header))
        + len(json.dumps(answer["entry"]["changes"]))
        + len(json.dumps(answer["consequences"]))
        + 200
    )
    assert len(json.dumps(whole.structured_content)) < bound
    page = log.structured_content
    assert len(json.dumps(page)) < bound
    assert page["has_more"] and [e["seq"] for e in page["items"]] == list(range(1, 11))


async def test_a_log_entry_for_an_exchange_names_the_flow_and_its_process(
    full_server: FastMCP,
) -> None:
    async with Client(full_server) as client:
        system_id = await _build_widget(client)
        whole = await client.call_tool("get_product_system", {"product_system_id": system_id})
        widget = next(
            p for p in whole.structured_content["value"]["processes"] if p["code"] == "widget"
        )
        exchange = next(e for e in widget["exchanges"] if e["type"] == "product")
        updated = await client.call_tool(
            "update_exchange",
            {"product_system_id": system_id, "exchange_id": exchange["id"], "comment": "checked"},
        )
        deleted = await client.call_tool(
            "delete_exchange", {"product_system_id": system_id, "exchange_id": exchange["id"]}
        )
    named = f"{exchange['name']} ({widget['name']}) {exchange['id']}"
    assert updated.structured_content["entry"]["message"] == f"updated exchange {named}"
    assert deleted.structured_content["entry"]["message"] == f"deleted exchange {named}"
