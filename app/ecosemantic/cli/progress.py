"""A command's progress, one line per step on standard error."""

from __future__ import annotations

import time
from typing import TextIO

from ecosemantic.ports.types import InstallProgress, Reporter


def printer(stream: TextIO, started: float) -> Reporter:
    """A reporter that writes one line per step to `stream`: the time since `started` as minutes and
    seconds, the step's name, its count when it carries one, and a download's size in MB with one
    decimal."""

    def report(progress: InstallProgress) -> None:
        elapsed = int(time.monotonic() - started)
        line = f"[{elapsed // 60}:{elapsed % 60:02d}] {progress.step}"
        if progress.count is not None:
            line += f" {_counted(progress.step, progress.count)}"
        print(line, file=stream, flush=True)

    return report


def _counted(step: str, count: int) -> str:
    """A step's count as a person reads it: a download's bytes in megabytes, any other count as it
    stands."""
    return f"{count / 1_000_000:.1f} MB" if step == "downloaded" else str(count)
