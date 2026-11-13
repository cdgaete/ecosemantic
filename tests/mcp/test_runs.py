from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import shutil
import threading
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from ecosemantic.compute.parameters import materialize
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import DemandItem, Method, ProductSystem, method_id
from ecosemantic.ports.run import RunLauncher, RunPort
from ecosemantic.ports.types import (
    MonteCarloCategory,
    MonteCarloConfig,
    MonteCarloResult,
    MonteCarloSummary,
    Run,
    RunDraft,
    RunPatch,
    System,
)
from tests.conftest import fixture_system
from tests.fixture_data import CODES, FIXTURE_DATABASE, GWP
from tests.memory_background import MemoryInventory

GWP_ID = method_id(" > ".join(GWP))


async def finished(
    client: Client, run_id: str, seconds: float = 120, samples: bool = False
) -> dict[str, object]:
    """The run once it is no longer open, or an assertion failure when it never settles."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        out = await client.call_tool("get_run", {"run_id": run_id, "samples": samples})
        run = out.structured_content["value"]
        if not run["open"]:
            return run
        await asyncio.sleep(0.2)
    raise AssertionError(f"run {run_id} never settled")


def starting(system: ProductSystem, **monte_carlo: object) -> dict[str, object]:
    return {"product_system_id": str(system.id), "method_id": GWP_ID, "monte_carlo": monte_carlo}


async def settle(runs: RunPort, *run_ids: uuid.UUID) -> None:
    """Settle runs no worker carries, so the next test does not find them open."""
    for run_id in run_ids:
        await runs.update_run(run_id, RunPatch(status="done"))


@pytest.fixture(autouse=True)
async def _every_run_settled(context: ServerContext) -> AsyncIterator[None]:
    """Settle the runs a test leaves open, so an assertion that fails before a test settles its
    run cannot refuse every later start in this file."""
    yield
    held = await context.runs.list_runs()
    await settle(context.runs, *[run.id for run in held if run.open])


class RecordingLauncher:
    """Starts nothing, so the run it is handed stays open however fast the machine is, and keeps
    the run ids it was asked to start."""

    def __init__(self) -> None:
        self.started: list[uuid.UUID] = []

    def start(self, run_id: uuid.UUID) -> int:
        self.started.append(run_id)
        return 4242

    def alive(self, run_id: uuid.UUID) -> bool:
        return run_id in self.started


class GatedLauncher:
    """Hands a run to the launcher it wraps only once the test opens the gate, so the run is still
    open when the test stops it, and names the run it was handed."""

    def __init__(self, inner: RunLauncher) -> None:
        self.inner = inner
        self.entered = threading.Event()
        self.opened = threading.Event()
        self.run_id: uuid.UUID | None = None

    def start(self, run_id: uuid.UUID) -> int:
        self.run_id = run_id
        self.entered.set()
        self.opened.wait()
        return self.inner.start(run_id)

    def alive(self, run_id: uuid.UUID) -> bool:
        return self.inner.alive(run_id)


async def test_a_started_run_finishes_with_the_answer_the_synchronous_call_gives(
    full_server: FastMCP, context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=12345)
        )
        run = started.structured_content["value"]
        assert run["status"] in ("queued", "running") and run["at_hash"] and run["pid"]
        done = await finished(client, run["id"], samples=True)
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
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    bound = dataclasses.replace(context, launcher=RecordingLauncher())
    async with Client(build_server(bound)) as client:
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


async def test_two_starts_at_once_leave_one_run(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    bound = dataclasses.replace(context, launcher=RecordingLauncher())
    async with Client(build_server(bound)) as client:
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
    assert len(started) == 1 and len(refused) == 1, (started, refused)
    assert refused[0]["error"] == "conflict" and started[0]["id"] in refused[0]["message"]


async def test_two_servers_over_one_workspace_start_one_run(
    bundle_dir: Path,
    context: ServerContext,
    fixture_system_stored: ProductSystem,
) -> None:
    other = build_context(bundle_dir, context.systems_dir)
    one_context = dataclasses.replace(context, launcher=RecordingLauncher())
    two_context = dataclasses.replace(other, launcher=RecordingLauncher())
    try:
        async with (
            Client(build_server(one_context)) as one,
            Client(build_server(two_context)) as two,
        ):
            outcomes = await asyncio.gather(
                one.call_tool(
                    "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=1)
                ),
                two.call_tool(
                    "start_monte_carlo", starting(fixture_system_stored, n=40, n_min=1, seed=2)
                ),
                return_exceptions=True,
            )
    finally:
        other.close()
    started = [o.structured_content["value"] for o in outcomes if not isinstance(o, Exception)]
    refused = [json.loads(str(o)) for o in outcomes if isinstance(o, ToolError)]
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
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    gated = GatedLauncher(context.launcher)
    bound = dataclasses.replace(context, launcher=gated)
    async with Client(build_server(bound)) as client:
        carrying = asyncio.create_task(
            client.call_tool(
                "start_monte_carlo", starting(fixture_system_stored, n=60, n_min=1, seed=12345)
            )
        )
        try:
            await asyncio.wait_for(asyncio.to_thread(gated.entered.wait), 60)
            assert gated.run_id is not None
            asked = await client.call_tool("cancel_run", {"run_id": str(gated.run_id)})
            # the worker starts only once the gate opens, so the run was still in flight
            assert asked.structured_content["value"]["cancel_requested"] is True
            assert asked.structured_content["value"]["status"] == "queued"
            gated.opened.set()
            await carrying
            settled = await finished(client, str(gated.run_id), samples=True)
            with pytest.raises(ToolError) as caught:
                await client.call_tool("cancel_run", {"run_id": str(gated.run_id)})
        finally:
            gated.opened.set()
            if not carrying.done():
                carrying.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await carrying
    assert settled["status"] == "cancelled"
    assert settled["result"]["stopped"] == "cancelled"
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


async def test_the_listing_answers_each_run_without_its_result_which_get_run_answers(
    full_server: FastMCP, fixture_system_stored: ProductSystem
) -> None:
    async with Client(full_server) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=2, n_min=1, seed=12345)
        )
        run_id = started.structured_content["value"]["id"]
        await finished(client, run_id)
        listed = (
            await client.call_tool(
                "list_runs", {"product_system_id": str(fixture_system_stored.id)}
            )
        ).structured_content["value"]
        one = (await client.call_tool("get_run", {"run_id": run_id})).structured_content["value"]
    [mine] = [run for run in listed if run["id"] == run_id]
    assert one["result"]["n"] == 2
    assert mine == {key: value for key, value in one.items() if key != "result"}


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


async def test_get_run_answers_a_histogram_unless_the_samples_are_asked_for(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    async with Client(build_server(context)) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=1)
        )
        run_id = started.structured_content["value"]["id"]
        await finished(client, run_id)
        bare = (await client.call_tool("get_run", {"run_id": run_id})).structured_content["value"]
        asked = (
            await client.call_tool("get_run", {"run_id": run_id, "samples": True})
        ).structured_content["value"]
    assert [category["samples"] for category in bare["result"]["categories"]] == [None]
    assert bare["result"]["categories"][0]["summary"] == asked["result"]["categories"][0]["summary"]
    histogram = bare["result"]["categories"][0]["histogram"]
    assert len(histogram["counts"]) == 20
    assert sum(histogram["counts"]) == bare["result"]["n"] == 3
    draws = asked["result"]["categories"][0]["samples"]
    assert len(draws) == asked["result"]["n"] == 3
    assert asked["result"]["categories"][0]["histogram"] is None


async def test_get_run_answers_a_record_naming_each_method_by_its_whole_record(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    method = await context.inventory.resolve_method(fixture_system_stored.database.name, GWP_ID)
    run = recorded_run(fixture_system_stored, method)
    folder = context.systems_dir / "runs" / str(run.id)
    try:
        written_naming_whole_methods(folder, run, method)
        async with Client(build_server(context)) as client:
            read = (
                await client.call_tool("get_run", {"run_id": str(run.id), "samples": True})
            ).structured_content["value"]
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    ids = [listed["id"] for listed in read["methods"]]
    assert ids == [method.id]
    assert [category["method_id"] for category in read["result"]["categories"]] == ids
    assert read["result"]["categories"][0]["samples"] == [0.000149, 0.000147, 0.000157]


def recorded_run(stored: ProductSystem, method: Method) -> Run:
    """A finished run of a product system under one method, carrying one category's draws."""
    return Run(
        id=uuid.UUID(int=7),
        product_system_id=stored.id,
        at_hash="9c1d" + "0" * 60,
        methods=[method],
        config=MonteCarloConfig(n=3),
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="done",
        result=MonteCarloResult(
            database=FIXTURE_DATABASE,
            n=3,
            stopped="fixed",
            gating_method=method.id,
            scope="full",
            normals_at_amount=0,
            credit_loops=[],
            dropped_draws=[],
            dropped_loops=[],
            dropped_background=[],
            categories=[
                MonteCarloCategory(
                    method_id=method.id,
                    summary=MonteCarloSummary(
                        n=3,
                        mean=0.00016,
                        median=0.00015,
                        median_ci95=(0.00014, 0.00017),
                        percentiles=(0.0001, 0.00025),
                        rel_se=0.046,
                    ),
                    samples=[0.000149, 0.000147, 0.000157],
                )
            ],
        ),
    )


def written_naming_whole_methods(folder: Path, run: Run, method: Method) -> None:
    """The run's record in the shape a store wrote when a result named each method by its whole
    record."""
    stored = run.model_dump(mode="json")
    result = stored["result"]
    assert isinstance(result, dict)
    whole = method.model_dump(mode="json")
    result["gating_method"] = whole
    for category in result["categories"]:
        assert isinstance(category, dict)
        del category["method_id"]
        category["method"] = whole
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps(stored), encoding="utf-8")


async def test_a_finished_run_names_each_category_by_the_id_of_one_of_its_methods(
    context: ServerContext, fixture_system_stored: ProductSystem
) -> None:
    async with Client(build_server(context)) as client:
        started = await client.call_tool(
            "start_monte_carlo", starting(fixture_system_stored, n=3, n_min=1, seed=1)
        )
        run_id = started.structured_content["value"]["id"]
        run = await finished(client, run_id)
    ids = [method["id"] for method in run["methods"]]
    assert ids == [GWP_ID]
    assert [category["method_id"] for category in run["result"]["categories"]] == ids
    assert run["result"]["gating_method"] in ids
