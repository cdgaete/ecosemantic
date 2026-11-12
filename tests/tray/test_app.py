from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import keyring
import pytest
from filelock import FileLock
from keyring.backends.fail import Keyring as FailKeyring

from ecosemantic.bridge.credentials import Credential, store_for
from ecosemantic.errors import Conflict, Invalid, Unavailable
from ecosemantic.settings import DEFAULT_BRIDGE_URL
from ecosemantic.settings.handover import BridgeHealth, Health
from ecosemantic.tray.__main__ import quit_tray
from ecosemantic.tray.app import SIGNED_OUT_NOTICE, Tray, dispatched
from ecosemantic.tray.engine import RESTART_SECONDS, RESTARTS, Engine, engine_command
from ecosemantic.tray.home import APP, Home, TraySettings, home_for
from ecosemantic.tray.menu import StartAtLogin, menu_for
from tests.tray.fakes import (
    SCREEN,
    FakeLauncher,
    FakePlatform,
    HealthReader,
    Time,
    health_of,
)

PAGE = "https://ana.bridge.example"
CONNECTOR = "https://bridge.example/mcp"
ENGINE_LOG = str(Path("logs") / "engine.log")
BRIDGE_LOG = str(Path("logs") / "bridge.log")
CONNECTED = BridgeHealth(state="connected", handle="ana", page=PAGE, connector=CONNECTOR)
HOLD = """
import os, time
from filelock import FileLock
from pathlib import Path

root = Path(os.environ["TRAY_HOME"])
lock = FileLock(root / "tray.lock", timeout=0)
lock.acquire()
staged = root / ".tray.pid.tmp"
staged.write_text(f"{os.getpid()}\\n", encoding="utf-8")
staged.replace(root / "tray.pid")
time.sleep(120)
assert lock.is_locked
"""


def a_tray(
    tmp_path: Path,
    *,
    bridge: bool = True,
    health_document: BridgeHealth | None = None,
    accounts: str | None = SCREEN,
    launcher: FakeLauncher | None = None,
    health: Callable[[int], Health | None] | None = None,
    signed_in: bool = False,
    environ: dict[str, str] | None = None,
) -> tuple[Tray, FakePlatform, Engine, Home, HealthReader, Time]:
    """A tray over this folder, its machine, its engine and this process's credential store, signed
    in when the test says so, and reading the environment the test gives it."""
    home = Home(tmp_path / "home")
    home.root.mkdir(parents=True)
    python = tmp_path / "payload" / "python" / "python.exe"
    models = tmp_path / "models"
    settings = TraySettings(databases=tmp_path / "databases", models=models, bridge=bridge)
    settings.write(home.settings)
    launcher = launcher if launcher is not None else FakeLauncher()
    platform = FakePlatform(launcher=launcher)
    reader = (
        health
        if health is not None
        else HealthReader(
            document=None
            if health_document is None
            else health_of(models, health_document, accounts=accounts)
        )
    )
    clock = Time()
    engine = Engine(
        python=python,
        settings=settings,
        home=home,
        launcher=launcher,
        health=reader,
        stopper=lambda host, port, folder: False,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    if signed_in:
        store_for(DEFAULT_BRIDGE_URL, models, None).save(a_credential(models))
    return (
        Tray(
            engine=engine,
            platform=platform,
            home=home,
            python=python,
            environ={} if environ is None else environ,
        ),
        platform,
        engine,
        home,
        reader,
        clock,
    )


def a_credential(models: Path) -> Credential:
    """The credential this folder was signed in with."""
    return Credential(
        bridge_url=DEFAULT_BRIDGE_URL,
        client_id="the-engine-browser",
        engine=uuid.UUID("3f0b9a0e-6a1c-4d5f-9a2b-7c1d0e8f4a63"),
        account="account-1",
        handle="ana",
        page_url=PAGE,
        refresh_token="rt_" + "0" * 40,
    )


def sign_in_command(python: Path, models: Path) -> list[str]:
    return [
        str(python),
        "-X",
        "utf8",
        "-m",
        "ecosemantic",
        "bridge",
        "sign-in",
        "--systems-dir",
        str(models),
    ]


def test_open_page_and_copy_connector_use_the_engine_s_addresses(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health_document=CONNECTED)
    engine.start()
    tray.state()
    tray.act("open-page")
    tray.act("copy-connector")
    assert platform.urls == [PAGE]
    assert platform.copied == [CONNECTOR]


def test_database_accounts_opens_the_screen(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health_document=CONNECTED)
    engine.start()
    tray.state()
    tray.act("accounts")
    assert platform.urls == [SCREEN]


def test_sign_in_runs_the_command_turns_the_bridge_on_and_restarts(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, bridge=False, health_document=CONNECTED, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("sign-in")
    assert platform.launcher.processes[1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )
    assert TraySettings.read(home.settings).bridge is False
    assert len(platform.launcher.processes) == 2
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is True
    assert platform.launcher.processes[-1].command == engine_command(
        tray.python, TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    )


def test_sign_out_turns_the_bridge_off_and_restarts(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, health_document=CONNECTED, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("sign-out")
    sign_out = platform.launcher.processes[1].command
    assert sign_out[4:7] == ["ecosemantic", "bridge", "sign-out"]
    assert TraySettings.read(home.settings).bridge is True
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is False
    assert platform.launcher.processes[-1].command == engine_command(
        tray.python,
        TraySettings(databases=tmp_path / "databases", models=tmp_path / "models", bridge=False),
    )


def test_a_sign_in_that_does_not_finish_notifies_once_and_changes_nothing(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, bridge=False, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("sign-in")
    platform.launcher.processes[1].ended(1)
    tray.state()
    assert TraySettings.read(home.settings).bridge is False
    assert len(platform.launcher.processes) == 2
    assert platform.notices == [(APP, f"Sign-in did not finish; see {BRIDGE_LOG}")]
    tray.state()
    assert len(platform.notices) == 1


def test_a_sign_out_that_does_not_finish_notifies_once_and_changes_nothing(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("sign-out")
    platform.launcher.processes[1].ended(1)
    tray.state()
    assert TraySettings.read(home.settings).bridge is True
    assert platform.notices == [(APP, f"Sign-out did not finish; see {BRIDGE_LOG}")]
    tray.state()
    assert len(platform.notices) == 1


def test_a_second_bridge_command_is_refused_while_one_runs(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("sign-in")
    with pytest.raises(Invalid, match="a bridge command is already running"):
        tray.act("sign-in")
    with pytest.raises(Invalid, match="a bridge command is already running"):
        tray.act("sign-out")


def test_connect_and_disconnect_save_the_setting_and_restart(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, bridge=False, signed_in=True)
    engine.start()
    tray.act("connect")
    assert TraySettings.read(home.settings).bridge is True
    assert "--bridge" in platform.launcher.processes[-1].command
    tray.act("disconnect")
    assert TraySettings.read(home.settings).bridge is False
    assert "--bridge" not in platform.launcher.processes[-1].command


def test_connect_without_a_credential_signs_in_and_starts_no_bridged_engine(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, bridge=False, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.act("connect")
    assert platform.launcher.processes[1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )
    assert TraySettings.read(home.settings).bridge is False
    assert "--bridge" not in platform.launcher.processes[-1].command
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is True
    assert "--bridge" in platform.launcher.processes[-1].command


def test_a_start_with_the_bridge_on_and_no_credential_serves_this_machine_while_it_signs_in(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=BridgeHealth(state="off"),
        launcher=FakeLauncher(ends_bridge=False),
    )
    tray.start()
    assert platform.launcher.processes[0].command == engine_command(
        tray.python,
        TraySettings(databases=tmp_path / "databases", models=tmp_path / "models", bridge=False),
    )
    assert platform.launcher.processes[1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )
    assert engine.running is True
    state = tray.state()
    assert state.kind == "running"
    assert menu_for(state, StartAtLogin(enabled=False))[0].text == "The bridge is off"
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is True
    assert engine.running is True
    assert "--bridge" in platform.launcher.processes[-1].command


def test_the_sign_in_a_start_runs_that_fails_keeps_the_engine_without_the_bridge(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=BridgeHealth(state="off"),
        launcher=FakeLauncher(ends_bridge=False),
    )
    tray.start()
    serving = platform.launcher.processes[0]
    platform.launcher.processes[1].ended(1)
    state = tray.state()
    assert TraySettings.read(home.settings).bridge is False
    assert engine.running is True
    assert len(platform.launcher.processes) == 2
    assert "--bridge" not in serving.command
    assert state.kind == "running"
    assert platform.notices == [(APP, f"Sign-in did not finish; see {BRIDGE_LOG}")]
    tray.state()
    assert len(platform.notices) == 1


def test_a_sign_in_that_finishes_while_the_bridge_is_on_restarts_the_engine(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=BridgeHealth(state="signed-out"),
        launcher=FakeLauncher(ends_bridge=False),
    )
    engine.start()
    signed_out = tray.state()
    assert signed_out.bridge == "signed-out"
    assert [
        item.text
        for item in menu_for(signed_out, StartAtLogin(enabled=False))
        if item.action == "sign-in"
    ] == ["Sign in…"]
    tray.act("sign-in")
    platform.launcher.processes[1].ended(0)
    assert tray.state().kind == "running"
    assert len(platform.launcher.processes) == 3
    assert "--bridge" in platform.launcher.processes[-1].command
    assert platform.launcher.processes[-1].command == engine_command(
        tray.python, TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    )


def test_a_sign_in_that_finishes_while_the_relay_is_stopped_restarts_the_engine(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=BridgeHealth(state="stopped"),
        launcher=FakeLauncher(ends_bridge=False),
    )
    engine.start()
    assert tray.state().bridge == "stopped"
    tray.act("sign-in")
    platform.launcher.processes[1].ended(0)
    assert tray.state().kind == "running"
    assert len(platform.launcher.processes) == 3
    assert "--bridge" in platform.launcher.processes[-1].command
    assert platform.launcher.processes[-1].command == engine_command(
        tray.python, TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    )


def test_a_sign_in_that_fails_while_the_bridge_is_on_leaves_the_engine_alone(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=BridgeHealth(state="signed-out"),
        launcher=FakeLauncher(ends_bridge=False),
    )
    engine.start()
    tray.state()
    tray.act("sign-in")
    platform.launcher.processes[1].ended(1)
    assert tray.state().bridge == "signed-out"
    tray.state()
    assert len(platform.launcher.processes) == 2
    assert engine.running is True
    assert TraySettings.read(home.settings).bridge is True
    assert platform.notices == [
        (APP, SIGNED_OUT_NOTICE),
        (APP, f"Sign-in did not finish; see {BRIDGE_LOG}"),
    ]


def test_a_start_with_the_bridge_off_and_no_credential_starts_the_engine(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, bridge=False)
    tray.start()
    assert not [process for process in platform.launcher.processes if "sign-in" in process.command]
    assert engine.running is True


def test_a_sign_out_then_a_connect_signs_in_instead_of_failing_the_engine(
    tmp_path: Path,
) -> None:
    store = store_for(DEFAULT_BRIDGE_URL, tmp_path / "models", None)
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        health_document=CONNECTED,
        launcher=FakeLauncher(ends_bridge=False),
        signed_in=True,
    )
    engine.start()
    assert tray.state().bridge == "connected"
    tray.act("sign-out")
    platform.launcher.processes[1].ended(0)
    store.delete()
    tray.state()
    assert TraySettings.read(home.settings).bridge is False
    tray.act("connect")
    assert platform.launcher.processes[-1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )
    platform.launcher.processes[-1].ended(0)
    state = tray.state()
    assert state.kind == "running"
    assert TraySettings.read(home.settings).bridge is True
    assert "--bridge" in platform.launcher.processes[-1].command


def test_a_start_with_the_bridge_on_and_no_credential_serves_then_signs_in(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    unbridged = TraySettings(
        databases=tmp_path / "databases", models=tmp_path / "models", bridge=False
    )
    tray.start()
    assert platform.launcher.processes[0].command == engine_command(tray.python, unbridged)
    assert platform.launcher.processes[1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )
    assert engine.running
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is True
    assert engine.running
    assert platform.launcher.processes[-1].command == engine_command(
        tray.python, TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    )
    tray, platform, engine, home, health, time = a_tray(tmp_path / "second", signed_in=True)
    tray.start()
    assert not [process for process in platform.launcher.processes if "sign-in" in process.command]
    assert engine.running


def test_a_start_whose_engine_the_launcher_refuses_starts_no_sign_in(tmp_path: Path) -> None:
    refusal = Unavailable("AssignProcessToJobObject failed: [WinError 5] Access is denied")
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(refuses_engine=refusal)
    )
    unbridged = TraySettings(
        databases=tmp_path / "databases", models=tmp_path / "models", bridge=False
    )
    with pytest.raises(Unavailable) as refused:
        tray.start()
    assert refused.value is refusal
    assert platform.launcher.commands == [engine_command(tray.python, unbridged)]
    assert not [command for command in platform.launcher.commands if "sign-in" in command]
    assert engine.running is False


def test_a_start_the_launcher_refuses_keeps_the_bridge_on_and_the_next_start_signs_in(
    tmp_path: Path,
) -> None:
    refusal = Unavailable("AssignProcessToJobObject failed: [WinError 5] Access is denied")
    launcher = FakeLauncher(refuses_engine=refusal, ends_bridge=False)
    tray, platform, engine, home, health, time = a_tray(tmp_path, launcher=launcher)
    with pytest.raises(Unavailable):
        tray.act("start-engine")
    assert engine.settings.bridge is True
    assert TraySettings.read(home.settings).bridge is True
    launcher.refuses_engine = None
    tray.act("start-engine")
    assert [process.command[5] for process in platform.launcher.processes] == ["serve", "bridge"]
    assert "--bridge" not in platform.launcher.processes[0].command
    assert platform.launcher.processes[1].command == sign_in_command(
        tray.python, tmp_path / "models"
    )


def test_a_second_tray_exits_and_quit_ends_the_first(tmp_path: Path) -> None:
    environ = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    home = home_for(environ)
    home.logs.mkdir(parents=True)
    models = tmp_path / "models"
    models.mkdir()
    TraySettings(databases=tmp_path / "databases", models=models).write(home.settings)
    environ = {**environ, "TRAY_HOME": str(home.root)}
    holder = subprocess.Popen([sys.executable, "-c", HOLD], env=environ)
    try:
        deadline = time.monotonic() + 30
        while not home.pid.is_file():
            assert time.monotonic() < deadline, "the holder never wrote its pid"
            time.sleep(0.05)
        written = home.pid.read_text(encoding="utf-8")
        second = subprocess.run(
            [sys.executable, "-m", "ecosemantic.tray"],
            env=environ,
            capture_output=True,
            timeout=120,
        )
        assert second.returncode == 0
        assert home.pid.read_text(encoding="utf-8") == written
        stopped: list[bool] = []
        assert (
            quit_tray(
                home,
                ask=lambda host, port, folder: stopped.append(True) or True,
                health=lambda port: None,
            )
            == 0
        )
        assert stopped == [True]
        assert holder.wait(timeout=10) is not None
        # a tray ended without its own cleanup leaves its pid, which the next quit clears
        assert quit_tray(home, ask=lambda host, port, folder: True, health=lambda port: None) == 0
        assert not home.pid.exists()
        with FileLock(home.lock, timeout=0):
            pass
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()


def test_the_tray_reads_signed_in_as_bridge_status_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = {"ECOSEMANTIC_BRIDGE_TOKEN": "the-engine-token"}
    tray, platform, engine, home, health, time = a_tray(tmp_path, bridge=False, environ=token)
    state = tray.start()
    assert state.signed_in is True

    monkeypatch.setattr(keyring, "get_keyring", lambda: FailKeyring())
    tray, platform, engine, home, health, time = a_tray(tmp_path / "no-store", bridge=False)
    state = tray.start()
    assert state.signed_in is False


def test_signed_out_and_failed_notify_once(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path / "signed-out", health_document=BridgeHealth(state="signed-out")
    )
    engine.start()
    for _ in range(3):
        assert tray.state().bridge == "signed-out"
    assert len(platform.notices) == 1
    tray, platform, engine, home, health, time = a_tray(tmp_path / "failed")
    engine.start()
    for _ in range(RESTARTS):
        platform.launcher.processes[-1].ended(1)
        tray.state()
        time.now += RESTART_SECONDS
        tray.state()
    platform.launcher.processes[-1].ended(1)
    assert tray.state().kind == "failed"
    assert tray.state().kind == "failed"
    assert len(platform.notices) == 1


def test_a_page_the_health_does_not_name_is_refused(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, health_document=BridgeHealth(state="off")
    )
    engine.start()
    with pytest.raises(Invalid, match="names no page"):
        tray.act("open-page")


def test_start_at_login_opens_the_logs_starts_the_engine_and_quits(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, signed_in=True)
    tray.act("start-at-login")
    assert platform.logins == [True]
    tray.act("open-logs")
    assert platform.folders == [home.logs]
    tray.act("start-engine")
    assert [process.command[5] for process in platform.launcher.processes] == ["serve"]
    tray.act("quit")
    assert tray.quit_requested is True


def one_race(root: Path) -> list[object]:
    """One round of a menu action and a poll started together, answering what each of them did: a
    relaunch is already due, so both would start an engine without the tray's lock."""
    launcher = FakeLauncher(slowness=0.05)
    tray, platform, engine, home, health, time = a_tray(root, launcher=launcher, signed_in=True)
    engine.start()
    launcher.processes[-1].ended(1)
    tray.state()
    time.now += RESTART_SECONDS
    together = threading.Barrier(2)
    outcomes: list[object] = []

    def acting() -> None:
        together.wait()
        try:
            outcomes.append(tray.act("start-engine"))
        except Conflict as refused:
            outcomes.append(refused)

    def polling() -> None:
        together.wait()
        outcomes.append(tray.state())

    threads = [threading.Thread(target=acting), threading.Thread(target=polling)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    alive = [process for process in platform.launcher.processes if process.poll() is None]
    assert len(alive) == 1, outcomes
    return outcomes


def test_a_menu_action_and_a_poll_at_once_launch_one_engine(tmp_path: Path) -> None:
    for round_ in range(5):
        one_race(tmp_path / str(round_))


def test_the_failure_notice_names_the_engine_s_log(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)
    engine.start()
    for _ in range(RESTARTS):
        platform.launcher.processes[-1].ended(1)
        tray.state()
        time.now += RESTART_SECONDS
        tray.state()
    platform.launcher.processes[-1].ended(1)
    tray.state()
    assert platform.notices == [(APP, f"The engine failed; see {ENGINE_LOG}")]


def test_a_poll_after_quit_acts_on_nothing(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path,
        bridge=False,
        health_document=CONNECTED,
        launcher=FakeLauncher(ends_bridge=False),
    )
    engine.start()
    tray.act("sign-in")
    sign_in = platform.launcher.processes[1]
    tray.act("quit")
    assert tray.quit_requested is True
    assert sign_in.terminated is True
    sign_in.ended(0)
    state = tray.state()
    assert state.kind == "stopped"
    assert engine.running is False
    assert TraySettings.read(home.settings).bridge is False
    assert len(platform.launcher.processes) == 2
    tray.act("start-engine")
    assert engine.running is False
    assert len(platform.launcher.processes) == 2


def test_quit_and_open_the_logs_work_while_health_is_refused(tmp_path: Path) -> None:
    def refused(port: int) -> Health | None:
        raise Unavailable(f"the engine's health answered what is not JSON: {b'<html>'!r}")

    tray, platform, engine, home, health, time = a_tray(tmp_path, health=refused)
    engine.start()
    state = tray.state()
    assert state.kind == "starting"
    assert platform.notices == []
    assert "not JSON" in (home.logs / "tray.log").read_text(encoding="utf-8")
    tray.state()
    assert platform.notices == []
    tray.act("open-logs")
    assert platform.folders == [home.logs]
    tray.act("quit")
    assert tray.quit_requested is True


def test_a_refused_health_is_written_once_for_each_reason(tmp_path: Path) -> None:
    reasons_line = "the health answered what is not JSON: b'<html>'"
    reasons = [reasons_line]

    def refused(port: int) -> Health | None:
        raise Unavailable(reasons[0])

    tray, platform, engine, home, health, time = a_tray(tmp_path, health=refused)
    engine.start()
    for _ in range(10):
        tray.state()
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert written.splitlines() == [reasons[0]]
    second = "the health answered what is not JSON: b'<html lang=\"en\">'"
    reasons[0] = second
    tray.state()
    tray.state()
    assert (home.logs / "tray.log").read_text(encoding="utf-8").splitlines() == [
        reasons_line,
        second,
    ]


def test_a_process_ending_under_a_refused_health_retries_to_failed_once(
    tmp_path: Path,
) -> None:
    def refused(port: int) -> Health | None:
        raise Unavailable("the health answered what is not JSON: b'<html>'")

    tray, platform, engine, home, health, time = a_tray(tmp_path, health=refused)
    engine.start()
    for _ in range(RESTARTS):
        platform.launcher.processes[-1].ended(1)
        tray.state()
        time.now += RESTART_SECONDS
        tray.state()
    platform.launcher.processes[-1].ended(1)
    state = tray.state()
    assert state.kind == "failed"
    assert menu_for(state, StartAtLogin(enabled=False))[7].text == "Start the engine"
    tray.state()
    assert platform.notices == [(APP, f"The engine failed; see {ENGINE_LOG}")]


def test_the_sign_in_a_start_runs_that_fails_turns_the_bridge_off_and_keeps_the_engine(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    tray.start()
    serving = platform.launcher.processes[0]
    assert engine.running is True
    assert platform.launcher.processes[1].command[4:7] == ["ecosemantic", "bridge", "sign-in"]
    assert "--bridge" not in serving.command
    platform.launcher.processes[1].ended(1)
    state = tray.state()
    assert TraySettings.read(home.settings).bridge is False
    assert engine.running is True
    assert [process.command[5] for process in platform.launcher.processes] == ["serve", "bridge"]
    assert len(platform.launcher.processes) == 2
    assert serving.terminated is False
    assert state.kind == "starting"
    assert platform.notices == [(APP, f"Sign-in did not finish; see {BRIDGE_LOG}")]


def test_a_poll_after_quit_does_not_restart_a_kept_engine(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)
    engine.start()
    tray.state()
    process = platform.launcher.processes[0]
    process.stubborn = True
    tray.act("quit")
    after_quit = tray.state()
    process.stubborn = False
    process.ended(1)
    time.now += RESTART_SECONDS
    assert tray.state() == after_quit
    assert engine.running is False
    assert len(platform.launcher.processes) == 1


def test_disconnect_with_a_process_that_ignores_terminate_saves_nothing(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health_document=CONNECTED)
    engine.start()
    tray.state()
    platform.launcher.processes[0].stubborn = True
    tray.act("disconnect")
    assert TraySettings.read(home.settings).bridge is True
    assert platform.notices == [(APP, f"The engine did not stop; see {ENGINE_LOG}")]
    state = tray.state()
    assert state.kind in ("running", "starting")
    assert len(platform.launcher.processes) == 1


def test_a_sign_in_that_ends_while_the_engine_ignores_terminate_saves_nothing(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, bridge=False, health_document=CONNECTED, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.state()
    tray.act("sign-in")
    platform.launcher.processes[0].stubborn = True
    platform.launcher.processes[1].ended(0)
    tray.state()
    assert TraySettings.read(home.settings).bridge is False
    assert platform.notices == [(APP, f"The engine did not stop; see {ENGINE_LOG}")]
    assert len(platform.launcher.processes) == 2


def test_a_bridge_command_shows_as_pending_and_the_menu_offers_no_bridge_action(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.state()
    tray.act("sign-out")
    pending = tray.state()
    assert pending.pending is True
    assert not [
        item
        for item in menu_for(pending, StartAtLogin(enabled=False))
        if item.action in ("connect", "disconnect", "sign-in", "sign-out", "start-engine")
    ]
    platform.launcher.processes[1].ended(0)
    finished = tray.state()
    assert finished.pending is False
    assert [
        item.text
        for item in menu_for(finished, StartAtLogin(enabled=False))
        if item.action in ("connect", "disconnect", "sign-in", "sign-out")
    ] == ["Connect to the bridge", "Sign in…"]


def refused_health(port: int) -> Health | None:
    """A health this tray refuses, as a port another program holds answers."""
    raise Unavailable("the health on port 1 answered what is not JSON: b'<html>'")


def test_disconnect_with_a_stubborn_engine_and_a_refused_health_does_not_raise(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health=refused_health)
    engine.start()
    tray.state()
    platform.launcher.processes[0].stubborn = True
    tray.act("disconnect")
    assert TraySettings.read(home.settings).bridge is True
    assert platform.notices == [(APP, f"The engine did not stop; see {ENGINE_LOG}")]


def test_a_sign_in_that_ends_while_a_stubborn_engine_refuses_health_is_read(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, bridge=False, health=refused_health, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.state()
    tray.act("sign-in")
    platform.launcher.processes[0].stubborn = True
    platform.launcher.processes[1].ended(0)
    state = tray.state()
    assert state.pending is False
    assert TraySettings.read(home.settings).bridge is False
    assert platform.notices == [(APP, f"The engine did not stop; see {ENGINE_LOG}")]
    assert state.kind == "starting"


def test_quit_with_a_stubborn_engine_and_a_refused_health_does_not_raise(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path, health=refused_health)
    engine.start()
    tray.state()
    platform.launcher.processes[0].stubborn = True
    tray.act("quit")
    assert tray.quit_requested is True


def test_a_refused_action_is_written_and_told_instead_of_ending_the_worker(
    tmp_path: Path,
) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.state()
    tray.act("sign-in")
    dispatched(tray, "sign-in")
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert "a bridge command is already running" in written, written
    assert platform.notices == [(APP, "a bridge command is already running")]
    dispatched(tray, "open-logs")
    assert platform.folders == [home.logs]


def test_the_engine_is_contained_and_the_bridge_commands_are_not(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(tmp_path)
    engine.start()
    tray.act("sign-in")
    assert platform.launcher.contained == [True, False]
    assert platform.launcher.logs[0] == home.logs / "engine.log"
    assert platform.launcher.logs[1] == home.logs / "bridge.log"


def test_each_refused_action_is_written(tmp_path: Path) -> None:
    tray, platform, engine, home, health, time = a_tray(
        tmp_path, launcher=FakeLauncher(ends_bridge=False)
    )
    engine.start()
    tray.state()
    tray.act("sign-in")
    dispatched(tray, "sign-in")
    dispatched(tray, "sign-in")
    written = (home.logs / "tray.log").read_text(encoding="utf-8")
    assert written.count("a bridge command is already running") == 2, written
    assert [notice for _, notice in platform.notices] == [
        "a bridge command is already running",
        "a bridge command is already running",
    ]
