"""The home page's rows: one answer over every stored system, and a system whose validation
cannot run kept to its own row."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastmcp import FastMCP
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.view.app import build_view

NOWHERE = Path("/nonexistent-static")


def _page(context: ServerContext, server: FastMCP) -> TestClient:
    return TestClient(build_view(context, server, static=NOWHERE))


async def test_every_system_has_its_row(
    ports_only: ServerContext, ports_only_server: FastMCP, cup: tuple[str, str]
) -> None:
    system_id, _ = cup
    with _page(ports_only, ports_only_server) as page:
        rows = page.get("/api/home").json()["value"]
        assert [row["system"]["id"] for row in rows] == [system_id]
        row = rows[0]
        assert row["processes"] == 1
        log = page.get(f"/api/product-systems/{system_id}/log").json()["value"]
        assert row["last"]["seq"] == log[-1]["seq"]
        assert row["open_requests"] == 0
        validation = page.get(f"/api/product-systems/{system_id}/validation").json()
        assert row["validation"] == validation["value"]
        assert row["unvalidated"] is None


async def test_a_system_that_cannot_be_validated_keeps_its_row(
    ports_only: ServerContext, ports_only_server: FastMCP, cup: tuple[str, str]
) -> None:
    system_id, _ = cup
    stored = await ports_only.storage.get_product_system(uuid.UUID(system_id))
    elsewhere = stored.model_copy(
        deep=True,
        update={
            "id": uuid.uuid4(),
            "hash": None,
            "database": stored.database.model_copy(update={"name": "nowhere"}),
        },
    )
    await ports_only.storage.put_product_system(elsewhere, ports_only.actor, "moved to nowhere")
    with _page(ports_only, ports_only_server) as page:
        rows = page.get("/api/home").json()["value"]
        listed = [card["id"] for card in page.get("/api/product-systems").json()["value"]]
        assert [row["system"]["id"] for row in rows] == listed
        kept = next(row for row in rows if row["system"]["id"] == system_id)
        unvalidated = next(row for row in rows if row["system"]["id"] == str(elsewhere.id))
        refused = page.get(f"/api/product-systems/{elsewhere.id}/validation")
        assert refused.status_code == 404
        assert unvalidated["unvalidated"] == refused.json()
        assert unvalidated["unvalidated"]["error"] == "not_found"
        assert unvalidated["validation"] is None
        assert kept["validation"] is not None
        assert kept["unvalidated"] is None
