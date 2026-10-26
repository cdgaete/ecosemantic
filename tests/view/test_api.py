from __future__ import annotations

import dataclasses
import json
import time
import uuid
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import (
    Case,
    DemandItem,
    ExchangeOverride,
    Method,
    Parameter,
    ProductSystem,
    Scenario,
    method_id,
)
from ecosemantic.model.refs import ElementaryFlowRef
from ecosemantic.ports.types import InventoryRow, System
from ecosemantic.view.api import call_tool
from ecosemantic.view.app import build_view
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DB, FLOW_IDS, GWP

GWP_ID = method_id(" > ".join(GWP))
NOWHERE = Path("/nonexistent-static")


@pytest.fixture(scope="module")
def client(context: ServerContext, full_server: FastMCP) -> Iterator[TestClient]:
    with TestClient(build_view(context, full_server, static=NOWHERE)) as client:
        yield client


def test_an_unbuilt_page_says_so(client: TestClient) -> None:
    response = client.get("/systems/anything")
    assert response.status_code == 200 and "not built" in response.text


def test_list_get_log_and_versions(
    client: TestClient, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    listed = client.get("/api/product-systems").json()["value"]
    assert system_id in [card["id"] for card in listed]
    read = client.get(f"/api/product-systems/{system_id}").json()
    assert read["value"]["id"] == system_id and read["open_requests"] == 0
    log = client.get(f"/api/product-systems/{system_id}/log").json()["value"]
    assert log[0]["seq"] == 1
    version = client.get(f"/api/product-systems/{system_id}/versions/{log[-1]['result_hash']}")
    assert version.status_code == 200 and version.json()["id"] == system_id
    missing = client.get(f"/api/product-systems/{system_id}/versions/{'0' * 64}")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"


def test_a_tool_error_keeps_its_envelope(client: TestClient) -> None:
    response = client.get(f"/api/product-systems/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found" and "message" in response.json()
    bad = client.get("/api/product-systems/not-a-uuid")
    assert bad.status_code == 400 and bad.json()["error"] == "invalid"


def test_discovery_routes(client: TestClient) -> None:
    databases = client.get("/api/databases").json()["value"]
    assert FIXTURE_DB in [d["name"] for d in databases]
    units = client.get(f"/api/databases/{FIXTURE_DB}/vocabulary/units").json()["value"]
    assert units
    hits = client.get(
        f"/api/databases/{FIXTURE_DB}/processes", params={"query": "steel", "limit": "5"}
    ).json()
    assert hits["items"] and len(hits["items"]) <= 5
    ref = hits["items"][0]["ref"]["id"]
    process = client.get(f"/api/databases/{FIXTURE_DB}/processes/{ref}").json()["value"]
    assert process["exchanges"] is not None
    methods = client.get(f"/api/databases/{FIXTURE_DB}/methods", params={"query": "GWP"}).json()
    assert methods["items"]


def test_calculation_routes(client: TestClient, fixture_system_stored: ProductSystem) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    impact = client.post(f"{base}/impact", json={"method_id": GWP_ID}).json()["value"]
    assert impact["scores"][0]["value"] > 0
    contributions = client.post(
        f"{base}/contributions", json={"method_id": GWP_ID, "by": "process", "top_n": 3}
    ).json()["value"]
    assert contributions["by"] == "process" and len(contributions["processes"]) <= 3
    inventory = client.post(f"{base}/inventory", json={"limit": 10}).json()
    assert inventory["items"] and len(inventory["items"]) <= 10
    validation = client.get(f"{base}/validation").json()["value"]
    assert "is_valid" in validation


def test_a_malformed_body_answers_the_error_envelope(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    not_json = client.post(
        f"{base}/impact", content=b"not json", headers={"content-type": "application/json"}
    )
    assert not_json.status_code == 400 and not_json.json()["error"] == "invalid"
    not_an_object = client.post(f"{base}/requests", json=["a", "b"])
    assert not_an_object.status_code == 400 and not_an_object.json()["error"] == "invalid"


def test_requests_are_posted_and_listed(
    client: TestClient, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    current = client.get(base).json()["value"]["hash"]
    posted = client.post(
        f"{base}/requests",
        json={"actor": "Carlos", "kind": "return", "at_hash": current, "message": "too heavy"},
    )
    assert posted.status_code == 201 and posted.json()["seq"] >= 1
    listed = client.get(f"{base}/requests").json()["value"]
    assert posted.json()["id"] in [r["id"] for r in listed]
    assert next(r for r in listed if r["id"] == posted.json()["id"])["open"] is True
    assert posted.json()["open"] is True
    assert client.get(base).json()["open_requests"] >= 1
    rejected = client.post(
        f"{base}/requests",
        json={"actor": "Carlos", "kind": "edit", "at_hash": current, "message": "x"},
    )
    assert rejected.status_code == 400 and rejected.json()["error"] == "invalid"
    open_only = client.get(f"{base}/requests", params={"open_only": "true"}).json()["value"]
    assert [r["id"] for r in open_only] == [posted.json()["id"]]


def test_an_unmatched_api_path_answers_a_json_404(client: TestClient) -> None:
    missing = client.get("/api/nothing")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"
    posted = client.post("/api/product-systems/not-a-route")
    assert posted.status_code == 404 and posted.json()["error"] == "not_found"
    assert client.get("/systems/anything").status_code == 200


def test_the_token_gates_the_api_and_not_the_page(
    context: ServerContext, full_server: FastMCP
) -> None:
    with TestClient(build_view(context, full_server, token="secret", static=NOWHERE)) as client:
        assert client.get("/api/product-systems").status_code == 401
        assert client.get("/api/product-systems", params={"token": "wrong"}).status_code == 401
        assert client.get("/api/product-systems", params={"token": "secret"}).status_code == 200
        assert client.get("/").status_code == 200


def test_an_elementary_flow_is_answered_with_its_side(client: TestClient) -> None:
    flow_id = FLOW_IDS["water_in"]
    flow = client.get(f"/api/databases/{FIXTURE_BIO}/elementary-flows/{flow_id}").json()
    assert flow["value"]["name"] == "Water, river" and flow["value"]["side"] == "input"
    missing = client.get(f"/api/databases/{FIXTURE_BIO}/elementary-flows/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"


class RefusingCalculation:
    async def inventory(self, system: System, demand: list[DemandItem]) -> list[InventoryRow]:
        ref = ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"])
        return [
            InventoryRow(
                flow=ref,
                name="Unplaced",
                compartment="economic",
                sub_compartment="waste",
                flow_type="economic",
                unit="kilogram",
                amount=1.0,
            )
        ]


def test_an_inventory_row_with_a_refused_pair_answers_not_supported(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    refusing = dataclasses.replace(context, calculation=RefusingCalculation())
    with TestClient(build_view(refusing, build_server(refusing), static=NOWHERE)) as client:
        base = f"/api/product-systems/{fixture_system_stored.id}"
        response = client.post(f"{base}/inventory", json={"limit": 10})
    assert response.status_code == 501 and response.json()["error"] == "not_supported"


def test_the_parameters_route_answers_the_space_and_a_past_version(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    now = client.get(f"/api/product-systems/{system_id}/parameters")
    assert now.status_code == 200
    space = now.json()["value"]
    assert [p["name"] for p in space["parameters"]] == [
        p.name for p in fixture_system_stored.parameters
    ]
    assert space["matrix"]["cases"] == [c.name for c in fixture_system_stored.cases]
    log = client.get(f"/api/product-systems/{system_id}/log").json()["value"]
    at = client.get(f"/api/product-systems/{system_id}/parameters?hash={log[0]['result_hash']}")
    assert at.status_code == 200 and "matrix" in at.json()["value"]
    missing = client.get(f"/api/product-systems/{system_id}/parameters?hash={'0' * 64}")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"


def settled(client: TestClient, run_id: str, seconds: float = 120) -> dict[str, object]:
    """The run once it is no longer open, or an assertion failure when it never settles."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()["value"]
        if not run["open"]:
            return run
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} never settled")


def test_a_run_started_through_the_route_is_listed_and_reaches_done(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    started = client.post(
        f"{base}/runs", json={"method_id": GWP_ID, "monte_carlo": {"n": 2, "n_min": 1, "seed": 1}}
    )
    assert started.status_code == 200
    run = started.json()["value"]
    assert settled(client, run["id"])["status"] == "done"
    assert client.get(f"{base}/runs").json()["value"][0]["id"] == run["id"]


def test_a_second_start_names_the_first_and_a_cancel_settles_it(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    base = f"/api/product-systems/{fixture_system_stored.id}"
    # enough samples that the first run is still open when the cancel arrives
    first = client.post(
        f"{base}/runs",
        json={"method_id": GWP_ID, "monte_carlo": {"n": 1000, "n_min": 1, "seed": 1}},
    ).json()["value"]
    refused = client.post(
        f"{base}/runs", json={"method_id": GWP_ID, "monte_carlo": {"n": 2, "n_min": 1, "seed": 2}}
    )
    assert refused.status_code == 409 and refused.json()["error"] == "conflict"
    assert refused.json()["details"] == {
        "run_id": first["id"],
        "product_system_id": str(fixture_system_stored.id),
    }
    asked = client.post(f"/api/runs/{first['id']}/cancel")
    assert asked.status_code == 200 and asked.json()["value"]["cancel_requested"] is True
    assert settled(client, first["id"])["status"] == "cancelled"


def test_an_unknown_run_is_not_found(client: TestClient) -> None:
    unknown = uuid.uuid4()
    response = client.get(f"/api/runs/{unknown}")
    assert response.status_code == 404 and response.json()["message"] == f"no run {unknown}"


async def test_a_tool_that_fails_its_own_validation_answers_an_envelope() -> None:
    server = FastMCP("probe")

    @server.tool(name="broken")
    def broken() -> str:
        Method.model_validate({})
        return "unreachable"

    response = await call_tool(server, "broken", {})
    assert response.status_code == 400
    assert json.loads(bytes(response.body))["error"] == "invalid"


async def test_the_layout_answers_the_arrangement_and_keeps_what_is_posted(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system_id = fixture_system_stored.id
    code = fixture_system_stored.processes[0].code
    with TestClient(build_view(context, full_server, static=NOWHERE)) as client:
        first = client.get(f"/api/product-systems/{system_id}/layout").json()["value"]
        # the arrangement graph_layout answers an agent
        assert set(first) == {"map", "cards", "edges", "troubles", "score", "bounds", "scaling"}
        cards = first["cards"]
        assert {p["code"] for p in cards} == {p.code for p in fixture_system_stored.processes}
        assert not any(p["held"] for p in cards)
        posted = client.post(
            f"/api/product-systems/{system_id}/layout",
            json={"placements": [{"code": code, "x": 11.0, "y": 22.0}]},
        )
        assert posted.status_code == 200
        held = {p["code"]: p for p in posted.json()["value"]["cards"]}
        assert (held[code]["x"], held[code]["y"], held[code]["held"]) == (11.0, 22.0, True)
        released = client.delete(f"/api/product-systems/{system_id}/layout").json()["value"]
        assert not any(p["held"] for p in released["cards"])


async def test_a_malformed_placement_answers_the_invalid_envelope(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system_id = fixture_system_stored.id
    with TestClient(
        build_view(context, full_server, static=NOWHERE), raise_server_exceptions=False
    ) as client:
        for bad in (
            [{"code": "frame", "y": 1.0}],
            [{"code": "frame", "x": "wide", "y": 1.0}],
            [{"x": 1.0, "y": 2.0}],
            [{"code": 7, "x": 1.0, "y": 2.0}],
        ):
            response = client.post(
                f"/api/product-systems/{system_id}/layout", json={"placements": bad}
            )
            assert response.status_code == 400
            assert response.json()["error"] == "invalid"


async def test_the_document_as_a_variant_is_resolved(
    client: TestClient, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "as-variant")
    system.name = "widget_as_variant"
    electricity = system.process("widget").exchanges[2]
    electricity.formula = "elec_kwh"
    system.parameters = [Parameter(name="elec_kwh", value=1.0)]
    system.cases = [Case(name="half", values={"elec_kwh": 0.5})]
    system.scenarios = [
        Scenario(
            name="stale",
            overrides=[ExchangeOverride(exchange_id=electricity.id, multiplier=2.0)],
            base_hash="0" * 64,
        )
    ]
    await context.storage.put_product_system(system, context.actor, "created")
    base = f"/api/product-systems/{system.id}"
    half = client.get(f"{base}?variant=half").json()["value"]
    amounts = {e["id"]: e["amount"] for p in half["processes"] for e in p["exchanges"]}
    assert amounts[str(electricity.id)] == 0.5
    whole = client.get(base).json()["value"]
    stored = {e["id"]: e["amount"] for p in whole["processes"] for e in p["exchanges"]}
    assert stored[str(electricity.id)] == 1.0
    missing = client.get(f"{base}?variant=nothing")
    assert missing.status_code == 404
    stale = client.get(f"{base}?variant=stale")
    assert stale.status_code == 400 and "rebase_scenario" in stale.json()["message"]


async def test_the_layout_is_drawn_read_posted_and_released_under_the_variant_named(
    context: ServerContext, full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "layout-variant")
    frame = next(e for e in system.process("widget").exchanges if e.name == "frame")
    frame.formula = "frame_mass"
    system.parameters = [Parameter(name="frame_mass", value=0.25)]
    system.cases = [Case(name="heavy frame", values={"frame_mass": 0.5})]
    await context.storage.put_product_system(system, context.actor, "created")
    base = f"/api/product-systems/{system.id}/layout"

    def frame_activity(answer: dict[str, object]) -> float:
        value = answer["value"]
        assert isinstance(value, dict)
        return next(c["activity"] for c in value["cards"] if c["code"] == "frame")

    def label(answer: dict[str, object]) -> str:
        value = answer["value"]
        assert isinstance(value, dict)
        [edge] = value["edges"]
        return edge["label"]["per_unit"]

    with TestClient(build_view(context, full_server, static=NOWHERE)) as client:
        plain = client.get(base).json()
        heavy = client.get(base, params={"variant": "heavy frame"}).json()
        assert frame_activity(plain) == pytest.approx(0.25) and label(plain) == "0.25 kg"
        assert frame_activity(heavy) == pytest.approx(0.5) and label(heavy) == "0.5 kg"
        posted = client.post(
            base,
            json={"placements": [{"code": "frame", "x": 1.0, "y": 2.0}], "variant": "heavy frame"},
        ).json()
        assert frame_activity(posted) == pytest.approx(0.5)
        released = client.delete(base, params={"variant": "heavy frame"}).json()
        assert frame_activity(released) == pytest.approx(0.5)
        assert client.get(base, params={"variant": "nothing"}).status_code == 404


async def test_the_server_route_names_the_client_and_the_directories(
    context: ServerContext,
) -> None:
    introduced = dataclasses.replace(context, client={"name": "Claude Desktop", "version": "0.9"})
    with TestClient(build_view(introduced, build_server(introduced), static=NOWHERE)) as client:
        answered = client.get("/api/server")
    assert answered.status_code == 200, answered.text
    assert answered.json() == {
        "client": {"name": "Claude Desktop", "version": "0.9"},
        "version": version("ecosemantic"),
        "data_dir": str(context.data_dir),
        "systems_dir": str(context.systems_dir),
    }
    with TestClient(build_view(context, build_server(context), static=NOWHERE)) as client:
        assert client.get("/api/server").json()["client"] is None
