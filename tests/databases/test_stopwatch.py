from __future__ import annotations

import time

import pytest

from ecosemantic.databases.stopwatch import Stopwatch


def test_a_lap_records_the_seconds_since_the_last(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter([1.0, 3.0, 4.5])
    monkeypatch.setattr(time, "perf_counter", lambda: next(readings))
    stopwatch = Stopwatch()
    stopwatch.lap("a")
    stopwatch.lap("b")
    assert stopwatch.seconds == {"a": 2.0, "b": 1.5}
