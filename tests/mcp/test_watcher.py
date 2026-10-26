from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from ecosemantic.backends.filesystem.run_folder import beat, run_dir
from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.events import EventBus
from ecosemantic.installs.supervisor import LocalInstaller
from ecosemantic.mcp.watcher import reap, reap_install, watch, watch_install
from ecosemantic.model.entities import Actor
from ecosemantic.ports.types import (
    STALE_SECONDS,
    Install,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    MonteCarloConfig,
    RunDraft,
    RunPatch,
    RunProgress,
)
from ecosemantic.runs.supervisor import LocalLauncher
from tests.memory_installs import MemoryInstaller, MemoryInstalls
from tests.memory_runs import MemoryLauncher


def draft() -> RunDraft:
    return RunDraft(
        product_system_id=uuid.UUID(int=1),
        at_hash="0" * 64,
        demand=[],
        methods=[],
        config=MonteCarloConfig(n=1),
    )


async def test_the_watcher_publishes_each_change_and_stops_when_the_run_does(
    tmp_path: Path,
) -> None:
    runs = FilesystemRuns(tmp_path)
    system = uuid.UUID(int=1)
    posted = await runs.post_run(
        RunDraft(
            product_system_id=system,
            at_hash="0" * 64,
            demand=[],
            methods=[],
            config=MonteCarloConfig(n=2),
        )
    )
    bus = EventBus()
    queue = bus.subscribe(system)
    watching = asyncio.create_task(
        watch(bus, runs, MemoryLauncher(alive=True), posted.id, interval=0.01)
    )
    await runs.update_run(posted.id, RunPatch(status="running"))
    await runs.update_run(posted.id, RunPatch(progress=RunProgress(iterations=1)))
    await runs.update_run(posted.id, RunPatch(status="done"))
    await asyncio.wait_for(watching, timeout=5)
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    assert all(event.kind == "run" for event in seen)
    assert [event.run.status for event in seen][-1] == "done"
    assert any(event.run.progress.iterations == 1 for event in seen)


async def test_a_run_already_finished_publishes_once_and_returns(tmp_path: Path) -> None:
    runs = FilesystemRuns(tmp_path)
    posted = await runs.post_run(
        RunDraft(
            product_system_id=uuid.UUID(int=1),
            at_hash="0" * 64,
            demand=[],
            methods=[],
            config=MonteCarloConfig(n=1),
        )
    )
    await runs.update_run(posted.id, RunPatch(status="done"))
    bus = EventBus()
    queue = bus.subscribe(uuid.UUID(int=1))
    watcher = watch(bus, runs, MemoryLauncher(), posted.id, interval=0.01)
    await asyncio.wait_for(watcher, timeout=5)
    assert queue.get_nowait().run.status == "done"
    assert queue.empty()


async def test_a_run_that_claims_to_run_with_no_heartbeat_is_failed(tmp_path: Path) -> None:
    runs = FilesystemRuns(tmp_path)
    posted = await runs.post_run(draft())
    await runs.update_run(posted.id, RunPatch(status="running", started_at=datetime.now(UTC)))
    launcher = LocalLauncher(tmp_path, tmp_path, tmp_path, "superlu")
    reaped = await reap(runs, launcher, await runs.get_run(posted.id))
    assert reaped.status == "failed" and reaped.finished_at is not None
    assert reaped.error is not None and "did not finish" in reaped.error.message
    # the correction is written, not merely answered
    assert (await runs.get_run(posted.id)).status == "failed"


async def test_a_live_run_and_a_finished_run_are_left_alone(tmp_path: Path) -> None:
    runs = FilesystemRuns(tmp_path)
    launcher = LocalLauncher(tmp_path, tmp_path, tmp_path, "superlu")
    live = await runs.post_run(draft())
    beat(run_dir(tmp_path, live.id))
    await runs.update_run(live.id, RunPatch(status="running"))
    assert (await reap(runs, launcher, await runs.get_run(live.id))).status == "running"
    finished = await runs.post_run(draft())
    await runs.update_run(finished.id, RunPatch(status="done"))
    assert (await reap(runs, launcher, await runs.get_run(finished.id))).status == "done"


async def test_a_queued_run_has_no_heartbeat_yet_and_survives_reaping(tmp_path: Path) -> None:
    runs = FilesystemRuns(tmp_path)
    launcher = LocalLauncher(tmp_path, tmp_path, tmp_path, "superlu")
    posted = await runs.post_run(draft())
    assert (await reap(runs, launcher, posted)).status == "queued"


def install_draft() -> InstallDraft:
    return InstallDraft(source="uslci", actor=Actor(kind="person", name="carlos"), version="2024")


async def test_a_queued_install_whose_process_never_beat_fails_after_the_stale_time(
    tmp_path: Path,
) -> None:
    installs = MemoryInstalls()
    posted = await installs.post_install(install_draft())
    launcher = LocalInstaller(tmp_path)
    # a process that has just been started has not beaten yet, so the record holds
    assert (await reap_install(installs, launcher, posted)).status == "queued"
    after = posted.posted_at + timedelta(seconds=STALE_SECONDS + 1)
    reaped = await reap_install(installs, launcher, posted, now=after)
    assert reaped.status == "failed" and reaped.finished_at is not None
    assert reaped.error is not None and "did not finish" in reaped.error.message
    assert (await installs.get_install(posted.id)).status == "failed"


async def test_a_running_install_whose_process_is_gone_fails(tmp_path: Path) -> None:
    installs = MemoryInstalls()
    posted = await installs.post_install(install_draft())
    running = await installs.update_install(
        posted.id, InstallPatch(status="running", started_at=datetime.now(UTC))
    )
    reaped = await reap_install(installs, LocalInstaller(tmp_path), running)
    assert reaped.status == "failed"
    assert (await installs.get_install(posted.id)).status == "failed"


async def test_watch_install_publishes_each_move_and_returns_when_it_settles() -> None:
    installs = MemoryInstalls()
    posted = await installs.post_install(install_draft())
    bus = EventBus()
    queue = bus.subscribe_all()
    watching = asyncio.create_task(
        watch_install(bus, installs, MemoryInstaller([]), posted.id, interval=0.01)
    )
    await installs.update_install(
        posted.id, InstallPatch(status="running", progress=InstallProgress(step="fetch", count=2))
    )
    # several polls of one unchanged record publish it once
    await asyncio.sleep(0.05)
    await installs.update_install(posted.id, InstallPatch(status="done"))
    await asyncio.wait_for(watching, timeout=5)
    seen: list[Install] = []
    while not queue.empty():
        event = queue.get_nowait()
        assert event.kind == "install" and event.install is not None
        seen.append(event.install)
    statuses = [move.status for move in seen]
    assert statuses[-1] == "done"
    assert all(earlier != later for earlier, later in pairwise(statuses))
    assert any(move.progress is not None and move.progress.count == 2 for move in seen)
