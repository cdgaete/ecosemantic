"""A page off the engine's computer names no path on it, and the page reruns none."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import ProductSystem
from ecosemantic.ports.types import CallDraft, Effect
from ecosemantic.view.app import build_view
from tests.mcp.test_bridge_paths import DOORS, bridged, store, stored
from tests.view.test_installs import OPENLCA, zipped

__all__ = ["store", "stored"]

NOWHERE = Path("/nonexistent-static")


def admitted(proof: str, path: str) -> bool:
    """The bridge's check, admitting every proof."""
    return True


@pytest.fixture(params=["here", "bridge"])
def client(request: pytest.FixtureRequest, store: ServerContext) -> Iterator[TestClient]:
    """The page from this computer and through the bridge."""
    view = build_view(store, build_server(store), static=NOWHERE, bridged=admitted)
    app = bridged(view) if request.param == "bridge" else view
    with TestClient(app, client=("127.0.0.1", 50000)) as served:
        yield served


@pytest.mark.parametrize("effect", ["read", "write"])
@pytest.mark.parametrize("tool", ["export_product_system", "export_tables"])
async def test_the_page_reruns_no_call_that_names_a_path(
    client: TestClient,
    store: ServerContext,
    stored: ProductSystem,
    tmp_path: Path,
    tool: str,
    effect: Effect,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "mine.txt").write_bytes(b"mine")
    path = work / "mine.txt" if tool == "export_product_system" else work
    call = await store.activity.record(
        CallDraft(
            agent="chat",
            client="chat",
            origin="agent",
            tool=tool,
            effect=effect,
            arguments={"product_system_id": str(stored.id), "path": str(path), "replace": True},
            product_system_id=stored.id,
            started_at=datetime.now(UTC),
            duration_ms=1,
            outcome="error",
        )
    )
    refused = client.post(f"/api/activity/{call.id}/rerun")
    assert refused.status_code == 501, refused.text
    assert "the page reruns no such call" in refused.json()["message"]
    assert [held.name for held in work.iterdir()] == ["mine.txt"]
    assert (work / "mine.txt").read_bytes() == b"mine"


@pytest.mark.parametrize("door", sorted(DOORS))
async def test_a_page_off_this_computer_posts_no_install_that_names_a_path(
    store: ServerContext, tmp_path: Path, door: str
) -> None:
    (tmp_path / "held.zip").write_bytes(zipped())
    view = build_view(store, build_server(store), static=NOWHERE, bridged=admitted)
    body = {**OPENLCA, "source": "openlca", "package": str(tmp_path / "held.zip")}
    with TestClient(DOORS[door][0](view), client=("127.0.0.1", 50000)) as client:
        refused = client.post("/api/installs", json=body)
    assert refused.status_code == 501, refused.text
    assert refused.json()["error"] == "not_supported"
    assert await store.installs.list_installs() == []


@pytest.mark.parametrize("door", sorted(DOORS))
async def test_a_page_off_this_computer_still_uploads_a_zip(
    store: ServerContext, tmp_path: Path, door: str
) -> None:
    view = build_view(store, build_server(store), static=NOWHERE, bridged=admitted)
    with TestClient(DOORS[door][0](view), client=("127.0.0.1", 50000)) as client:
        answered = client.post(
            "/api/installs/openlca",
            files={"file": ("database.zip", zipped(), "application/zip")},
            data=OPENLCA,
        )
    assert answered.status_code < 400, answered.text
    [install] = await store.installs.list_installs()
    assert install.draft.package is not None
    Path(install.draft.package).unlink()
