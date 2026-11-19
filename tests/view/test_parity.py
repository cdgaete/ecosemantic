"""Every /api route answers what the tool it calls answers, and no page route opens an MCP
session."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import JsonValue
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient

from ecosemantic.errors import error_status
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import envelope_of
from ecosemantic.view.app import build_view
from tests.fixture_data import CODES, FIXTURE_DB, FLOW_IDS
from tests.view.test_page_fixtures import shape

NOWHERE = Path("/nonexistent-static")
UNKNOWN = uuid.UUID("00000000-0000-4000-8000-000000000000")
ABSENT = uuid.UUID("00000000-0000-4000-8000-000000000001")


@dataclass(frozen=True)
class Refusal:
    """A request whose argument the tool refuses, and the arguments it sends the tool."""

    path: str
    arguments: dict[str, JsonValue]
    body: dict[str, JsonValue] | None = None


@dataclass(frozen=True)
class Row:
    """One route held to the tool it calls: the request it sends, and the tool call it makes. A
    rerun row names no tool of its own: it calls the one the recorded agent call records."""

    method: str
    template: str
    path: str
    tool: str
    arguments: dict[str, JsonValue]
    body: dict[str, JsonValue] | None = None
    write: bool = False
    log: bool = False
    rerun: bool = False
    refused: Refusal | None = None
    unknown: bool = False


@dataclass(frozen=True)
class Planted:
    """What the rows name: the cup, its method, one run, one install and one agent call."""

    ids: dict[str, str]
    absent: dict[str, str]
    recorded: tuple[str, dict[str, JsonValue]]


PARITY: tuple[Row, ...] = (
    Row(
        "GET",
        "/api/databases/{name}/vocabulary/{kind}",
        "/api/databases/$db/vocabulary/units",
        "list_vocabulary",
        {"database": "$db", "kind": "units"},
        refused=Refusal(
            "/api/databases/$db/vocabulary/nonsense",
            {"database": "$db", "kind": "nonsense"},
        ),
    ),
    Row(
        "GET",
        "/api/databases/{name}/processes",
        "/api/databases/$db/processes?query=steel&limit=5",
        "search_processes",
        {"database": "$db", "query": "steel", "limit": "5"},
        refused=Refusal(
            "/api/databases/$db/processes?query=steel&limit=x",
            {"database": "$db", "query": "steel", "limit": "x"},
        ),
    ),
    Row(
        "GET",
        "/api/databases/{name}/elementary-flows",
        "/api/databases/$db/elementary-flows?query=carbon",
        "search_elementary_flows",
        {"database": "$db", "query": "carbon"},
        refused=Refusal(
            "/api/databases/$db/elementary-flows?query=carbon&limit=x",
            {"database": "$db", "query": "carbon", "limit": "x"},
        ),
    ),
    Row(
        "GET",
        "/api/databases/{name}/methods",
        "/api/databases/$db/methods?query=climate",
        "search_methods",
        {"database": "$db", "query": "climate"},
        refused=Refusal(
            "/api/databases/$db/methods?query=climate&limit=x",
            {"database": "$db", "query": "climate", "limit": "x"},
        ),
    ),
    Row(
        "GET",
        "/api/databases/{name}/processes/{ref}",
        "/api/databases/$db/processes/$process",
        "get_background_process",
        {"database": "$db", "process_id": "$process", "exchanges": True},
        unknown=True,
    ),
    Row(
        "GET",
        "/api/databases/{name}/elementary-flows/{ref}",
        "/api/databases/$db/elementary-flows/$flow",
        "get_elementary_flow",
        {"database": "$db", "flow_id": "$flow"},
        unknown=True,
    ),
    Row("GET", "/api/product-systems", "/api/product-systems", "list_product_systems", {}),
    Row(
        "GET",
        "/api/product-systems/{id}",
        "/api/product-systems/$system",
        "get_product_system",
        {"product_system_id": "$system", "variant": None},
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/parameters",
        "/api/product-systems/$system/parameters",
        "get_parameters",
        {"product_system_id": "$system", "content_hash": None},
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/log",
        "/api/product-systems/$system/log",
        "get_product_system_log",
        {"product_system_id": "$system", "cursor": None},
        log=True,
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/validation",
        "/api/product-systems/$system/validation",
        "validate_product_system",
        {"product_system_id": "$system"},
        unknown=True,
    ),
    Row(
        "POST",
        "/api/product-systems/{id}/impact",
        "/api/product-systems/$system/impact",
        "calculate_impact",
        {"product_system_id": "$system", "method_id": "$method", "samples": True},
        body={"method_id": "$method"},
        refused=Refusal(
            "/api/product-systems/$system/impact",
            {"product_system_id": "$system", "method_id": 5, "samples": True},
            {"method_id": 5},
        ),
        unknown=True,
    ),
    Row(
        "POST",
        "/api/product-systems/{id}/contributions",
        "/api/product-systems/$system/contributions",
        "contribution_analysis",
        {"product_system_id": "$system", "method_id": "$method", "by": "process"},
        body={"method_id": "$method", "by": "process"},
        refused=Refusal(
            "/api/product-systems/$system/contributions",
            {"product_system_id": "$system", "method_id": "$method", "by": "nowhere"},
            {"method_id": "$method", "by": "nowhere"},
        ),
        unknown=True,
    ),
    Row(
        "POST",
        "/api/product-systems/{id}/inventory",
        "/api/product-systems/$system/inventory",
        "calculate_inventory",
        {"product_system_id": "$system"},
        body={},
        refused=Refusal(
            "/api/product-systems/$system/inventory",
            {"product_system_id": "$system", "limit": "x"},
            {"limit": "x"},
        ),
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/runs",
        "/api/product-systems/$system/runs",
        "list_runs",
        {"product_system_id": "$system"},
        unknown=True,
    ),
    Row(
        "POST",
        "/api/product-systems/{id}/runs",
        "/api/product-systems/$system/runs",
        "start_monte_carlo",
        {
            "product_system_id": "$system",
            "method_id": "$method",
            "monte_carlo": {"n": 4, "seed": 1},
        },
        body={"method_id": "$method", "monte_carlo": {"n": 4, "seed": 1}},
        write=True,
        refused=Refusal(
            "/api/product-systems/$system/runs",
            {"product_system_id": "$system", "method_id": 5, "monte_carlo": {"n": 4, "seed": 1}},
            {"method_id": 5, "monte_carlo": {"n": 4, "seed": 1}},
        ),
        unknown=True,
    ),
    Row(
        "GET",
        "/api/runs/{run_id}",
        "/api/runs/$run",
        "get_run",
        {"run_id": "$run", "samples": True},
        unknown=True,
    ),
    Row(
        "POST",
        "/api/runs/{run_id}/cancel",
        "/api/runs/$run/cancel",
        "cancel_run",
        {"run_id": "$run"},
        write=True,
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/requests",
        "/api/product-systems/$system/requests",
        "list_requests",
        {"product_system_id": "$system", "open_only": False},
        unknown=True,
    ),
    Row(
        "GET",
        "/api/product-systems/{id}/layout",
        "/api/product-systems/$system/layout",
        "graph_layout",
        {"product_system_id": "$system", "variant": None},
        unknown=True,
    ),
    Row(
        "POST",
        "/api/product-systems/{id}/layout",
        "/api/product-systems/$system/layout",
        "arrange_graph",
        {"product_system_id": "$system", "placements": [{"code": "cup", "x": 1.0, "y": 2.0}]},
        body={"placements": [{"code": "cup", "x": 1.0, "y": 2.0}]},
        write=True,
        refused=Refusal(
            "/api/product-systems/$system/layout",
            {"product_system_id": "$system", "placements": "x"},
            {"placements": "x"},
        ),
        unknown=True,
    ),
    Row(
        "DELETE",
        "/api/product-systems/{id}/layout",
        "/api/product-systems/$system/layout",
        "arrange_graph",
        {"product_system_id": "$system", "placements": [], "release_all": True, "variant": None},
        write=True,
        unknown=True,
    ),
    Row("GET", "/api/sources", "/api/sources", "list_sources", {}),
    Row(
        "POST",
        "/api/installs",
        "/api/installs",
        "install_database",
        {"source": "uslci"},
        body={"source": "uslci"},
        write=True,
        refused=Refusal("/api/installs", {"source": "nowhere"}, {"source": "nowhere"}),
    ),
    Row("GET", "/api/installs", "/api/installs", "list_installs", {}),
    Row(
        "GET",
        "/api/installs/{id}",
        "/api/installs/$install",
        "get_install",
        {"install_id": "$install"},
        unknown=True,
    ),
    Row(
        "POST",
        "/api/installs/{id}/cancel",
        "/api/installs/$install/cancel",
        "cancel_install",
        {"install_id": "$install"},
        write=True,
        unknown=True,
    ),
    Row(
        "POST",
        "/api/activity/{call_id}/rerun",
        "/api/activity/$call/rerun",
        "",
        {},
        rerun=True,
    ),
)

PORT_READS: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/server"),
        ("GET", "/api/monte-carlo"),
        ("GET", "/api/product-systems/{id}/versions/{hash}"),
        ("GET", "/api/product-systems/{id}/anchors"),
        ("POST", "/api/product-systems/{id}/requests"),
        ("GET", "/api/agents"),
        ("GET", "/api/agents/{agent}/trail"),
        ("GET", "/api/activity"),
        ("GET", "/api/product-systems/{id}/log/{seq:int}/trail"),
        ("GET", "/api/product-systems/{id}/calculations"),
        ("GET", "/api/events"),
        ("GET", "/api/product-systems/{id}/events"),
        ("GET", "/api/product-systems/{id}/package.zip"),
        ("POST", "/api/product-systems/{id}/return"),
        ("GET", "/api/credentials"),
        ("GET", "/api/credentials/entry"),
        ("PUT", "/api/credentials/{kind}"),
        ("DELETE", "/api/credentials/{kind}"),
        ("GET", "/api/databases"),
        ("GET", "/api/databases/{name}/summary"),
        ("GET", "/api/databases/{name}/classifications"),
        ("GET", "/api/databases/{name}/classifications/{scheme}"),
        ("GET", "/api/databases/{name}/classifications/{scheme}/processes"),
        ("GET", "/api/databases/{name}/compartments"),
        ("GET", "/api/databases/{name}/compartments/{compartment}/flows"),
        ("GET", "/api/databases/{name}/impact-methods"),
        ("GET", "/api/databases/{name}/impact-methods/{id}/factors"),
        ("POST", "/api/databases/{name}/elementary-flows/read"),
        ("GET", "/api/home"),
        ("POST", "/api/installs/openlca"),
        ("GET", "/api/installs/{id}/licence"),
        ("GET", "/api/product-systems/{id}/tables.zip"),
        ("POST", "/api/product-systems/{id}/tables"),
        ("POST", "/api/product-systems/{id}/impact.zip"),
        ("POST", "/api/product-systems/{id}/contributions.zip"),
        ("POST", "/api/product-systems/{id}/inventory.zip"),
        ("GET", "/api/{path:path}"),
        ("POST", "/api/{path:path}"),
        ("PUT", "/api/{path:path}"),
        ("DELETE", "/api/{path:path}"),
        ("PATCH", "/api/{path:path}"),
    }
)


def _filled(value: JsonValue, ids: Mapping[str, str]) -> JsonValue:
    """A templated path, body or argument set with every `$name` replaced by its id."""
    if isinstance(value, str):
        filled = value
        for name, found in ids.items():
            filled = filled.replace(f"${name}", found)
        return filled
    if isinstance(value, dict):
        return {key: _filled(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_filled(item, ids) for item in value]
    return value


def _filled_arguments(
    value: Mapping[str, JsonValue], ids: Mapping[str, str]
) -> dict[str, JsonValue]:
    filled = _filled(dict(value), ids)
    assert isinstance(filled, dict)
    return filled


def _request(
    page: TestClient, method: str, path: str, body: Mapping[str, JsonValue] | None
) -> Response:
    return page.request(method, path, json=None if body is None else dict(body))


async def _joined_log(tools: Client, arguments: Mapping[str, JsonValue]) -> list[JsonValue]:
    """A log tool's pages, read one after the other, joined in order."""
    entries: list[JsonValue] = []
    cursor = arguments["cursor"]
    while True:
        page = await tools.call_tool("get_product_system_log", {**arguments, "cursor": cursor})
        assert page.structured_content is not None
        entries.extend(page.structured_content["items"])
        cursor = page.structured_content["next_cursor"]
        if cursor is None:
            return entries


@pytest.fixture
async def planted(
    ports_only: ServerContext, ports_only_server: FastMCP, cup: tuple[str, str]
) -> Planted:
    """A run posted, an install posted and an agent call recorded, through the MCP path. The
    in-memory launcher starts no worker, so a start over these ports answers unavailable after the
    run is posted, and the run every row names is the one it left."""
    system_id, method_id = cup
    async with Client(ports_only_server) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "start_monte_carlo",
                {
                    "product_system_id": system_id,
                    "method_id": method_id,
                    "monte_carlo": {"n": 4, "seed": 1},
                },
            )
        posted = await client.call_tool("install_database", {"source": "uslci"})
        assert posted.structured_content is not None
        await client.call_tool("get_product_system", {"product_system_id": system_id})
    (run,) = await ports_only.runs.list_runs()
    recorded = [
        call for call in await ports_only.activity.list_calls() if call.tool == "get_product_system"
    ]
    call = recorded[-1]
    ids = {
        "db": FIXTURE_DB,
        "system": system_id,
        "method": method_id,
        "run": str(run.id),
        "install": posted.structured_content["value"]["id"],
        "call": str(call.id),
        "process": CODES["steel"],
        "flow": FLOW_IDS["co2"],
    }
    absent = {
        **ids,
        "system": str(UNKNOWN),
        "run": str(UNKNOWN),
        "install": str(UNKNOWN),
        "call": str(UNKNOWN),
        "process": str(ABSENT),
        "flow": str(ABSENT),
    }
    yield Planted(ids=ids, absent=absent, recorded=(call.tool, call.arguments))
    for task in ports_only.watchers:
        task.cancel()
    await asyncio.gather(*ports_only.watchers, return_exceptions=True)


async def test_a_page_route_opens_no_mcp_session(
    ports_only: ServerContext,
    ports_only_server: FastMCP,
    cup: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_view(ports_only, ports_only_server, static=NOWHERE)
    system_id, _ = cup

    async def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the page opened an MCP session")

    monkeypatch.setattr(Client, "__aenter__", refuse)
    with TestClient(app) as page:
        answered = page.get(f"/api/product-systems/{system_id}")
    assert answered.status_code == 200, answered.text


@pytest.mark.parametrize("row", PARITY, ids=[f"{row.method} {row.template}" for row in PARITY])
async def test_every_route_answers_what_its_tool_answers(
    row: Row,
    planted: Planted,
    ports_only: ServerContext,
    ports_only_server: FastMCP,
) -> None:
    path = _filled(row.path, planted.ids)
    assert isinstance(path, str)
    body = None if row.body is None else _filled_arguments(row.body, planted.ids)
    arguments = _filled_arguments(row.arguments, planted.ids)
    await _compared(row, planted, path, body, arguments, ports_only, ports_only_server)
    for refusal in _variants(row, planted):
        await _compared(
            row,
            planted,
            refusal.path,
            refusal.body,
            refusal.arguments,
            ports_only,
            ports_only_server,
        )


def _variants(row: Row, planted: Planted) -> list[Refusal]:
    """The wrong-argument case a row sends, and the unknown id one it sends."""
    variants: list[Refusal] = []
    if row.refused is not None:
        variants.append(
            Refusal(
                str(_filled(row.refused.path, planted.ids)),
                _filled_arguments(row.refused.arguments, planted.ids),
                None
                if row.refused.body is None
                else _filled_arguments(row.refused.body, planted.ids),
            )
        )
    if row.unknown:
        variants.append(
            Refusal(
                str(_filled(row.path, planted.absent)),
                _filled_arguments(row.arguments, planted.absent),
                None if row.body is None else _filled_arguments(row.body, planted.absent),
            )
        )
    return variants


async def _compared(
    row: Row,
    planted: Planted,
    path: str,
    body: dict[str, JsonValue] | None,
    arguments: dict[str, JsonValue],
    ports_only: ServerContext,
    ports_only_server: FastMCP,
) -> None:
    """The route's answer and the tool's answer to the same request, compared."""
    app = build_view(ports_only, ports_only_server, static=NOWHERE)
    with TestClient(app) as page:
        answered = _request(page, row.method, path, body)
    async with Client(ports_only_server) as tools:
        try:
            if row.rerun:
                name, recorded = planted.recorded
                call = await tools.call_tool(name, recorded)
                assert answered.json()["value"]["result"] == call.structured_content
                return
            if row.log:
                entries = await _joined_log(tools, arguments)
                assert answered.json()["value"] == entries
                return
            call = await tools.call_tool(row.tool, arguments)
        except ToolError as error:
            envelope = envelope_of(error)
            assert answered.status_code == error_status(envelope.error), answered.text
            assert answered.json() == envelope.model_dump(mode="json")
            return
    assert answered.status_code == 200, answered.text
    if row.write:
        assert shape(answered.json()) == shape(call.structured_content)
        return
    assert answered.json() == call.structured_content


def test_every_api_route_is_held_to_its_tool_or_named_a_port_read(
    ports_only: ServerContext, ports_only_server: FastMCP
) -> None:
    app = build_view(ports_only, ports_only_server, static=NOWHERE)
    served = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, Route) and route.path.startswith("/api")
        for method in (route.methods or set()) - {"HEAD"}
    }
    held = {(row.method, row.template) for row in PARITY}
    assert held <= served
    assert served - held - PORT_READS == set()
