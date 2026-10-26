"""Record the API's answers over the synthetic fixture as JSON the page's tests read."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import Client, FastMCP
from mcp.types import Implementation
from pydantic import SecretStr
from starlette.testclient import TestClient

from ecosemantic.compute.edits import add_scenario
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import (
    Actor,
    Case,
    Exchange,
    ExchangeOverride,
    Parameter,
    ParameterOverride,
    Process,
    ProductSystem,
    method_id,
)
from ecosemantic.ports.types import (
    Account,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    InstallTerms,
    Outcome,
    RequestDraft,
)
from ecosemantic.view.app import build_view

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import fixture_system, uid  # noqa: E402
from tests.engine_fixture import install_fixtures  # noqa: E402
from tests.fixture_data import FIXTURE_BIO, FIXTURE_DATABASE, FIXTURE_DB, FLOW_IDS, GWP

FIXTURES = Path(__file__).resolve().parents[1] / "page" / "tests" / "fixtures"
GWP_ID = method_id(" > ".join(GWP))
NOWHERE = Path("/nonexistent-static")
PERSON = Actor(kind="person", name="Carlos")
AGENT = "fixture-agent"
CLIENT = {"name": "Claude Desktop", "version": "fixture"}
BAFU_TERMS = "BAFU release terms, fixture\n"
LOOPBACK = ("127.0.0.1", 50000)


def parameterised_system() -> ProductSystem:
    """The fixture widget with a literal and a formula parameter, a case and a scenario."""
    system = fixture_system().product_system
    assert system is not None
    widget = system.process("widget")
    widget.exchanges[3].formula = "frame_mass"
    system.parameters = [
        Parameter(name="frame_mass", value=0.25, unit="kilogram", description="frame per widget"),
        Parameter(name="frame_steel", formula="frame_mass * 2.4", unit="kilogram"),
    ]
    system.cases = [Case(name="heavy", description="a heavier frame", values={"frame_mass": 0.5})]
    changed, _ = add_scenario(
        system,
        name="lighter",
        description="a lighter frame and half the electricity",
        overrides=[
            ParameterOverride(name="frame_mass", value=0.2),
            ExchangeOverride(exchange_id=widget.exchanges[2].id, multiplier=0.5),
        ],
    )
    return changed


def unfinished_system() -> ProductSystem:
    """A product system whose one process draws nothing, so validation fails."""
    stub = Process(
        id=uid("fixture-act", "stub"),
        code="stub",
        name="stub",
        unit="unit",
        location="GLO",
        reference_product="stub",
        exchanges=[
            Exchange(
                id=uid("fixture-ex", "stub", "0"),
                type="production",
                name="stub",
                amount=1.0,
                unit="unit",
            )
        ],
    )
    return ProductSystem(
        id=uid("fixture-product_system", "unfinished"),
        name="unfinished",
        database=FIXTURE_DATABASE,
        processes=[stub],
    )


async def store_systems(context: ServerContext) -> tuple[str, str]:
    """Store both systems, an open request and a resolved one; answer both ids."""
    system = parameterised_system()
    await context.storage.put_product_system(system, context.actor, "created")
    stored = await context.storage.get_product_system(system.id)
    assert stored.hash is not None
    await context.storage.post_request(
        system.id,
        RequestDraft(
            actor=PERSON,
            kind="return",
            at_hash=stored.hash,
            message="recheck the lorry distance",
        ),
    )
    edit = await context.storage.post_request(
        system.id,
        RequestDraft(
            actor=PERSON,
            kind="edit",
            at_hash=stored.hash,
            message="use recycled steel in the frame",
            entity="process",
            entity_id="frame",
        ),
    )
    await context.storage.resolve_request(
        system.id,
        edit.id,
        Outcome(
            timestamp=datetime.now(UTC),
            actor=context.actor,
            resolution="overridden",
            message="the supplier certifies no recycled content",
        ),
    )
    unfinished = unfinished_system()
    await context.storage.put_product_system(unfinished, context.actor, "created")
    return str(system.id), str(unfinished.id)


def finished_run(client: TestClient, run_id: str) -> dict[str, object]:
    """The run's answer once it is no longer open."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        answer = client.get(f"/api/runs/{run_id}").json()
        if not answer["value"]["open"]:
            return answer
        time.sleep(0.2)
    raise TimeoutError(f"run {run_id} did not settle")


async def record_installs(context: ServerContext) -> None:
    """Hold an ecoinvent account and write one install, stopped at its terms, into the record store
    directly, so the recorded answers carry a held kind and an install without a process."""
    context.credentials["ecoinvent"] = Account(username="fixture", password=SecretStr("fixture"))
    context.client.update(CLIENT)
    licence = context.data_dir / "installs" / "bafu-terms.txt"
    licence.parent.mkdir(parents=True, exist_ok=True)
    licence.write_text(BAFU_TERMS)
    posted = await context.installs.post_install(
        InstallDraft(source="bafu", actor=PERSON, version="2026-v1")
    )
    await context.installs.update_install(
        posted.id,
        InstallPatch(
            status="terms",
            progress=InstallProgress(step="fetching the terms"),
            terms=InstallTerms(licence=str(licence), citation="BAFU 2026-v1, openLCA Nexus"),
            finished_at=datetime.now(UTC),
        ),
    )


def record(client: TestClient, system_id: str, unfinished_id: str) -> dict[str, object]:
    """Every answer the page's tests read, keyed by fixture name."""
    base = f"/api/product-systems/{system_id}"
    recorded: dict[str, object] = {
        "databases": client.get("/api/databases").json(),
        "sources": client.get("/api/sources").json(),
        "installs": client.get("/api/installs").json(),
        "credentials": client.get("/api/credentials").json(),
        "server": client.get("/api/server").json(),
        "vocabulary_impact_methods": client.get(
            f"/api/databases/{FIXTURE_DB}/vocabulary/impact_methods"
        ).json(),
        "vocabulary_compartments": client.get(
            f"/api/databases/{FIXTURE_DB}/vocabulary/compartments"
        ).json(),
        "search_processes": client.get(
            f"/api/databases/{FIXTURE_DB}/processes", params={"query": "steel"}
        ).json(),
        "search_methods": client.get(
            f"/api/databases/{FIXTURE_DB}/methods", params={"query": "GWP"}
        ).json(),
        "search_elementary_flows": client.get(
            f"/api/databases/{FIXTURE_DB}/elementary-flows", params={"query": "carbon"}
        ).json(),
        "elementary_flow": client.get(
            f"/api/databases/{FIXTURE_BIO}/elementary-flows/{FLOW_IDS['water_in']}"
        ).json(),
        "systems": client.get("/api/product-systems").json(),
        "system": client.get(base).json(),
        "parameters": client.get(f"{base}/parameters").json(),
        "log": client.get(f"{base}/log").json(),
        "validation": client.get(f"{base}/validation").json(),
        "validation_errors": client.get(f"/api/product-systems/{unfinished_id}/validation").json(),
        "anchors": client.get(f"{base}/anchors").json(),
        "anchors_unfinished": client.get(f"/api/product-systems/{unfinished_id}/anchors").json(),
        "layout": client.get(f"{base}/layout").json(),
        "requests": client.get(f"{base}/requests").json(),
        "impact": client.post(
            f"{base}/impact", json={"impact_method": GWP[1], "variants": []}
        ).json(),
        "impact_monte_carlo": client.post(
            f"{base}/impact",
            json={
                "impact_method": GWP[1],
                "variants": ["heavy", "lighter"],
                "monte_carlo": {"n_min": 6, "n_max": 8, "rel_se_target": 0.05, "seed": 12345},
            },
        ).json(),
        "contributions_process": client.post(
            f"{base}/contributions", json={"method_id": GWP_ID, "by": "process"}
        ).json(),
        "contributions_flow": client.post(
            f"{base}/contributions", json={"method_id": GWP_ID, "by": "flow"}
        ).json(),
        "contributions_path": client.post(
            f"{base}/contributions", json={"method_id": GWP_ID, "by": "path", "max_level": 2}
        ).json(),
        "inventory": client.post(f"{base}/inventory", json={"limit": 50}).json(),
        "error_not_found": client.get(
            "/api/product-systems/00000000-0000-4000-8000-000000000000"
        ).json(),
    }
    hits = recorded["search_processes"]
    assert isinstance(hits, dict)
    ref = hits["items"][0]["ref"]["id"]
    recorded["background_process"] = client.get(
        f"/api/databases/{FIXTURE_DB}/processes/{ref}"
    ).json()
    started = client.post(
        f"{base}/runs",
        json={"method_id": GWP_ID, "monte_carlo": {"n": 6, "n_min": 1, "seed": 12345}},
    ).json()
    recorded["run"] = finished_run(client, started["value"]["id"])
    recorded["runs"] = client.get(f"{base}/runs").json()
    return recorded


async def agent_at_work(server: FastMCP) -> tuple[str, int, int]:
    """An agent builds a system through the tools, leaving a trail a search led, a trail a
    calculation led, and an open trail with a failed read; answer the system's id and the seqs
    of the two entries."""
    agent = Client(server, client_info=Implementation(name=AGENT, version="1"))
    async with agent as session:
        made = await session.call_tool(
            "create_product_system", {"name": "bottle", "database": FIXTURE_DB}
        )
        system_id = made.structured_content["value"]["id"]
        await session.call_tool(
            "create_process",
            {
                "product_system_id": system_id,
                "code": "bottle",
                "name": "bottle",
                "unit": "kilogram",
                "reference_product": "bottle",
            },
        )
        await session.call_tool(
            "update_product_system",
            {"product_system_id": system_id, "reference_process": "bottle"},
        )
        hits = await session.call_tool(
            "search_processes", {"database": FIXTURE_DB, "query": "steel"}
        )
        chosen = hits.structured_content["items"][0]["ref"]["id"]
        await session.call_tool(
            "get_background_process", {"database": FIXTURE_DB, "process_id": chosen}
        )
        linked = await session.call_tool(
            "create_exchange",
            {
                "product_system_id": system_id,
                "code": "bottle",
                "type": "product",
                "amount": 0.5,
                "input": {"kind": "background", "database": FIXTURE_DB, "id": chosen},
            },
        )
        methods = await session.call_tool(
            "search_methods", {"database": FIXTURE_DB, "query": "climate"}
        )
        await session.call_tool(
            "calculate_impact",
            {
                "product_system_id": system_id,
                "method_id": methods.structured_content["items"][0]["id"],
            },
        )
        edited = await session.call_tool(
            "update_exchange",
            {
                "product_system_id": system_id,
                "exchange_id": linked.structured_content["value"]["id"],
                "amount": 0.6,
            },
        )
        await session.call_tool(
            "search_processes", {"database": FIXTURE_DB, "query": "electricity"}
        )
        await session.call_tool(
            "get_background_process",
            {"database": FIXTURE_DB, "process_id": "missing"},
            raise_on_error=False,
        )
    return (
        system_id,
        linked.structured_content["entry"]["seq"],
        edited.structured_content["entry"]["seq"],
    )


def record_activity(
    client: TestClient, system_id: str, searched: int, computed: int
) -> dict[str, object]:
    """The agents, the agent's calls, its system, that system's log, the two trails, the open
    trail, the calculations the record holds for the system, and its calculation run again over
    the edited system. The calculations are read before that rerun, which is itself recorded as
    a calculation the page made."""
    base = f"/api/product-systems/{system_id}"
    calls = client.get("/api/activity", params={"agent": AGENT}).json()
    impact = next(call for call in calls["value"] if call["effect"] == "compute")
    return {
        "agents": client.get("/api/agents").json(),
        "calls": calls,
        "agent_system": client.get(base).json(),
        "agent_log": client.get(f"{base}/log").json(),
        "trail": client.get(f"{base}/log/{searched}/trail").json(),
        "trail_compute": client.get(f"{base}/log/{computed}/trail").json(),
        "open_trail": client.get(f"/api/agents/{AGENT}/trail").json(),
        "calculations": client.get(f"{base}/calculations").json(),
        "rerun": client.post(f"/api/activity/{impact['id']}/rerun").json(),
    }


async def record_fixtures(context: ServerContext) -> dict[str, object]:
    """Store the recorded systems in the context's storage, let an agent work, and answer every
    recorded route."""
    system_id, unfinished_id = await store_systems(context)
    await record_installs(context)
    server = build_server(context)
    agent_system, searched, computed = await agent_at_work(server)
    with TestClient(build_view(context, server, static=NOWHERE), client=LOOPBACK) as client:
        recorded = record(client, system_id, unfinished_id)
        return {**recorded, **record_activity(client, agent_system, searched, computed)}


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        systems_dir = Path(tmp) / "systems"
        data_dir.mkdir()
        systems_dir.mkdir()
        install_fixtures(data_dir, Path(tmp))
        context = build_context(data_dir, systems_dir)
        recorded = await record_fixtures(context)
        context.close()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, payload in recorded.items():
        (FIXTURES / f"{name}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(recorded)} fixtures to {FIXTURES}")


if __name__ == "__main__":
    asyncio.run(main())
