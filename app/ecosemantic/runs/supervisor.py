"""Starting the process that carries a run or an install on this machine, and asking whether it
still runs."""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import IO, cast

from ecosemantic.backends.filesystem.run_folder import LOG_FILE, heartbeat_age, run_dir
from ecosemantic.ports.types import STALE_SECONDS

WINDOWS_DETACHED = 0x00000200 | 0x00000008


def start_detached(
    command: list[str],
    log: Path,
    stdin: bytes | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Start a process that outlives the caller, its output kept in the log and its standard input
    written whole from the bytes given, and answer its process id.

    Neither a signal to the caller nor its console closing takes the process with it: in a session
    of its own on POSIX, and on Windows in a process group of its own with no console,
    `WINDOWS_DETACHED` being CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS. A process given no
    bytes inherits the caller's standard input, and one given no environment inherits the
    caller's environment, as `subprocess.Popen` does when neither is passed.
    """
    with log.open("ab") as handle:
        pipe = None if stdin is None else subprocess.PIPE
        held = None if environment is None else dict(environment)
        if sys.platform == "win32":
            started = subprocess.Popen(
                command,
                stdin=pipe,
                stdout=handle,
                stderr=handle,
                env=held,
                creationflags=WINDOWS_DETACHED,
            )
        else:
            started = subprocess.Popen(
                command,
                stdin=pipe,
                stdout=handle,
                stderr=handle,
                env=held,
                start_new_session=True,
            )
    if stdin is not None:
        held_input = cast(IO[bytes], started.stdin)
        held_input.write(stdin)
        held_input.close()
    return started.pid


class LocalLauncher:
    """Carries each run in a worker process on this machine, over the directories the server
    binds and under its solver."""

    def __init__(self, systems: Path, data: Path, runs_root: Path, solver: str) -> None:
        self.systems = systems
        self.data = data
        self.runs_root = runs_root
        self.solver = solver

    def start(self, run_id: uuid.UUID) -> int:
        """Spawn the worker for one run and answer its process id, with its output kept beside
        it."""
        folder = run_dir(self.runs_root, run_id)
        folder.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "ecosemantic.runs.worker",
            "--systems-dir",
            str(self.systems),
            "--data-dir",
            str(self.data),
            "--runs-dir",
            str(self.runs_root),
            "--run",
            str(run_id),
            "--solver",
            self.solver,
        ]
        return start_detached(command, folder / LOG_FILE)

    def alive(self, run_id: uuid.UUID) -> bool:
        """Whether the worker carrying this run beat its heartbeat within `STALE_SECONDS`, which
        holds a run's longest silent stretch many times over (`NOTES.md`)."""
        age = heartbeat_age(run_dir(self.runs_root, run_id))
        return age is not None and age <= STALE_SECONDS
