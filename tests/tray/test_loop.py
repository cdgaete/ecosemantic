from __future__ import annotations

import threading
import time as systime
from pathlib import Path

import pytest

from ecosemantic.errors import Unavailable
from ecosemantic.tray.loop import (
    TEXT_UNITS,
    TITLE_UNITS,
    TOOLTIP_UNITS,
    Loop,
    clipped,
    units,
)
from tests.tray.test_app import CONNECTED, a_tray


def test_a_notification_is_clipped_to_what_pystray_keeps() -> None:
    assert clipped("a short line", TITLE_UNITS) == "a short line"
    assert clipped("y" * TITLE_UNITS, TITLE_UNITS) == "y" * TITLE_UNITS
    longer = clipped("z" * (TITLE_UNITS + 10), TITLE_UNITS)
    assert units(longer) == TITLE_UNITS
    assert longer.endswith("…")
    assert units(clipped("w" * (TEXT_UNITS + 10), TEXT_UNITS)) == TEXT_UNITS
    astral = clipped("🌍" * 40, TITLE_UNITS)
    assert units(astral) == TITLE_UNITS, units(astral)
    assert astral.endswith("…")
    assert len(astral) < TITLE_UNITS


def test_an_unavailable_address_is_written_and_told_and_the_worker_goes_on(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health_document=CONNECTED)
    engine.start()
    tray.state()

    def refusing(text: str) -> None:
        raise Unavailable("OpenClipboard failed: access is denied")

    platform.copy = refusing
    loop = Loop(tray=tray, draw=lambda state: None, stop_icon=lambda: None)
    loop.asked("copy-connector")
    loop.asked("open-logs")
    loop.stopped()
    loop.worked()
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert "OpenClipboard failed" in written, written
    assert platform.notices == [("EcoSemantic Engine", "OpenClipboard failed: access is denied")]
    assert platform.folders == [home.logs]


def test_an_os_error_an_action_raises_is_written_and_the_worker_stays(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)

    def refusing(path: Path) -> None:
        raise OSError(2, "the shell could not open the folder")

    platform.open_folder = refusing
    loop = Loop(tray=tray, draw=lambda state: None, stop_icon=lambda: None)
    loop.asked("open-logs")
    loop.asked("quit")
    loop.stopped()
    loop.worked()
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert "[Errno 2] the shell could not open the folder" in written, written
    assert "Traceback (most recent call last)" in written, written
    assert platform.notices[0][0] == "EcoSemantic Engine"
    assert "The tray could not finish" in platform.notices[0][1]
    assert tray.quit_requested is True


def test_the_poll_keeps_polling_and_writes_each_distinct_error_once(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)
    trouble = {"kind": OSError, "reason": "the clipboard is held by another program"}

    def failing(state: object) -> None:
        if trouble["kind"] is ValueError:
            raise ValueError(trouble["reason"])
        raise OSError(5, trouble["reason"])

    loop = Loop(
        tray=tray,
        draw=failing,
        stop_icon=lambda: None,
        wait_seconds=0.01,
    )
    polling = threading.Thread(target=loop.polled)
    polling.start()
    try:
        _waited(home, "the clipboard is held by another program")
        trouble["kind"] = ValueError
        _waited(home, "ValueError: the clipboard is held by another program")
        trouble["kind"] = OSError
        trouble["reason"] = "the clipboard belongs to another window"
        _waited(home, "the clipboard belongs to another window")
    finally:
        loop.stopped()
        polling.join(timeout=10)
    assert not polling.is_alive()
    written = _written(home)
    assert (
        written.count("OSError: [Errno 5] the clipboard is held by another program\nTraceback") == 1
    )
    # the same words under another type are another error
    assert written.count("ValueError: the clipboard is held by another program\nTraceback") == 1, (
        written
    )
    assert (
        written.count("OSError: [Errno 5] the clipboard belongs to another window\nTraceback") == 1
    )
    assert len(platform.notices) == 3, platform.notices


def _waited(home: object, line: str) -> None:
    """Wait until the tray's log holds this line, or fail after ten seconds."""
    deadline = systime.monotonic() + 10
    while line not in _written(home):
        assert systime.monotonic() < deadline, f"the log never held {line!r}: {_written(home)!r}"
        systime.sleep(0.02)


def _written(home: object) -> str:
    log = home.logs / "tray.log"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


def test_each_failed_action_is_written_and_told(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)

    def refusing(path: Path) -> None:
        raise OSError(2, "the shell could not open the folder")

    platform.open_folder = refusing
    loop = Loop(tray=tray, draw=lambda state: None, stop_icon=lambda: None)
    loop.asked("open-logs")
    loop.asked("open-logs")
    loop.stopped()
    loop.worked()
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert written.count("[Errno 2] the shell could not open the folder\nTraceback") == 2, written
    assert len(platform.notices) == 2, platform.notices


def test_a_report_that_itself_fails_goes_to_standard_error_and_the_worker_goes_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)

    def refusing(path: Path) -> None:
        raise OSError(2, "the shell could not open the folder")

    def refusing_notice(title: str, text: str) -> None:
        raise OSError(5, "the notification area is busy")

    platform.open_folder = refusing
    platform.notify = refusing_notice
    loop = Loop(tray=tray, draw=lambda state: None, stop_icon=lambda: None)
    loop.asked("open-logs")
    loop.asked("quit")
    loop.stopped()
    loop.worked()
    printed = capsys.readouterr().err
    assert "the tray could not report" in printed, printed
    assert "the notification area is busy" in printed, printed
    assert tray.quit_requested is True


def test_a_lone_surrogate_counts_as_the_one_unit_it_is() -> None:
    lone = "a\ud800b"
    assert units(lone) == 3
    assert clipped(lone, 3) == lone
    cut = clipped(lone, 2)
    assert units(cut) == 2, cut
    assert cut == "a…"


def test_the_tooltip_is_clipped_to_pystray_s_field() -> None:
    long_title = "Connected as " + "a" * 200
    assert units(clipped(long_title, TOOLTIP_UNITS)) == TOOLTIP_UNITS
    assert clipped(long_title, TOOLTIP_UNITS).startswith("Connected as a")
