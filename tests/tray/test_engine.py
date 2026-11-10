from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, Unavailable
from ecosemantic.settings import derived_port
from ecosemantic.settings.handover import BridgeHealth
from ecosemantic.tray.engine import (
    EARLY_SECONDS,
    LOG_BYTES,
    RESTART_SECONDS,
    Engine,
    EngineState,
    engine_command,
)
from ecosemantic.tray.home import Home, TraySettings
from tests.tray.fakes import SCREEN, FakeLauncher, HealthReader, Time, health_of


def running_engine(
    tmp_path: Path, health: HealthReader | None = None
) -> tuple[Engine, FakeLauncher, HealthReader, Time]:
    """An engine over this folder, its processes and health the test's, its clock the test's."""
    home = Home(tmp_path / "home")
    settings = TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    launcher = FakeLauncher()
    reader = health if health is not None else HealthReader()
    time = Time()
    engine = Engine(
        python=Path("/payload/python/python.exe"),
        settings=settings,
        home=home,
        launcher=launcher,
        health=reader,
        stopper=lambda host, port, folder: False,
        clock=time.clock,
        sleep=time.sleep,
    )
    return engine, launcher, reader, time


def test_the_engine_command_is_exact_with_and_without_the_bridge(tmp_path: Path) -> None:
    python = Path("/payload/python/python.exe")
    served = TraySettings(databases=tmp_path / "data", models=tmp_path / "models")
    listener = ["--view-host", "127.0.0.1", "--view-port", str(derived_port(tmp_path / "models"))]
    assert engine_command(python, served) == [
        str(python),
        "-X",
        "utf8",
        "-m",
        "ecosemantic",
        "serve",
        "--transport",
        "http",
        "--tray",
        *listener,
        "--no-token",
        "--bridge",
        "--data-dir",
        str(tmp_path / "data"),
        "--systems-dir",
        str(tmp_path / "models"),
        "--solver",
        "pardiso",
    ]
    unbridged = TraySettings(databases=tmp_path / "data", models=tmp_path / "models", bridge=False)
    assert engine_command(python, unbridged) == [
        str(python),
        "-X",
        "utf8",
        "-m",
        "ecosemantic",
        "serve",
        "--transport",
        "http",
        "--tray",
        *listener,
        "--no-token",
        "--data-dir",
        str(tmp_path / "data"),
        "--systems-dir",
        str(tmp_path / "models"),
        "--solver",
        "pardiso",
    ]


def test_the_engine_command_names_its_listener(tmp_path: Path) -> None:
    python = Path("/payload/python/python.exe")
    models = tmp_path / "models"
    for bridge in (True, False):
        command = engine_command(
            python, TraySettings(databases=tmp_path / "data", models=models, bridge=bridge)
        )
        assert command[command.index("--view-host") + 1] == "127.0.0.1"
        assert command[command.index("--view-port") + 1] == str(derived_port(models))
        assert "--no-token" in command


def test_the_engine_command_names_the_tray_as_its_starter(tmp_path: Path) -> None:
    python = Path("/payload/python/python.exe")
    models = tmp_path / "models"
    for bridge in (True, False):
        command = engine_command(
            python, TraySettings(databases=tmp_path / "data", models=models, bridge=bridge)
        )
        assert command[command.index("--transport") + 1 : command.index("--view-host")] == [
            "http",
            "--tray",
        ]
        assert command[command.index("--view-host") + 1] == "127.0.0.1"
        assert command[command.index("--view-port") + 1] == str(derived_port(models))
        assert "--no-token" in command


def test_the_state_carries_the_accounts_screen_the_health_names(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    models = tmp_path / "models"
    engine.start()
    health.document = health_of(models, BridgeHealth(state="off"))
    assert engine.poll().accounts == SCREEN
    health.document = health_of(models, BridgeHealth(state="off"), accounts=None)
    assert engine.poll().accounts is None


def test_the_state_follows_health(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    models = tmp_path / "models"
    assert engine.start() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert len(launcher.processes) == 1
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    health.document = health_of(
        models,
        BridgeHealth(
            state="connected",
            handle="ana",
            page="https://ana.bridge.example",
            connector="https://bridge.example/mcp",
        ),
    )
    assert engine.poll() == EngineState(
        kind="running",
        bridge="connected",
        bridge_on=True,
        handle="ana",
        page="https://ana.bridge.example",
        connector="https://bridge.example/mcp",
        accounts=SCREEN,
    )
    health.document = health_of(models, BridgeHealth(state="off"))
    assert engine.poll() == EngineState(
        kind="running", bridge="off", bridge_on=True, accounts=SCREEN
    )
    health.document = None
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert health.ports == [derived_port(models)] * 4
    assert time.slept == []


def test_a_health_of_another_folder_is_refused(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    health.document = health_of(tmp_path / "other", BridgeHealth(state="off"))
    with pytest.raises(Unavailable, match="another models folder"):
        engine.poll()


def test_stop_asks_the_engine_then_ends_it_after_ten_seconds(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    asked: list[tuple[str, int, Path]] = []

    def refusing(host: str, port: int, folder: Path) -> bool:
        asked.append((host, port, folder))
        return False

    engine.stopper = refusing
    moments: list[float] = []
    process = launcher.processes[0]
    ending = process.terminate

    def terminate() -> None:
        moments.append(time.now)
        ending()

    process.terminate = terminate
    assert engine.stop() == EngineState(kind="stopped", bridge="off", bridge_on=True)
    assert asked == [("127.0.0.1", derived_port(tmp_path / "models"), tmp_path / "models")]
    assert process.terminated
    assert moments and 10 <= moments[0] <= 10.25
    again = running_engine(tmp_path)
    again[0].start()

    def yielding(host: str, port: int, folder: Path) -> bool:
        launcher.processes[0].ended(0)
        return True

    engine, launcher, health, time = again
    engine.stopper = yielding
    assert engine.stop() == EngineState(kind="stopped", bridge="off", bridge_on=True)
    assert not launcher.processes[0].terminated
    assert time.slept == []


def test_the_log_is_rotated_past_5_mib_keeping_four(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.home.logs.mkdir(parents=True)
    engine.log.write_bytes(b"x" * (LOG_BYTES + 1))
    engine.start()
    assert (engine.home.logs / "engine.log.1").stat().st_size == LOG_BYTES + 1
    assert not (engine.home.logs / "engine.log.2").exists()
    engine, launcher, health, time = running_engine(tmp_path)
    engine.log.write_bytes(b"y" * (LOG_BYTES + 1))
    (engine.home.logs / "engine.log.1").write_text("older 1", encoding="utf-8")
    engine.start()
    assert (engine.home.logs / "engine.log.1").stat().st_size == LOG_BYTES + 1
    assert (engine.home.logs / "engine.log.2").read_text(encoding="utf-8") == "older 1"
    assert not (engine.home.logs / "engine.log.3").exists()
    engine, launcher, health, time = running_engine(tmp_path)
    engine.log.write_bytes(b"z" * (LOG_BYTES + 1))
    for number in range(1, 5):
        (engine.home.logs / f"engine.log.{number}").write_text(f"older {number}", encoding="utf-8")
    engine.start()
    assert (engine.home.logs / "engine.log.1").stat().st_size == LOG_BYTES + 1
    assert (engine.home.logs / "engine.log.2").read_text(encoding="utf-8") == "older 1"
    assert (engine.home.logs / "engine.log.4").read_text(encoding="utf-8") == "older 3"
    assert not (engine.home.logs / "engine.log.5").exists()
    engine, launcher, health, time = running_engine(tmp_path)
    engine.log.write_text("a short log", encoding="utf-8")
    engine.start()
    assert engine.log.read_text(encoding="utf-8") == "a short log"
    assert (engine.home.logs / "engine.log.1").stat().st_size == LOG_BYTES + 1


def test_an_engine_ending_soon_after_start_is_retried_three_times_then_failed(
    tmp_path: Path,
) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    for attempt in range(3):
        launcher.processes[-1].ended(1)
        assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
        time.now += RESTART_SECONDS - 0.1
        assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
        assert len(launcher.processes) == attempt + 1
        time.now += 0.1
        engine.poll()
        assert len(launcher.processes) == attempt + 2
    launcher.processes[-1].ended(1)
    assert engine.poll() == EngineState(kind="failed", bridge="off", bridge_on=True)
    assert len(launcher.processes) == 4
    engine.start()
    launcher.processes[-1].ended(1)
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    time.now += RESTART_SECONDS
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert len(launcher.processes) == 6


def test_an_engine_ended_from_outside_is_shown_stopped(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    time.now += EARLY_SECONDS * 2
    launcher.processes[0].ended(0)
    assert engine.poll() == EngineState(kind="stopped", bridge="off", bridge_on=True)
    assert engine.poll() == EngineState(kind="stopped", bridge="off", bridge_on=True)
    assert len(launcher.processes) == 1


def test_stopping_an_engine_that_already_ended_asks_nothing(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    launcher.processes[0].ended(0)
    asked: list[tuple[str, int, Path]] = []
    engine.stopper = lambda host, port, folder: asked.append((host, port, folder)) or True
    assert engine.stop() == EngineState(kind="stopped", bridge="off", bridge_on=True)
    assert asked == []


def test_a_process_that_ignores_terminate_keeps_its_engine_and_refuses_a_start(
    tmp_path: Path,
) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    launcher.processes[0].stubborn = True
    assert engine.stop() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert launcher.processes[0].terminated
    assert sum(time.slept) >= 10
    assert engine.running is True
    with pytest.raises(Conflict, match="already running"):
        engine.start()
    assert len(launcher.processes) == 1


def test_starting_an_engine_that_already_runs_is_refused(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    with pytest.raises(Conflict, match="already running"):
        engine.start()
    assert len(launcher.processes) == 1


def test_the_engine_is_asked_through_its_own_stopper(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    asked: list[tuple[str, int, Path]] = []
    engine.stopper = lambda host, port, folder: asked.append((host, port, folder)) or True
    assert engine.ask() is True
    assert asked == [("127.0.0.1", derived_port(tmp_path / "models"), tmp_path / "models")]
    assert engine.running is True
    assert launcher.processes[0].terminated is False
    assert time.slept == []
