from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="the tray's Windows adapter runs on Windows only",
)

if sys.platform == "win32":
    import winreg
    from importlib.metadata import version

    from ecosemantic.tray import windows
    from tests.tray.fakes import FakeLauncher, FakeStore

    windows.kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    windows.kernel32.TerminateProcess.restype = wintypes.BOOL
    from ecosemantic.tray.app import Tray
    from ecosemantic.tray.engine import Engine
    from ecosemantic.tray.home import Home, TraySettings

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
WM_QUERYENDSESSION = 0x0011
PROCESS_TERMINATE = 0x0001
RUN_VALUE = "EcoSemantic Engine (a test value)"
APPROVED_VALUE = "EcoSemantic Engine (a test switch)"
LAUNCHER_SCRIPT = """
import ctypes, sys

print(ctypes.windll.kernel32.GetConsoleWindow())
print(repr(sys.stdin.read()))
print('José Muñoz')
"""
TRAY_SCRIPT = r"""
import os, sys, time
from pathlib import Path

from ecosemantic.tray.windows import WindowsLauncher

folder = Path(sys.argv[1])
base = getattr(sys, "_base_executable", None) or sys.executable


def written(name: str, pid: int) -> None:
    staged = folder / f"{name}.tmp"
    staged.write_text(str(pid), encoding="utf-8")
    staged.replace(folder / name)


written("tray.pid", os.getpid())
WindowsLauncher().start(
    [
        base,
        "-X",
        "utf8",
        "-c",
        "import os, sys, time\nfrom pathlib import Path\n"
        "held = Path(sys.argv[1])\n"
        "staged = held.with_name('.child.pid.tmp')\n"
        "staged.write_text(str(os.getpid()), encoding='utf-8')\n"
        "staged.replace(held)\n"
        "time.sleep(120)",
        str(folder / "child.pid"),
    ],
    folder / "helper.log",
    contained=True,
)
time.sleep(120)
"""


def a_windows_tray(tmp_path: Path) -> tuple[Tray, windows.WindowsPlatform]:
    """A tray over this folder with this machine's own platform and launcher."""
    home = Home(tmp_path / "home")
    home.root.mkdir(parents=True)
    models = tmp_path / "models"
    models.mkdir()
    settings = TraySettings(databases=tmp_path / "databases", models=models)
    settings.write(home.settings)
    python = Path(sys.executable).with_name("python.exe")
    platform = windows.WindowsPlatform()
    engine = Engine(
        python=python,
        settings=settings,
        home=home,
        launcher=platform.launcher,
        health=lambda port: None,
        stopper=lambda host, port, folder: True,
        clock=time.monotonic,
        sleep=time.sleep,
    )
    return (
        Tray(
            engine=engine,
            platform=platform,
            home=home,
            python=python,
            store=FakeStore(),
        ),
        platform,
    )


def wrote(folder: Path) -> str:
    """What the helper wrote to its log, which a failure that reads it shows."""
    log = folder / "helper.log"
    return log.read_text(encoding="utf-8", errors="replace") if log.is_file() else "no log"


def running(pid: int) -> bool:
    """Whether the process this pid names is still running, asked of Windows itself."""
    handle = windows.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not windows.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise OSError(ctypes.get_last_error(), "GetExitCodeProcess failed")
        return code.value == STILL_ACTIVE
    finally:
        windows.kernel32.CloseHandle(handle)


def ended(pid: int) -> None:
    """End a process this test started."""
    handle = windows.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if handle:
        windows.kernel32.TerminateProcess(handle, 1)
        windows.kernel32.CloseHandle(handle)


def deleted(root: int, path: str, value: str) -> None:
    """Remove one value, whether or not the key or the value is there."""
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value)
    except FileNotFoundError:
        return


def test_the_clipboard_holds_the_connector_address_with_its_non_ascii_letters() -> None:
    address = "https://carlos.bridge.ecosemantic.com/mcp?handle=José Muñoz"
    windows.copy_text(address)
    seen = windows.clipboard_text()
    assert seen == address, f"the clipboard held {seen!r}"


def test_an_empty_clipboard_reads_as_no_text() -> None:
    windows.copy_text("")
    assert windows.clipboard_text() == ""


def test_the_run_value_is_written_read_and_deleted() -> None:
    platform = windows.WindowsPlatform(value=RUN_VALUE)
    try:
        platform.set_start_at_login(True)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.RUN_KEY) as key:
            written, kind = winreg.QueryValueEx(key, RUN_VALUE)
        assert (written, kind) == (platform.command, winreg.REG_SZ), (written, kind)
        read = platform.start_at_login()
        assert read.enabled is True, read
        platform.set_start_at_login(False)
        after = platform.start_at_login()
        assert after.enabled is False, after
        with pytest.raises(FileNotFoundError):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, windows.RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
    finally:
        deleted(winreg.HKEY_CURRENT_USER, windows.RUN_KEY, RUN_VALUE)


def test_windows_own_switch_is_read_from_startup_approved() -> None:
    platform = windows.WindowsPlatform(value=APPROVED_VALUE)
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, windows.APPROVED_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, APPROVED_VALUE, 0, winreg.REG_BINARY, bytes([0x03]) + b"\0" * 11)
    try:
        platform.set_start_at_login(True)
        turned_off = platform.start_at_login()
        assert turned_off.turned_off_by_windows is True, turned_off
        assert turned_off.enabled is False, turned_off
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, windows.APPROVED_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APPROVED_VALUE, 0, winreg.REG_BINARY, bytes([0x02]) + b"\0" * 11)
        allowed = platform.start_at_login()
        assert allowed.turned_off_by_windows is False, allowed
        assert allowed.enabled is True, allowed
    finally:
        deleted(winreg.HKEY_CURRENT_USER, windows.APPROVED_KEY, APPROVED_VALUE)
        deleted(winreg.HKEY_CURRENT_USER, windows.RUN_KEY, APPROVED_VALUE)


def test_a_run_value_windows_never_approved_counts_as_on() -> None:
    platform = windows.WindowsPlatform(value=APPROVED_VALUE)
    try:
        platform.set_start_at_login(True)
        read = platform.start_at_login()
        assert read.enabled is True and read.turned_off_by_windows is False, read
    finally:
        deleted(winreg.HKEY_CURRENT_USER, windows.RUN_KEY, APPROVED_VALUE)


def test_the_launcher_starts_python_without_a_window_and_logs_its_output(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "EcoSemantic José Muñoz"
    folder.mkdir()
    log = folder / "engine.log"
    process = windows.WindowsLauncher().start(
        [sys.executable, "-X", "utf8", "-c", LAUNCHER_SCRIPT], log, contained=True
    )
    code = process.wait(timeout=120)
    written = log.read_text(encoding="utf-8").splitlines()
    assert code == 0, (code, written)
    assert written == ["0", "''", "José Muñoz"], written


def test_a_child_ends_when_the_tray_that_started_it_is_ended(tmp_path: Path) -> None:
    """A tray of its own starts a long child in a job; ending that tray's own process, as Task
    Manager does, must take the child with it. The tray is started with this venv's interpreter,
    which imports the core and writes its own pid, and the child it starts is standard-library code
    the base interpreter runs, so no launcher sits between either pid and the process it names."""
    folder = tmp_path / "job"
    folder.mkdir()
    tray = subprocess.Popen([sys.executable, "-c", TRAY_SCRIPT, str(folder)])
    tray_pid: int | None = None
    child: int | None = None
    try:
        deadline = time.monotonic() + 60
        while not ((folder / "tray.pid").is_file() and (folder / "child.pid").is_file()):
            code = tray.poll()
            assert code is None, f"the helper ended {code}: {wrote(folder)}"
            assert time.monotonic() < deadline, f"the helper never wrote both pids: {wrote(folder)}"
            time.sleep(0.1)
        tray_pid = int((folder / "tray.pid").read_text(encoding="utf-8"))
        child = int((folder / "child.pid").read_text(encoding="utf-8"))
        assert running(child), "the child did not start"
        ended(tray_pid)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and running(child):
            time.sleep(0.2)
        assert not running(child), (
            f"the child outlived the tray at {tray_pid}, which ended {tray.poll()}"
        )
    finally:
        if tray.poll() is None:
            tray.kill()
            tray.wait(timeout=60)
        if child is not None and running(child):
            ended(child)


def test_the_icon_lets_windows_end_the_session(tmp_path: Path) -> None:
    tray, platform = a_windows_tray(tmp_path)
    asked: list[bool] = []
    tray.engine.stopper = lambda host, port, folder: asked.append(True) or True
    showing = windows.Showing(tray, platform, interval=0.02)
    stopped = showing.icon.title
    tray.engine.launcher = FakeLauncher()
    tray.engine.health = lambda port: {
        "bridge": {"state": "connected", "handle": "ana", "page": "", "connector": ""}
    }
    tray.engine.start()
    showing.icon._message_handlers.update(windows.session_handlers(tray))
    running_icon = threading.Thread(target=showing.run, daemon=True)
    running_icon.start()
    try:
        deadline = time.monotonic() + 30
        while not showing.icon._running:
            assert time.monotonic() < deadline, "the icon never started its loop"
            time.sleep(0.1)
        windows.user32.SendMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        windows.user32.SendMessageW.restype = ctypes.c_ssize_t
        wanted = windows.clipped(f"{windows.APP} — Connected as ana", windows.TOOLTIP_UNITS)
        deadline = time.monotonic() + 30
        while showing.icon.title != wanted:
            assert time.monotonic() < deadline, (
                f"the poll never drew the connected state: the icon reads {showing.icon.title!r}"
            )
            time.sleep(0.02)
        assert showing.icon.title != stopped, showing.icon.title
        answer = windows.user32.SendMessageW(showing.icon._hwnd, WM_QUERYENDSESSION, 0, 0)
        assert answer == 1, answer
        ended = windows.user32.SendMessageW(showing.icon._hwnd, windows.WM_ENDSESSION, 1, 0)
        assert ended == 0, ended
        assert asked == [True], asked
        windows.user32.SendMessageW(showing.icon._hwnd, windows.WM_ENDSESSION, 1, 0)
        assert asked == [True], asked
    finally:
        showing.icon.stop()
        running_icon.join(timeout=30)
        assert not running_icon.is_alive(), "the tray's own thread outlived its quit"
    log = tmp_path / "home" / "logs" / "tray.log"
    drawn = log.read_text(encoding="utf-8") if log.is_file() else "the tray wrote no log"
    assert not log.is_file(), drawn


def test_the_pystray_the_handlers_reach_is_the_pinned_one() -> None:
    assert version("pystray") == "0.19.5", version("pystray")


class Recorded:
    """An icon that records the notifications it is given."""

    def __init__(self) -> None:
        self.notified: list[tuple[str | None, str]] = []

    def notify(self, message: str, title: str | None = None) -> None:
        self.notified.append((title, message))


def test_a_notice_waits_for_the_flush_the_tray_s_setup_runs(tmp_path: Path) -> None:
    platform = windows.WindowsPlatform(value=RUN_VALUE)
    icon = Recorded()
    platform.showing(icon)
    platform.notify(title="a title", text="a text")
    assert icon.notified == [], icon.notified
    platform.flush()
    assert icon.notified == [("a title", "a text")], icon.notified
    platform.notify(title="another", text="notice")
    assert icon.notified[-1] == ("another", "notice"), icon.notified
