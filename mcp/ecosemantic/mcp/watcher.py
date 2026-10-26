"""The server's view of a run or an install in another process: poll the record, publish what
changed, and settle one whose process is gone."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from ecosemantic.errors import failure_payload
from ecosemantic.events import Event, EventBus
from ecosemantic.ports.install import InstallLauncher, InstallPort
from ecosemantic.ports.run import RunLauncher, RunPort
from ecosemantic.ports.types import STALE_SECONDS, Install, InstallPatch, Run, RunPatch

INTERVAL = 1.0
T = TypeVar("T")


async def reap(runs: RunPort, launcher: RunLauncher, run: Run) -> Run:
    """The run as it stands, or failed when it claims to be running and its worker is gone."""
    if run.status != "running" or launcher.alive(run.id):
        return run
    return await runs.update_run(
        run.id,
        RunPatch(
            status="failed",
            error=failure_payload(f"the worker for run {run.id} did not finish"),
            finished_at=datetime.now(UTC),
        ),
    )


async def reap_install(
    installs: InstallPort,
    launcher: InstallLauncher,
    install: Install,
    now: datetime | None = None,
) -> Install:
    """The install as it stands, or failed when its process is gone: a running one at once, and a
    queued one once it has stood posted for `STALE_SECONDS` without a beat, so a process that dies
    before its first beat holds no data directory."""
    at = datetime.now(UTC) if now is None else now
    if not install.open or launcher.alive(install.id):
        return install
    if install.status == "queued" and at - install.posted_at < timedelta(seconds=STALE_SECONDS):
        return install
    return await installs.update_install(
        install.id,
        InstallPatch(
            status="failed",
            error=failure_payload(f"the process for install {install.id} did not finish"),
            finished_at=at,
        ),
    )


async def poll(
    read: Callable[[], Awaitable[T]],
    publish: Callable[[T], None],
    settled: Callable[[T], bool],
    interval: float,
) -> None:
    """Publish each state the read answers that differs from the one before, and return once the
    open test says the record is settled."""
    before: T | None = None
    while True:
        now = await read()
        if now != before:
            publish(now)
            before = now
        if settled(now):
            return
        await asyncio.sleep(interval)


async def watch(
    bus: EventBus,
    runs: RunPort,
    launcher: RunLauncher,
    run_id: uuid.UUID,
    interval: float = INTERVAL,
) -> None:
    """Publish the run whenever it moves, and return once it is no longer open.

    The worker is another process and the bus is this one's, so the record is the only
    thing both can see.
    """

    async def read() -> Run:
        return await reap(runs, launcher, await runs.get_run(run_id))

    def publish(run: Run) -> None:
        bus.publish(Event(kind="run", product_system_id=run.product_system_id, run=run))

    await poll(read, publish, lambda run: not run.open, interval)


async def watch_install(
    bus: EventBus,
    installs: InstallPort,
    launcher: InstallLauncher,
    install_id: uuid.UUID,
    interval: float = INTERVAL,
) -> None:
    """Publish the install whenever it moves, and return once it is no longer open, as `watch`
    follows a run."""

    async def read() -> Install:
        return await reap_install(installs, launcher, await installs.get_install(install_id))

    def publish(install: Install) -> None:
        bus.publish(Event(kind="install", install=install))

    await poll(read, publish, lambda install: not install.open, interval)
