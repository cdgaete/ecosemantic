"""What a directory tree reports as it is written, for the backends that keep their records in
one."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from watchfiles._rust_notify import RustNotify

_DEBOUNCE_MS = 200
_STEP_MS = 50
_TIMEOUT_MS = 5_000


def touched(root: Path) -> AsyncIterator[set[Path]]:
    """Every batch of paths written under a directory, from the moment this is called.

    The watch is armed before this returns, so a write made before the first batch is read is
    reported. A directory that does not exist yet is created, because a store is a directory its
    first write creates.
    """
    root.mkdir(parents=True, exist_ok=True)
    watcher = RustNotify([str(root)], False, False, _STEP_MS, True, False)
    return _batches(watcher)


async def _batches(watcher: RustNotify) -> AsyncIterator[set[Path]]:
    """The watcher's batches, each read on a worker thread. A read that times out is read again;
    one that answers `stop` ends the batches. Closing the iterator stops the read in flight
    within a step and closes the watcher."""
    stop = threading.Event()
    try:
        while True:
            raw = await asyncio.to_thread(watcher.watch, _DEBOUNCE_MS, _STEP_MS, _TIMEOUT_MS, stop)
            if raw == "timeout":
                continue
            if isinstance(raw, str):
                return
            yield {Path(path) for _, path in raw}
    finally:
        stop.set()
        watcher.close()
