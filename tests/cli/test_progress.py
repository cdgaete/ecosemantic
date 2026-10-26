from __future__ import annotations

import io

import pytest

from ecosemantic.cli.progress import printer
from ecosemantic.ports.types import InstallProgress


def test_printer_writes_one_line_per_step_with_its_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = iter([107.0, 165.5, 165.5])
    monkeypatch.setattr("ecosemantic.cli.progress.time.monotonic", lambda: next(moments))
    stream = io.StringIO()

    report = printer(stream, 100.0)
    report(InstallProgress(step="downloading"))
    report(InstallProgress(step="downloaded", count=12_340_000))
    report(InstallProgress(step="checking", count=7))

    assert stream.getvalue().splitlines() == [
        "[0:07] downloading",
        "[1:05] downloaded 12.3 MB",
        "[1:05] checking 7",
    ]
