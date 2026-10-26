from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from mcp.types import Implementation
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.entities import ProductSystem, method_id
from ecosemantic.view.app import build_view
from tests.fixture_data import FIXTURE_DB, GWP

GWP_ID = method_id(" > ".join(GWP))
NOWHERE = Path("/nonexistent-static")


@pytest.fixture(scope="module")
def client(context: ServerContext, full_server: FastMCP) -> Iterator[TestClient]:
    with TestClient(build_view(context, full_server, static=NOWHERE)) as client:
        yield client


@pytest.fixture
async def built(full_server: FastMCP) -> tuple[str, int]:
    """A system an agent searched for and then described, and the seq of that entry."""
    agent = Client(full_server, client_info=Implementation(name="view-test-agent", version="1"))
    async with agent as session:
        made = await session.call_tool(
            "create_product_system", {"name": "watched", "database": FIXTURE_DB}
        )
        system_id = made.structured_content["value"]["id"]
        await session.call_tool("search_processes", {"database": FIXTURE_DB, "query": "a"})
        changed = await session.call_tool(
            "update_product_system", {"product_system_id": system_id, "description": "seen"}
        )
    return system_id, changed.structured_content["entry"]["seq"]


def test_the_agents_and_their_calls_are_listed(client: TestClient, built: tuple[str, int]) -> None:
    system_id, _ = built
    agents = client.get("/api/agents").json()["value"]
    mine = next(a for a in agents if a["agent"] == "view-test-agent")
    assert mine["origin"] == "agent" and mine["product_system_id"] == system_id
    calls = client.get("/api/activity", params={"product_system_id": system_id}).json()["value"]
    assert [c["tool"] for c in calls if c["agent"] == "view-test-agent"][-1] == (
        "update_product_system"
    )
    since = calls[-1]["started_at"]
    later = client.get("/api/activity", params={"agent": "view-test-agent", "after": since})
    assert later.json()["value"] == []


def test_a_time_that_is_not_one_is_invalid(client: TestClient) -> None:
    assert client.get("/api/activity", params={"after": "yesterday"}).status_code == 400


def test_the_trail_of_an_entry_is_what_led_to_it(
    client: TestClient, built: tuple[str, int]
) -> None:
    system_id, seq = built
    found = client.get(f"/api/product-systems/{system_id}/log/{seq}/trail").json()["value"]
    assert [c["tool"] for c in found] == ["search_processes", "update_product_system"]
    none = client.get(f"/api/product-systems/{system_id}/log/99/trail").json()["value"]
    assert none == []
    missing = client.get(f"/api/product-systems/{uuid.uuid4()}/log/1/trail")
    assert missing.status_code == 404


def test_a_read_reruns_and_says_whether_the_system_moved(
    client: TestClient, built: tuple[str, int]
) -> None:
    system_id, _ = built
    calls = client.get("/api/activity", params={"agent": "view-test-agent"}).json()["value"]
    search = next(c for c in calls if c["tool"] == "search_processes")
    again = client.post(f"/api/activity/{search['id']}/rerun").json()["value"]
    assert "items" in again["result"] and again["at_hash"] is None and again["hash_now"] is None
    write = next(c for c in calls if c["tool"] == "update_product_system")
    refused = client.post(f"/api/activity/{write['id']}/rerun")
    assert refused.status_code == 400 and "changes a model" in refused.json()["message"]
    assert client.post(f"/api/activity/{uuid.uuid4()}/rerun").status_code == 404


async def test_an_agents_open_trail_is_its_calls_after_its_latest_write(
    client: TestClient, full_server: FastMCP
) -> None:
    agent = Client(full_server, client_info=Implementation(name="open-trail-agent", version="1"))
    async with agent as session:
        await session.call_tool("create_product_system", {"name": "open", "database": FIXTURE_DB})
        await session.call_tool("search_processes", {"database": FIXTURE_DB, "query": "a"})
    found = client.get("/api/agents/open-trail-agent/trail").json()["value"]
    assert [c["tool"] for c in found] == ["search_processes"]
    assert client.get("/api/agents/nobody/trail").json()["value"] == []
    assert client.get("/api/agents/-leading/trail").status_code == 400


async def test_an_open_trail_under_a_system_leaves_out_the_calls_about_another(
    client: TestClient, full_server: FastMCP
) -> None:
    agent = Client(full_server, client_info=Implementation(name="scoped-trail-agent", version="1"))
    async with agent as session:
        made = await session.call_tool(
            "create_product_system", {"name": "scoped", "database": FIXTURE_DB}
        )
        system_id = made.structured_content["value"]["id"]
        await session.call_tool("search_processes", {"database": FIXTURE_DB, "query": "a"})
        await session.call_tool("get_product_system", {"product_system_id": system_id})
    under = client.get(f"/api/agents/scoped-trail-agent/trail?product_system_id={system_id}")
    assert [c["tool"] for c in under.json()["value"]] == ["search_processes", "get_product_system"]
    elsewhere = client.get(f"/api/agents/scoped-trail-agent/trail?product_system_id={uuid.uuid4()}")
    assert [c["tool"] for c in elsewhere.json()["value"]] == ["search_processes"]


def test_the_page_records_the_calculations_a_person_starts_and_not_what_draws_a_result(
    client: TestClient, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    base = f"/api/product-systems/{system_id}"
    before = len(client.get("/api/activity", params={"agent": "view"}).json()["value"])
    assert client.get(f"{base}/validation").status_code == 200
    assert client.post(f"{base}/impact", json={"method_id": GWP_ID}).status_code == 200
    drawn = client.post(f"{base}/contributions", json={"method_id": GWP_ID, "by": "process"})
    assert drawn.status_code == 200
    assert client.get("/api/activity", params={"agent": "view"}).json()["value"][before:] == []
    started = client.post(f"{base}/impact?started=true", json={"method_id": GWP_ID})
    assert started.status_code == 200
    calls = client.get("/api/activity", params={"agent": "view"}).json()["value"]
    assert [c["tool"] for c in calls[before:]] == ["calculate_impact"]
    assert calls[-1]["origin"] == "view" and calls[-1]["summary"]["scores"]
    assert client.post(f"/api/activity/{calls[-1]['id']}/rerun").status_code == 200
    again = client.get("/api/activity", params={"agent": "view"}).json()["value"]
    assert [c["tool"] for c in again[before:]] == ["calculate_impact", "calculate_impact"]
    agents = client.get("/api/agents").json()["value"]
    assert next(a for a in agents if a["agent"] == "view")["origin"] == "view"


def test_a_card_placed_and_released_through_the_page_is_not_activity(
    client: TestClient, fixture_system_stored: ProductSystem
) -> None:
    system_id = str(fixture_system_stored.id)
    before = len(client.get("/api/activity", params={"agent": "view"}).json()["value"])
    placed = client.post(
        f"/api/product-systems/{system_id}/layout",
        json={"placements": [{"code": "frame", "x": 1.0, "y": 2.0}]},
    )
    released = client.delete(f"/api/product-systems/{system_id}/layout")
    assert placed.status_code == released.status_code == 200
    after = client.get("/api/activity", params={"agent": "view"}).json()["value"]
    assert after[before:] == []


def test_the_anchors_answer_the_reference_or_the_roots(
    client: TestClient, built: tuple[str, int], fixture_system_stored: ProductSystem
) -> None:
    empty, _ = built
    assert client.get(f"/api/product-systems/{empty}/anchors").json()["value"] == []
    one = client.get(f"/api/product-systems/{fixture_system_stored.id}/anchors").json()["value"]
    assert one == ["widget"]
    assert client.get(f"/api/product-systems/{uuid.uuid4()}/anchors").status_code == 404


async def test_the_calculations_of_a_system_are_its_impact_calls_newest_first(
    client: TestClient, full_server: FastMCP
) -> None:
    agent = Client(full_server, client_info=Implementation(name="calc-test-agent", version="1"))
    async with agent as session:
        made = await session.call_tool(
            "create_product_system", {"name": "scored", "database": FIXTURE_DB}
        )
        system_id = made.structured_content["value"]["id"]
        await session.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": "p",
                "name": "p",
                "unit": "kilogram",
                "reference_product": "p",
            },
        )
        await session.call_tool(
            "update_product_system", {"product_system_id": system_id, "reference_process": "p"}
        )
        hits = await session.call_tool(
            "search_processes", {"database": FIXTURE_DB, "query": "steel"}
        )
        chosen = hits.structured_content["items"][0]["ref"]["id"]
        await session.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": "p",
                "type": "product",
                "amount": 0.5,
                "input": {"kind": "background", "database": FIXTURE_DB, "id": chosen},
            },
        )
        await session.call_tool(
            "calculate_impact", {"product_system_id": system_id, "method_id": GWP_ID}
        )
        await session.call_tool(
            "contribution_analysis",
            {"product_system_id": system_id, "method_id": GWP_ID, "by": "process"},
        )
    client.post(f"/api/product-systems/{system_id}/impact?started=true", json={"method_id": GWP_ID})
    found = client.get(f"/api/product-systems/{system_id}/calculations").json()["value"]
    assert [(c["tool"], c["origin"]) for c in found] == [
        ("calculate_impact", "view"),
        ("calculate_impact", "agent"),
    ]
    assert found[1]["arguments"]["method_id"] == GWP_ID
    assert found[1]["summary"]["scores"][0]["unit"]
    missing = client.get(f"/api/product-systems/{uuid.uuid4()}/calculations")
    assert missing.status_code == 404
