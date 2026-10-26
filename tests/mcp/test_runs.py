from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import time
import uuid
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.compute.parameters import materialize
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import DemandItem, ProductSystem, method_id
from ecosemantic.ports.types import MonteCarloConfig, MonteCarloResult, RunDraft, RunPatch, System
from tests.conftest import fixture_system
from tests.fixture_data import CODES, GWP
from tests.memory_background import MemoryInventory

GWP_ID = method_id(" > ".join(GWP))


async def finished(client: Client, run_id: str, seconds: float = 120) -> dict[str, object]:
    """The run once it is no longer open, or an assertion failure when it never settles."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        out = await client.call_tool("get_run", {"run_id": run_id})
        run = out.structured_content["value"]
        if not run["open"]:
            return run
        await asyncio.sleep(0.2)
    raise AssertionError(f"run {run_id} never settled")


def starting(system: ProductSystem, **monte_carlo: object) -> dict[str, object]:
    return {"product_system_id": str(system.id), "method_id": GWP_ID, "monte_carlo": monte_carlo}


async def test_a_started_run_finishes_with_the_answer_the_synchronous_call_gives(
    full_server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=12345)
        )
        run = started.structured_content["value"]
        assert run["status"] in ("queued", "running") and run["at_hash"] and run["pid"]
        done = await finished(client, run["id"])
    assert done["status"] == "done" and done["progress"]["iterations"] == 3
    assert done["at_hash"] == run["at_hash"]
    stored = await context.storage.get_version(fixture_system_stored.id, run["at_hash"])
    system = System(database=stored.database.name, product_system=materialize(stored))
    methods = [await context.inventory.resolve_method(stored.database.name, GWP_ID)]
    demand = [DemandItem.model_validate(item) for item in done["demand"]]
    config = MonteCarloConfig(n=3, n_min=1, seed=12345)
    same = await context.calculation.monte_carlo(system, demand, methods, config)
    assert MonteCarloResult.model_validate(done["result"]) == same


async def test_a_second_run_is_refused_while_one_is_open(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        first = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=12345)
        )
        run = first.structured_content["value"]
        with pytest.raises(ToolError) as caught:
            await client.call_tool(
                "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1, seed=1)
            )
        refused = json.loads(str(caught.value))
        assert refused["error"] == "conflict" and run["id"] in refused["message"]
        assert refused["details"] == {
            "run_id": run["id"],
            "product_system_id": str(fixture_system_stored.id),
        }
        await client.call_tool("cancel_run", {"run_id": run["id"]})
        await finished(client, run["id"])


async def test_two_starts_at_once_leave_one_run(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        outcomes = await asyncio.gather(
            client.call_tool(
                "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=1)
            ),
            client.call_tool(
                "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=2)
            ),
            return_exceptions=True,
        )
        started = [o.structured_content["value"] for o in outcomes if not isinstance(o, Exception)]
        refused = [json.loads(str(o)) for o in outcomes if isinstance(o, ToolError)]
        for run in started:
            await finished(client, run["id"])
    assert len(started) == 1 and len(refused) == 1, (started, refused)
    assert refused[0]["error"] == "conflict" and started[0]["id"] in refused[0]["message"]


async def test_two_servers_over_one_workspace_start_one_run(
    bundle_dir: Path,
    context: ServerContext,
    full_server: FastMCP,
    fixture_system_stored: ProductSystem,
) -> None:
    other = build_context(bundle_dir, context.systems_dir)
    try:
        async with Client(full_server) as one, Client(build_server(other)) as two:
            outcomes = await asyncio.gather(
                one.call_tool(
                    "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=1)
                ),
                two.call_tool(
                    "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=2)
                ),
                return_exceptions=True,
            )
            started = [
                o.structured_content["value"] for o in outcomes if not isinstance(o, Exception)
            ]
            refused = [json.loads(str(o)) for o in outcomes if isinstance(o, ToolError)]
            for run in started:
                await one.call_tool("cancel_run", {"run_id": run["id"]})
                await finished(one, run["id"])
    finally:
        other.close()
    assert len(started) == 1 and len(refused) == 1, (started, refused)
    assert refused[0]["details"]["run_id"] == started[0]["id"]


async def test_a_start_over_a_record_this_version_cannot_read_names_it(
    full_server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    posted = await context.runs.post_run(
        RunDraft(
            product_system_id=fixture_system_stored.id,
            at_hash="0" * 64,
            demand=[],
            methods=[],
            config=MonteCarloConfig(),
        )
    )
    folder = context.systems_dir / "runs" / str(posted.id)
    stored = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    del stored["at_hash"]
    (folder / "run.json").write_text(json.dumps(stored), encoding="utf-8")
    try:
        async with Client(full_server) as client:
            with pytest.raises(ToolError) as caught:
                await client.call_tool(
                    "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1, seed=1)
                )
        refused = json.loads(str(caught.value))
        assert refused["error"] == "unavailable" and str(posted.id) in refused["message"]
        assert str(folder) in refused["details"]["hint"]
    finally:
        shutil.rmtree(folder)


async def test_a_cancelled_run_settles_as_cancelled_and_keeps_its_samples(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=60, n_min=1, seed=12345)
        )
        run_id = started.structured_content["value"]["id"]
        asked = await client.call_tool("cancel_run", {"run_id": run_id})
        assert asked.structured_content["value"]["cancel_requested"] is True
        settled = await finished(client, run_id)
        with pytest.raises(ToolError) as caught:
            await client.call_tool("cancel_run", {"run_id": run_id})
    assert settled["status"] == "cancelled"
    assert settled["result"]["n"] == len(settled["result"]["categories"][0]["samples"])
    assert json.loads(str(caught.value))["error"] == "conflict"


async def test_runs_are_listed_newest_first_for_one_product_system(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1, seed=12345)
        )
        newest = started.structured_content["value"]["id"]
        await finished(client, newest)
        mine = await client.call_tool(
            "list_runs", {"product_system_id": str(fixture_system_stored.id)}
        )
        every = await client.call_tool("list_runs", {})
    listed = mine.structured_content["value"]
    assert listed[0]["id"] == newest
    assert all(r["product_system_id"] == str(fixture_system_stored.id) for r in listed)
    posted = [r["posted_at"] for r in every.structured_content["value"]]
    assert posted == sorted(posted, reverse=True)


async def test_an_unknown_run_is_not_found(full_server: FastMCP) -> None:
    async with Client(full_server) as client:
        with pytest.raises(ToolError) as caught:
            await client.call_tool("get_run", {"run_id": "00000000-0000-0000-0000-000000000001"})
    assert json.loads(str(caught.value))["error"] == "not_found"


async def test_a_finished_run_survives_the_product_system_moving(
    full_server: FastMCP, context: ServerContext
) -> None:
    widget = fixture_system().product_system
    assert widget is not None
    # a copy of its own, so moving it leaves the shared fixture where other tests expect it
    mover = widget.model_copy(update={"id": uuid.uuid4(), "name": "widget, moved"})
    await context.storage.put_product_system(mover, context.actor, "created")
    async with Client(full_server) as client:
        started = await client.call_tool("start_monte_carlo", starting(mover, n=2, n_min=1, seed=1))
        run = started.structured_content["value"]
        done = await finished(client, run["id"])
        moved = await client.call_tool(
            "set_parameters",
            {
                "product_system_id": str(mover.id),
                "parameters": [{"name": "moved_after_the_run", "value": 1.0}],
            },
        )
        again = await client.call_tool("get_run", {"run_id": run["id"]})
    after = again.structured_content["value"]
    # the run still answers, and says which state it answered for
    assert moved.structured_content["entry"]["result_hash"] != done["at_hash"]
    assert after["status"] == "done" and after["at_hash"] == done["at_hash"]
    assert after["result"]["n"] == 2


async def test_the_server_publishes_the_run_it_started_until_it_settles(
    full_server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    queue = context.events.subscribe(fixture_system_stored.id)
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=12345)
        )
        run_id = started.structured_content["value"]["id"]
        await finished(client, run_id)
    deadline = time.monotonic() + 10
    while context.watchers and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    context.events.unsubscribe(fixture_system_stored.id, queue)
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    assert context.watchers == set()
    assert [e.call.tool for e in seen if e.kind == "call"] == ["start_monte_carlo"]
    moved = [e for e in seen if e.kind == "run"]
    assert moved and all(str(e.run.id) == run_id for e in moved)
    assert moved[-1].run.status == "done" and moved[-1].run.result.n == 3


class RecordingLauncher:
    """Starts nothing, and keeps the run ids it was asked to start."""

    def __init__(self) -> None:
        self.started: list[uuid.UUID] = []

    def start(self, run_id: uuid.UUID) -> int:
        self.started.append(run_id)
        return 4242

    def alive(self, run_id: uuid.UUID) -> bool:
        return run_id in self.started


async def test_start_monte_carlo_starts_the_run_through_the_context_launcher(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    launcher = RecordingLauncher()
    bound = dataclasses.replace(context, launcher=launcher)
    async with Client(build_server(bound)) as client:
        answer = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1)
        )
    run = answer.structured_content["value"]
    assert launcher.started == [uuid.UUID(run["id"])]
    assert run["pid"] == 4242
    await bound.runs.update_run(uuid.UUID(run["id"]), RunPatch(status="done"))


async def test_a_run_names_each_positive_input_to_a_treatment_from_the_moment_it_is_posted(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    # the fixture background holds no treatment, so steel stands for one
    treating = MemoryInventory({CODES["steel"]})
    bound = dataclasses.replace(context, launcher=RecordingLauncher(), inventory=treating)
    async with Client(build_server(bound)) as client:
        answer = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1)
        )
        run_id = answer.structured_content["value"]["id"]
        read = await client.call_tool("get_run", {"run_id": run_id})
    named = ["frame · steel at 2.4", "widget · steel at 0.5"]
    assert answer.structured_content["value"]["treatments_run_backwards"] == named
    assert read.structured_content["value"]["treatments_run_backwards"] == named
    await bound.runs.update_run(uuid.UUID(run_id), RunPatch(status="done"))


async def test_the_run_tools_link_to_the_simulation_page(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    bound = dataclasses.replace(context, view_url="http://127.0.0.1:1?token=abc")
    async with Client(build_server(bound)) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=1)
        )
        run_id = started.structured_content["value"]["id"]
        read = await client.call_tool("get_run", {"run_id": run_id})
        await finished(client, run_id)
    expected = (
        f"http://127.0.0.1:1/systems/{fixture_system_stored.id}/simulations/{run_id}?token=abc"
    )
    assert started.structured_content["view_url"] == expected
    assert read.structured_content["view_url"] == expected
