from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from filelock import FileLock

from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.settings import derived_port
from ecosemantic.tray.__main__ import (
    _engine,
    _gone,
    checked,
    interpreter,
    main,
    quit_tray,
    streams_to,
)
from ecosemantic.tray.app import Tray
from ecosemantic.tray.engine import LOG_BYTES
from ecosemantic.tray.home import APP, Home, TraySettings, home_for, login_command, written
from tests.tray.fakes import FakePlatform, Time

PAGE = "https://ana.bridge.example"


def a_home(tmp_path: Path) -> Home:
    home = Home(tmp_path / "home")
    home.root.mkdir(parents=True)
    return home


def settings_for(tmp_path: Path, **named: object) -> TraySettings:
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    return TraySettings(databases=tmp_path / "databases", models=models, **named)


def test_the_folder_is_named_by_the_local_application_data() -> None:
    with pytest.raises(Invalid, match="LOCALAPPDATA"):
        home_for({})
    named = home_for({"LOCALAPPDATA": "/home/person/AppData/Local"})
    assert named.root == Path("/home/person/AppData/Local/EcoSemantic Engine")
    assert named.logs == named.root / "logs"


def test_the_standard_streams_a_windowless_interpreter_lacks_go_to_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = a_home(tmp_path)
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    streams_to(home)
    assert sys.stdout is not None and sys.stderr is not None and sys.stdin is not None
    sys.stdout.write("the tray speaks\n")
    sys.stdout.flush()
    assert "the tray speaks" in (home.logs / "tray.log").read_text(encoding="utf-8")
    assert sys.stdin.read() == ""


def test_the_console_interpreter_is_found_beside_the_windowless_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    windowless = tmp_path / "pythonw.exe"
    windowless.write_text("", encoding="utf-8")
    console = tmp_path / "python.exe"
    console.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(windowless))
    assert interpreter() == console
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(sys, "executable", str(elsewhere / "pythonw.exe"))
    with pytest.raises(Invalid, match="python.exe is missing"):
        interpreter()


def test_quit_asks_the_engine_the_settings_name_and_leaves_a_free_folder(
    tmp_path: Path,
) -> None:
    home = a_home(tmp_path)
    settings = settings_for(tmp_path)
    settings.write(home.settings)
    asked: list[tuple[str, int, Path]] = []
    assert (
        quit_tray(
            home,
            ask=lambda host, port, folder: asked.append((host, port, folder)) or True,
            health=lambda port: None,
        )
        == 0
    )
    assert asked == [("127.0.0.1", derived_port(settings.models), settings.models)]


def test_quit_with_no_settings_asks_no_engine(tmp_path: Path) -> None:
    home = a_home(tmp_path)
    asked: list[tuple[str, int, Path]] = []
    assert (
        quit_tray(
            home,
            ask=lambda host, port, folder: asked.append((host, port, folder)) or True,
            health=lambda port: None,
        )
        == 0
    )
    assert asked == []


def test_quit_asks_no_engine_whose_folder_is_gone(tmp_path: Path) -> None:
    home = a_home(tmp_path)
    TraySettings(databases=tmp_path / "databases", models=tmp_path / "gone").write(home.settings)
    assert quit_tray(home, ask=lambda host, port, folder: True, health=lambda port: None) == 0


def test_a_settings_file_that_cannot_be_read_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = a_home(tmp_path)
    home.settings.write_text("{ not settings", encoding="utf-8")
    assert quit_tray(home) == 4
    printed = capsys.readouterr().err
    assert str(home.settings) in printed and "cannot be read" in printed


def test_an_engine_that_keeps_answering_health_stops_the_quit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = a_home(tmp_path)
    settings = settings_for(tmp_path)
    settings.write(home.settings)
    answered = {"bridge": {"state": "connected", "handle": "ana"}}
    time_ = Time()
    assert (
        quit_tray(
            home,
            ask=lambda host, port, folder: True,
            health=lambda port: answered,
            clock=time_.clock,
            sleep=time_.sleep,
        )
        == 3
    )
    assert time_.now >= 10
    printed = capsys.readouterr().err
    assert str(derived_port(settings.models)) in printed
    assert "still answers" in printed


def test_a_stale_pid_is_removed_and_its_process_left_alone(tmp_path: Path) -> None:
    home = a_home(tmp_path)
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        home.pid.write_text(f"{unrelated.pid}\n", encoding="utf-8")
        assert quit_tray(home, ask=lambda host, port, folder: True, health=lambda port: None) == 0
        assert not home.pid.exists()
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait()


def test_a_pid_that_no_longer_exists_is_already_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = a_home(tmp_path)

    def gone_pid(pid: int, number: int) -> None:
        if sys.platform == "win32":
            invalid = OSError(22, "Invalid argument")
            invalid.winerror = 87
            raise invalid
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(os, "kill", gone_pid)
    home.pid.write_text("4242\n", encoding="utf-8")
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    time_ = Time()
    try:
        assert (
            quit_tray(
                home,
                ask=lambda host, port, folder: True,
                health=lambda port: None,
                clock=time_.clock,
                sleep=time_.sleep,
            )
            == 3
        )
    finally:
        held.release()
    assert time_.now >= 15


def test_a_pid_file_that_cannot_be_read_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = a_home(tmp_path)
    home.pid.write_text("not a pid", encoding="utf-8")
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    try:
        assert quit_tray(home, ask=lambda host, port, folder: True, health=lambda port: None) == 3
    finally:
        held.release()
    printed = capsys.readouterr().err
    assert str(home.pid) in printed and "cannot be read" in printed


def test_ending_a_pid_the_person_may_not_open_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = a_home(tmp_path)
    home.pid.write_text("4242\n", encoding="utf-8")

    def refused(pid: int, number: int) -> None:
        raise PermissionError(1, "the process is owned by another account")

    monkeypatch.setattr("os.kill", refused)
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    try:
        assert quit_tray(home, ask=lambda host, port, folder: True, health=lambda port: None) == 3
    finally:
        held.release()
    printed = capsys.readouterr().err
    assert "4242" in printed and "another account" in printed


def test_a_gone_pid_is_recognized_on_each_platform() -> None:
    invalid = OSError(22, "Invalid argument")
    invalid.winerror = 87
    assert _gone(ProcessLookupError())
    assert _gone(invalid)
    assert not _gone(PermissionError(13, "Permission denied"))


def test_quit_answers_three_when_the_lock_never_comes_free(tmp_path: Path) -> None:
    home = a_home(tmp_path)
    time_ = Time()
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    try:
        assert (
            quit_tray(
                home,
                ask=lambda host, port, folder: True,
                health=lambda port: None,
                clock=time_.clock,
                sleep=time_.sleep,
            )
            == 3
        )
    finally:
        held.release()
    assert time_.now >= 15


def test_the_engine_is_built_from_the_settings_and_the_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = a_home(tmp_path)
    settings = settings_for(tmp_path)
    settings.write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    platform = FakePlatform()
    engine = _engine(home, platform, settings, tmp_path / "python.exe")
    assert engine.settings.models == tmp_path / "models"
    assert engine.launcher is platform.launcher
    assert engine.port > 0


def test_quit_from_the_command_line_leaves_a_free_folder(tmp_path: Path) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    assert main(["--quit"], environ) == 0
    assert home.logs.is_dir()


def test_importing_the_tray_loads_no_server() -> None:
    script = (
        "import sys\n"
        "import ecosemantic.tray.__main__\n"
        "heavy = sorted(\n"
        "    name\n"
        "    for name in sys.modules\n"
        "    if name.split('.')[0] in {'numpy', 'scipy', 'uvicorn', 'starlette', 'fastmcp'}\n"
        "    or name.startswith(('ecosemantic.view', 'ecosemantic.mcp', 'ecosemantic.serve'))\n"
        ")\n"
        "print(heavy)\n"
    )
    ran = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "[]", ran.stdout


def test_a_tray_whose_settings_are_missing_refuses_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    platform = FakePlatform()
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (platform, lambda tray: None),
    )
    assert main([], environ) == 1
    assert str(home.settings) in capsys.readouterr().err
    assert platform.refusals and str(home.settings) in platform.refusals[0][1]
    assert platform.notices == []
    assert not home.pid.exists()


def test_a_tray_whose_settings_cannot_be_read_writes_the_refusal_to_its_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    home.settings.write_text("{ not settings", encoding="utf-8")
    platform = FakePlatform()
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (platform, lambda tray: None),
    )
    monkeypatch.setattr(sys, "stderr", None)
    assert main([], environ) == 1
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert str(home.settings) in written and "cannot be read" in written


def test_only_the_tray_that_runs_rotates_its_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    oversized = home.logs / "tray.log"
    oversized.write_bytes(b"x" * (LOG_BYTES + 1))
    assert main(["--quit"], environ) == 0
    assert oversized.stat().st_size == LOG_BYTES + 1
    assert not (home.logs / "tray.log.1").exists()
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    try:
        monkeypatch.setattr(
            "ecosemantic.tray.__main__.platform_and_runner",
            lambda: (FakePlatform(), lambda tray: None),
        )
        assert main([], environ) == 0
    finally:
        held.release()
    assert oversized.stat().st_size == LOG_BYTES + 1
    assert not (home.logs / "tray.log.1").exists()
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (FakePlatform(), lambda tray: None),
    )
    assert main([], environ) == 0
    assert (home.logs / "tray.log.1").stat().st_size == LOG_BYTES + 1


def test_a_second_tray_leaves_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    held = FileLock(home.lock, timeout=0)
    held.acquire()
    try:
        monkeypatch.setattr(
            "ecosemantic.tray.__main__.platform_and_runner",
            lambda: (FakePlatform(), lambda tray: None),
        )
        assert main([], environ) == 0
        assert not home.pid.exists()
    finally:
        held.release()


class Refusing:
    """A launcher this machine refuses: every start of a process raises the refusal the test
    named."""

    def __init__(self, refusal: Exception) -> None:
        self.refusal = refusal

    def start(self, command: list[str], log: Path, contained: bool) -> None:
        raise self.refusal


@pytest.mark.parametrize(
    "_refusal",
    [
        OSError(5, "the program could not be started"),
        Unavailable("CreateJobObjectW failed: [WinError 5] Access is denied"),
    ],
)
def test_a_first_start_the_machine_refuses_is_told_to_the_person(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _refusal: Exception,
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    platform = FakePlatform(launcher=Refusing(_refusal))
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner", lambda: (platform, lambda tray: None)
    )
    assert main([], environ) == 1
    assert platform.refusals == [(APP, str(_refusal))]
    assert str(_refusal) in (home.logs / "tray.log").read_text(encoding="utf-8")
    assert str(_refusal) in capsys.readouterr().err
    assert not home.pid.exists()


def test_a_machine_without_a_credential_store_is_told_the_tray_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    platform = FakePlatform()
    refused = "this machine has no credential store for the bridge's sign-in"

    def refusing(*args: object) -> None:
        raise Unavailable(refused)

    monkeypatch.setattr("ecosemantic.tray.__main__.store_for", refusing)
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner", lambda: (platform, lambda tray: None)
    )
    assert main([], environ) == 1
    assert platform.refusals == [(APP, refused)]
    assert refused in (home.logs / "tray.log").read_text(encoding="utf-8")
    assert not home.pid.exists()


def test_a_first_tray_starts_the_engine_and_leaves_its_pid_behind_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    platform = FakePlatform()
    seen: list[bool] = []

    def runner(tray: Tray) -> None:
        seen.append(home.pid.exists())
        assert tray.engine.running

    monkeypatch.setattr("ecosemantic.tray.__main__.platform_and_runner", lambda: (platform, runner))
    assert main([], environ) == 0
    assert seen == [True]
    assert not home.pid.exists()
    assert list(home.root.glob(".tray.pid*")) == []
    assert [process.command[5] for process in platform.launcher.processes] == ["serve", "bridge"]


@pytest.mark.skipif(os.name != "posix", reason="only POSIX refuses a read by its mode")
def test_a_settings_file_that_cannot_be_opened_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = a_home(tmp_path)
    settings_for(tmp_path).write(home.settings)
    home.settings.chmod(0o000)
    try:
        assert quit_tray(home) == 4
    finally:
        home.settings.chmod(0o600)
    printed = capsys.readouterr().err
    assert str(home.settings) in printed and "cannot be read" in printed


def test_a_tray_without_a_console_interpreter_tells_the_person(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    platform = FakePlatform()
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (platform, lambda tray: None),
    )
    monkeypatch.setattr(sys, "stderr", None)
    assert main([], environ) == 1
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert "python.exe is missing" in written
    assert str(home.settings) not in written
    assert platform.refusals and "python.exe is missing" in platform.refusals[0][1]


class Html(http.server.BaseHTTPRequestHandler):
    """A server that answers on a port this tray's engine would have held."""

    body = b"<html>another program</html>"

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_quit_past_a_port_another_program_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.root.mkdir(parents=True)
    settings = settings_for(tmp_path)
    settings.write(home.settings)
    port = derived_port(settings.models)
    server = http.server.HTTPServer(("127.0.0.1", port), Html)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = time.monotonic()
        assert main(["--quit"], environ) == 0
        assert time.monotonic() - started < 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    printed = capsys.readouterr().err
    assert str(port) in printed and "not JSON" in printed


def test_a_rotation_the_os_refuses_is_the_first_line_this_run_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    (home.logs / "tray.log").write_text("an earlier run wrote this\n", encoding="utf-8")
    settings_for(tmp_path).write(home.settings)
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pythonw.exe"))
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (FakePlatform(), lambda tray: None),
    )

    def refusing(log: Path, keep: int = 1, limit: int = 1) -> None:
        raise PermissionError(32, "the file is held open by another process")

    monkeypatch.setattr("ecosemantic.tray.__main__.rotate", refusing)
    monkeypatch.setattr(sys, "stderr", None)
    assert main([], environ) == 0
    lines = (home.logs / "tray.log").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "an earlier run wrote this"
    assert "cannot be rotated" in lines[1]
    assert "held open" in lines[1]


@pytest.mark.skipif(sys.platform == "win32", reason="the tray runs on Windows, where it passes")
def test_check_refuses_on_a_machine_that_is_not_windows() -> None:
    with pytest.raises(Invalid, match="the tray runs on Windows"):
        checked()


def test_check_builds_the_platform_and_the_icons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = FakePlatform()
    monkeypatch.setattr(
        "ecosemantic.tray.__main__.platform_and_runner",
        lambda: (platform, lambda tray: None),
    )
    assert checked() == 0


@pytest.mark.skipif(sys.platform == "win32", reason="the tray runs on Windows, where it passes")
def test_check_from_the_command_line_leaves_a_free_folder(tmp_path: Path) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    with pytest.raises(Invalid, match="the tray runs on Windows"):
        main(["--check"], environ)
    assert not home.pid.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="--check builds the Windows platform")
def test_check_from_the_command_line_on_windows_leaves_a_free_folder(tmp_path: Path) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    assert main(["--check"], environ) == 0
    assert not home.pid.exists()


def test_the_login_command_is_the_windowless_interpreter_quoted(tmp_path: Path) -> None:
    folder = (
        tmp_path / "José Muñoz" / "AppData" / "Local" / "Programs" / "EcoSemantic Engine" / "python"
    )
    folder.mkdir(parents=True)
    (folder / "pythonw.exe").write_text("", encoding="utf-8")
    assert login_command(folder / "python.exe") == (
        f'"{folder / "pythonw.exe"}" -X utf8 -m ecosemantic.tray'
    )


def test_a_login_command_without_pythonw_is_refused(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="pythonw.exe is missing"):
        login_command(tmp_path / "python.exe")


@pytest.mark.skipif(sys.platform == "win32", reason="the tray runs on Windows, where it starts")
def test_a_tray_on_a_machine_that_is_not_windows_refuses_at_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    assert main([], environ) == 1
    assert "the tray runs on Windows" in capsys.readouterr().err
    assert "the tray runs on Windows" in (home.logs / "tray.log").read_text(encoding="utf-8")
    assert not home.pid.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows platform is built there")
def test_a_platform_that_cannot_be_built_is_shown_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ecosemantic.tray.windows as windows_module

    shown: list[tuple[str, str]] = []

    def raising() -> None:
        raise Invalid("C:\\app\\python\\pythonw.exe is missing, and Windows runs the tray with it")

    monkeypatch.setattr(windows_module, "refuse", lambda title, text: shown.append((title, text)))
    monkeypatch.setattr("ecosemantic.tray.__main__.platform_and_runner", raising)
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    assert main([], environ) == 1
    assert shown and "pythonw.exe is missing" in shown[0][1], shown
    assert "pythonw.exe is missing" in (home.logs / "tray.log").read_text(encoding="utf-8")
    assert not home.pid.exists()


def test_a_platform_the_job_refuses_is_shown_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []

    def refusing() -> None:
        raise Unavailable("CreateJobObjectW failed: [WinError 5] Access is denied")

    monkeypatch.setattr("ecosemantic.tray.__main__.platform_and_runner", refusing)
    monkeypatch.setattr("ecosemantic.tray.__main__._shown", shown.append)
    environ = {"LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    assert main([], environ) == 1
    assert shown == ["CreateJobObjectW failed: [WinError 5] Access is denied"], shown
    written_log = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert "CreateJobObjectW failed" in written_log, written_log
    assert not home.pid.exists()


def test_a_write_that_fails_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refusing(self: Path, target: Path) -> Path:
        raise OSError(5, "the file is held by another process")

    monkeypatch.setattr(Path, "replace", refusing)
    with pytest.raises(OSError, match="held by another process"):
        written(tmp_path / "tray.pid", "4242\n")
    assert list(tmp_path.iterdir()) == []


def test_the_written_helper_names_the_line_ending_it_writes() -> None:
    """The docstring holds the two characters `\\n`, not a line break between its backticks, which
    is what `__doc__` reads when the string is not raw."""
    assert "`\\n`" in (written.__doc__ or "")
