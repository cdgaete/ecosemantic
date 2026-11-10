"""The engine a tray owns: its command, its log, the state its health reports, and what happens
when it ends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ecosemantic.errors import Conflict, Unavailable
from ecosemantic.settings import derived_port, workspace_digest
from ecosemantic.settings.handover import LOOPBACK_ADDRESS, BridgeState, Health
from ecosemantic.tray.home import Home, TraySettings

LOG_FILE = "engine.log"
LOG_BYTES = 5 * 1024 * 1024
KEPT_LOGS = 4
STOP_SECONDS = 10.0
TERMINATE_SECONDS = 5.0
POLL_SECONDS = 0.25
EARLY_SECONDS = 30.0
RESTART_SECONDS = 10.0
RESTARTS = 3

EngineKind = Literal["starting", "running", "stopped", "failed"]


class Process(Protocol):
    """A process the tray started, as the launcher answers it."""

    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...


class Launcher(Protocol):
    """How the tray starts a process: its command, and the log its output is appended to."""

    def start(self, command: list[str], log: Path, contained: bool) -> Process: ...


@dataclass(frozen=True, kw_only=True)
class EngineState:
    """What the tray shows: whether the engine runs, how its tunnel stands, whether the person keeps
    the bridge on, whether this folder holds a credential, and the addresses its health names."""

    kind: EngineKind
    bridge: BridgeState
    bridge_on: bool
    signed_in: bool = False
    pending: bool = False
    handle: str | None = None
    page: str | None = None
    connector: str | None = None
    accounts: str | None = None


def asked(settings: TraySettings, stopper: Callable[[str, int, Path], bool]) -> bool:
    """Ask the engine these settings name to stop, through the stopper given, on the port `serve`
    derives for its models folder."""
    return stopper(LOOPBACK_ADDRESS, derived_port(settings.models), settings.models)


def core_command(python: Path, *arguments: str) -> list[str]:
    """The core's command line as the tray runs it: this interpreter, its output written as UTF-8
    whatever code page this machine has, the module, and the arguments given after them."""
    return [str(python), "-X", "utf8", "-m", "ecosemantic", *arguments]


def engine_command(python: Path, settings: TraySettings) -> list[str]:
    """The command the tray runs the engine with: the page over HTTP on the address and port the
    tray polls with no token, the tray named as its starter, the bridge unless the person turned it
    off, the two folders it was given, and the solver the payload carries."""
    command = core_command(
        python,
        "serve",
        "--transport",
        "http",
        "--tray",
        "--view-host",
        LOOPBACK_ADDRESS,
        "--view-port",
        str(derived_port(settings.models)),
        "--no-token",
    )
    if settings.bridge:
        command.append("--bridge")
    return [
        *command,
        "--data-dir",
        str(settings.databases),
        "--systems-dir",
        str(settings.models),
        "--solver",
        "pardiso",
    ]


def rotate(log: Path, *, keep: int = KEPT_LOGS, limit: int = LOG_BYTES) -> None:
    """Move a log past its limit aside, shifting each earlier file one number older, dropping the
    oldest, and keeping the ones that are there: a first rotation finds none of them."""
    if not log.is_file() or log.stat().st_size <= limit:
        return
    for number in range(keep - 1, 0, -1):
        earlier = log.with_name(f"{log.name}.{number}")
        if earlier.is_file():
            earlier.replace(log.with_name(f"{log.name}.{number + 1}"))
    log.replace(log.with_name(f"{log.name}.1"))


class Engine:
    """The engine process a tray owns: it writes the log the engine appends to, starts it with the
    command its settings name, reads the state its health reports, stops it through `/stop` and
    terminates it when that does not end it, and starts it again after an end within thirty seconds
    of its start, three times, and fails after that."""

    def __init__(
        self,
        *,
        python: Path,
        settings: TraySettings,
        home: Home,
        launcher: Launcher,
        health: Callable[[int], Health | None],
        stopper: Callable[[str, int, Path], bool],
        clock: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.python = python
        self.settings = settings
        self.home = home
        self.launcher = launcher
        self.health = health
        self.stopper = stopper
        self.clock = clock
        self.sleep = sleep
        self._process: Process | None = None
        self._started_at = 0.0
        self._restarts = 0
        self._restart_at: float | None = None
        self._failed = False

    @property
    def port(self) -> int:
        """The port the engine serves this folder on, which `serve` derives when given none."""
        return derived_port(self.settings.models)

    @property
    def log(self) -> Path:
        """The file the engine's output is appended to, and the one a start rotates."""
        return self.home.logs / LOG_FILE

    @property
    def running(self) -> bool:
        """Whether a process the tray started is alive."""
        return self._process is not None and self._process.poll() is None

    def start(self) -> EngineState:
        """Start the engine on the settings as they are now, and begin the count of early ends
        afresh; an engine that already runs is refused, so no path leaves one behind."""
        if self.running:
            raise Conflict("the engine is already running")
        self._restarts = 0
        return self._launched()

    def _launched(self) -> EngineState:
        """Rotate the log and start the process, keeping the count of early ends a start again
        spends."""
        self.home.logs.mkdir(parents=True, exist_ok=True)
        rotate(self.log)
        self._process = self.launcher.start(
            engine_command(self.python, self.settings), self.log, contained=True
        )
        self._started_at = self.clock()
        self._restart_at = None
        self._failed = False
        return self._starting()

    def ask(self) -> bool:
        """Ask the engine to stop through its stopper once, waiting for nothing, and answer what the
        stopper said; the command line's handover and Windows' end of session both ask this way."""
        return asked(self.settings, self.stopper)

    def stop(self) -> EngineState:
        """Ask the engine to stop through the nonce its folder proves, and terminate its process
        when that has not ended it after ten seconds. A process that has still not ended keeps the
        engine, so a start is refused while it lives, and answers starting without reading the
        health a stop must not need."""
        process = self._process
        if process is None or process.poll() is not None:
            self._process = None
            self._restart_at = None
            self._failed = False
            self._restarts = 0
            return self._stopped()
        self.ask()
        deadline = self.clock() + STOP_SECONDS
        while process.poll() is None and self.clock() < deadline:
            self.sleep(POLL_SECONDS)
        if process.poll() is None:
            process.terminate()
            giving = self.clock() + TERMINATE_SECONDS
            while process.poll() is None and self.clock() < giving:
                self.sleep(POLL_SECONDS)
        if process.poll() is None:
            return self._starting()
        self._process = None
        self._restart_at = None
        self._failed = False
        self._restarts = 0
        return self._stopped()

    def restart(self) -> EngineState:
        """Stop the engine and start it again, as a change of settings needs; an engine that will
        not stop keeps its place, and the state it answers says which."""
        state = self.stop()
        if self.running:
            return state
        return self.start()

    def starting(self) -> EngineState:
        """The state of a process that has not answered as this engine yet."""
        return self._starting()

    def poll(self) -> EngineState:
        """The state the tray shows now: while the process lives, what its health answers; when it
        has ended, a start again ten seconds later if it ended within thirty of its start and has
        not been started again three times, and stopped or failed otherwise."""
        now = self.clock()
        if self._process is not None:
            if self._process.poll() is None:
                return self._serving()
            self._process = None
            if now - self._started_at <= EARLY_SECONDS:
                if self._restarts >= RESTARTS:
                    self._failed = True
                else:
                    self._restarts += 1
                    self._restart_at = now + RESTART_SECONDS
        if self._failed:
            return self._stopped("failed")
        if self._restart_at is not None:
            if now < self._restart_at:
                return self._starting()
            return self._launched()
        return self._stopped()

    def _starting(self) -> EngineState:
        """Starting, with the bridge connecting when the person keeps it on and off when they do
        not."""
        return EngineState(
            kind="starting",
            bridge="connecting" if self.settings.bridge else "off",
            bridge_on=self.settings.bridge,
        )

    def _stopped(self, kind: EngineKind = "stopped") -> EngineState:
        """Stopped, or failed, with the bridge the person's setting names."""
        return EngineState(
            kind=kind,
            bridge="off",
            bridge_on=self.settings.bridge,
        )

    def _serving(self) -> EngineState:
        """What a live engine's health says, and starting while it answers nothing; a health of
        another models folder is refused, since this port is the one this folder derives."""
        health = self.health(self.port)
        if health is None:
            return self._starting()
        if health.workspace != workspace_digest(self.settings.models):
            raise Unavailable(f"port {self.port} serves another models folder")
        return EngineState(
            kind="running",
            bridge=health.bridge.state,
            bridge_on=self.settings.bridge,
            handle=health.bridge.handle,
            page=health.bridge.page,
            connector=health.bridge.connector,
            accounts=health.accounts,
        )
