from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, Unavailable
from ecosemantic.settings import derived_port
from ecosemantic.tray.engine import (
    EARLY_SECONDS,
    LOG_BYTES,
    RESTART_SECONDS,
    Engine,
    EngineState,
    engine_command,
    read_health,
)
from ecosemantic.tray.home import Home, TraySettings
from tests.tray.fakes import FakeLauncher, Health, Time


def running_engine(
    tmp_path: Path, health: Health | None = None
) -> tuple[Engine, FakeLauncher, Health, Time]:
    """An engine over this folder, its processes and health the test's, its clock the test's."""
    home = Home(tmp_path / "home")
    settings = TraySettings(databases=tmp_path / "databases", models=tmp_path / "models")
    launcher = FakeLauncher()
    reader = health if health is not None else Health()
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
    assert engine_command(python, served) == [
        str(python),
        "-X",
        "utf8",
        "-m",
        "ecosemantic",
        "serve",
        "--transport",
        "http",
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
        "--data-dir",
        str(tmp_path / "data"),
        "--systems-dir",
        str(tmp_path / "models"),
        "--solver",
        "pardiso",
    ]


def test_the_state_follows_health(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    assert engine.start() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert len(launcher.processes) == 1
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    health.document = {
        "service": "ecosemantic-view",
        "workspace": "abcd1234abcd1234",
        "yields": False,
        "bridge": {
            "state": "connected",
            "handle": "ana",
            "page": "https://ana.bridge.example",
            "connector": "https://bridge.example/mcp",
        },
    }
    assert engine.poll() == EngineState(
        kind="running",
        bridge="connected",
        bridge_on=True,
        handle="ana",
        page="https://ana.bridge.example",
        connector="https://bridge.example/mcp",
    )
    health.document = {"bridge": {"state": "off"}}
    assert engine.poll() == EngineState(kind="running", bridge="off", bridge_on=True)
    health.document = None
    assert engine.poll() == EngineState(kind="starting", bridge="connecting", bridge_on=True)
    assert health.ports == [derived_port(tmp_path / "models")] * 4
    assert time.slept == []


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


class Answering(http.server.BaseHTTPRequestHandler):
    """A server that answers one health document on any GET."""

    body = json.dumps({"bridge": {"state": "off"}}).encode()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_health_is_read_on_this_machine_s_loopback() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), Answering)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        assert read_health(port) == {"bridge": {"state": "off"}}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert read_health(port) is None


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


def test_a_bridge_state_the_relay_does_not_know_is_reported(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    health.document = {"bridge": {"state": "asleep"}}
    with pytest.raises(Unavailable, match="asleep"):
        engine.poll()


def test_starting_an_engine_that_already_runs_is_refused(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    with pytest.raises(Conflict, match="already running"):
        engine.start()
    assert len(launcher.processes) == 1


def test_a_health_that_names_no_bridge_state_is_refused(tmp_path: Path) -> None:
    engine, launcher, health, time = running_engine(tmp_path)
    engine.start()
    health.document = {}
    with pytest.raises(Unavailable, match="no bridge state"):
        engine.poll()
    health.document = {"bridge": {}}
    with pytest.raises(Unavailable, match="no bridge state"):
        engine.poll()


class NotJson(http.server.BaseHTTPRequestHandler):
    """A server that answers a body this tray cannot read as health."""

    body = b"<html>the port belongs to another program</html>"

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_a_health_that_is_not_json_is_refused_with_what_answered() -> None:
    server = http.server.HTTPServer(("127.0.0.1", 0), NotJson)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with pytest.raises(Unavailable, match="not JSON"):
            read_health(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
