"""Where a run lives on disk: one directory per run under the systems directory, and the
heartbeat its worker beats there."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread

RUNS_DIR = "runs"
RECORD_FILE = "run.json"
LOG_FILE = "worker.log"
HEARTBEAT_FILE = "heartbeat"


def run_dir(root: Path, run_id: uuid.UUID) -> Path:
    """The directory of one run under a systems directory, whether or not it exists yet."""
    return root / RUNS_DIR / str(run_id)


def beat(folder: Path) -> None:
    """Mark the worker carrying the run in this folder as alive now, by the heartbeat file's
    modification time."""
    (folder / HEARTBEAT_FILE).touch()


def heartbeat_age(folder: Path) -> float | None:
    """Seconds since the worker carrying the run in this folder last beat, or None when it never
    has."""
    heartbeat = folder / HEARTBEAT_FILE
    if not heartbeat.is_file():
        return None
    return time.time() - heartbeat.stat().st_mtime


@contextmanager
def beating(folder: Path, every: float) -> Iterator[None]:
    """Beat this folder's heartbeat every `every` seconds until the block ends, so a step that
    reports nothing does not look like a process that is gone."""
    stop = Event()

    def keep_beating() -> None:
        while not stop.wait(every):
            beat(folder)

    beater = Thread(target=keep_beating, daemon=True)
    beater.start()
    try:
        yield
    finally:
        stop.set()
        beater.join()
