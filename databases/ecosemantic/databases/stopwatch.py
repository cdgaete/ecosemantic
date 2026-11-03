"""Seconds each step of a run took."""

from __future__ import annotations

import time


class Stopwatch:
    """Records the seconds between one lap and the last, starting at its own creation."""

    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}
        self._started = time.perf_counter()

    def lap(self, step: str) -> None:
        """Record the seconds since the last lap under `step`."""
        now = time.perf_counter()
        self.seconds[step] = now - self._started
        self._started = now
