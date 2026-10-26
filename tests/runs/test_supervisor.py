from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.run_folder import HEARTBEAT_FILE, beat, run_dir
from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.mcp.calculation import demand_of
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.ports.types import MonteCarloConfig, RunDraft
from ecosemantic.runs.supervisor import (
    STALE_SECONDS,
    WINDOWS_DETACHED,
    LocalLauncher,
    start_detached,
)


class Started:
    pid = 4242


def child_writing(target: Path, value: str) -> list[str]:
    """A command for a python child that writes one expression's value to a file."""
    return [
        sys.executable,
        "-c",
        f"import os, pathlib, sys; pathlib.Path({str(target)!r}).write_bytes({value})",
    ]


def await_written(path: Path, expected: bytes) -> bytes:
    """The content the child wrote, once it is the expected one or the wait is over."""
    deadline = time.monotonic() + 60
    found = b""
    while time.monotonic() < deadline:
        if path.is_file():
            found = path.read_bytes()
            if found == expected:
                return found
        time.sleep(0.05)
    return found


def started_on(platform: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """The keyword arguments the launcher hands Popen on one platform, nothing started."""
    seen: dict[str, object] = {}

    def popen(command: list[str], **kwargs: object) -> Started:
        seen.update(kwargs)
        return Started()

    monkeypatch.setattr("ecosemantic.runs.supervisor.subprocess.Popen", popen)
    monkeypatch.setattr("ecosemantic.runs.supervisor.sys.platform", platform)
    assert LocalLauncher(tmp_path, tmp_path, tmp_path, "superlu").start(uuid.uuid4()) == 4242
    return seen


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_worker_starts_in_a_session_of_its_own_on_posix(
    platform: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = started_on(platform, tmp_path, monkeypatch)
    assert seen["start_new_session"] is True and "creationflags" not in seen


def test_a_worker_starts_in_a_process_group_of_its_own_with_no_console_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = started_on("win32", tmp_path, monkeypatch)
    # CREATE_NEW_PROCESS_GROUP 0x200 and DETACHED_PROCESS 0x8
    assert seen["creationflags"] == WINDOWS_DETACHED == 0x208
    assert "start_new_session" not in seen


def test_a_run_is_alive_while_its_heartbeat_is_fresh(tmp_path: Path) -> None:
    run_id = uuid.uuid4()
    launcher = LocalLauncher(tmp_path, tmp_path, tmp_path, "superlu")
    # a run whose worker never beat is not alive
    assert launcher.alive(run_id) is False
    folder = run_dir(tmp_path, run_id)
    folder.mkdir(parents=True)
    beat(folder)
    assert launcher.alive(run_id) is True
    stale = time.time() - STALE_SECONDS - 1
    os.utime(folder / HEARTBEAT_FILE, (stale, stale))
    assert launcher.alive(run_id) is False
    beat(folder)
    assert launcher.alive(run_id) is True


def test_start_detached_hands_the_child_its_standard_input_then_end_of_file(
    tmp_path: Path,
) -> None:
    read = tmp_path / "read"

    pid = start_detached(
        child_writing(read, "sys.stdin.buffer.read()"),
        tmp_path / "worker.log",
        stdin=b"the whole input",
    )

    assert pid > 0
    assert await_written(read, b"the whole input") == b"the whole input"


def test_start_detached_runs_the_child_in_the_environment_it_is_given(tmp_path: Path) -> None:
    read = tmp_path / "read"

    start_detached(
        child_writing(read, 'os.environ.get("ONLY_THIS", "").encode()'),
        tmp_path / "worker.log",
        environment={"ONLY_THIS": "yes"},
    )

    assert await_written(read, b"yes") == b"yes"


async def test_the_local_launcher_spawns_a_worker_that_finishes_the_run(
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
    context: ServerContext,
) -> None:
    runs = FilesystemRuns(tmp_path)
    methods = await context.inventory.list_methods(fixture_system_stored.database.name, None)
    posted = await runs.post_run(
        RunDraft(
            product_system_id=fixture_system_stored.id,
            at_hash=content_hash(fixture_system_stored),
            demand=demand_of(fixture_system_stored, None),
            methods=methods[:1],
            config=MonteCarloConfig(n=2, n_min=1, seed=12345),
        )
    )
    pid = LocalLauncher(systems_dir, bundle_dir, tmp_path, "superlu").start(posted.id)
    assert pid > 0
    deadline = time.monotonic() + 120
    run = await runs.get_run(posted.id)
    while run.open and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        run = await runs.get_run(posted.id)
    assert run.status == "done" and run.result is not None
    assert (tmp_path / "runs" / str(posted.id) / "worker.log").is_file()
    assert (tmp_path / "runs" / str(posted.id) / HEARTBEAT_FILE).is_file()
