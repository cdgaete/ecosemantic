"""The tray's actions: what each menu item does to the engine, to the settings, to Windows'
start-at-login value, and to the bridge's credential for this folder."""

from __future__ import annotations

import dataclasses
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, assert_never

from ecosemantic.bridge.credentials import CredentialStore
from ecosemantic.bridge.state import SIGNED_OUT_STATES
from ecosemantic.errors import Conflict, Invalid, Unavailable
from ecosemantic.tray.engine import (
    LOG_FILE,
    Engine,
    EngineState,
    Launcher,
    Process,
    core_command,
)
from ecosemantic.tray.home import APP, BRIDGE_LOG, TRAY_LOG, Home, TraySettings
from ecosemantic.tray.menu import Action, StartAtLogin

SIGN_IN = ("bridge", "sign-in")
SIGN_OUT = ("bridge", "sign-out")
WORDING = {SIGN_IN: "Sign-in", SIGN_OUT: "Sign-out"}
SIGNED_OUT_NOTICE = "The bridge signed out; sign in again"
REFUSALS = (Conflict, Invalid, Unavailable)


class Platform(Protocol):
    """This machine as the tray needs it: its notifications, its shell, its clipboard, Windows'
    start-at-login value, and the launcher that runs a program out of the tray's sight."""

    @property
    def launcher(self) -> Launcher: ...

    def notify(self, *, title: str, text: str) -> None: ...

    def refuse(self, *, title: str, text: str) -> None: ...

    def open_url(self, url: str) -> None: ...

    def open_folder(self, path: Path) -> None: ...

    def copy(self, text: str) -> None: ...

    def start_at_login(self) -> StartAtLogin: ...

    def set_start_at_login(self, enabled: bool) -> None: ...


@dataclass(frozen=True)
class Pending:
    """A bridge command the tray started and has not acted on yet: which command it is, and the
    process that carries it."""

    verb: tuple[str, str]
    process: Process

    @property
    def wording(self) -> str:
        """What the person is told when this command does not finish."""
        return WORDING[self.verb]


class Tray:
    """What a person's menu does: it opens and copies the engine's addresses, signs this folder in
    or out of the bridge, turns the bridge on or off, signing this folder in where no credential is
    kept so no engine serves bridged without one, starts the engine, sets Windows' start-at-login
    value, opens the logs, quits, and notifies once each time the bridge signs out or the engine
    fails. One lock serialises a menu action and a poll, which come from two threads."""

    def __init__(
        self,
        *,
        engine: Engine,
        platform: Platform,
        home: Home,
        python: Path,
        store: CredentialStore,
    ) -> None:
        self.engine = engine
        self.platform = platform
        self.home = home
        self.python = python
        self.store = store
        self.quit_requested = False
        self._pending: Pending | None = None
        self._own_sign_in = False
        self._notified: str | None = None
        self._refusals: set[str] = set()
        self._last: EngineState | None = None
        self._lock = threading.Lock()

    def state(self) -> EngineState:
        """The state the tray shows, acting on a bridge command that has finished and notifying
        once each time the state changes into a signed-out bridge or a failed engine."""
        with self._lock:
            return self._state()

    def act(self, action: Action) -> EngineState:
        """Do what one menu item says, and answer the state the tray last showed. It reads the
        addresses from that state and polls nothing, so a health the tray cannot read stops no
        action; once quit, nothing is started or opened at all."""
        with self._lock:
            if self.quit_requested:
                return self._last if self._last is not None else self._quiet()
            state = self._last if self._last is not None else self._quiet()
            if action == "open-page":
                self.platform.open_url(_known(state.page, what="page"))
            elif action == "copy-connector":
                self.platform.copy(_known(state.connector, what="connector address"))
            elif action == "connect":
                self._connect()
            elif action == "disconnect":
                self._bridged(False)
            elif action == "sign-in":
                self._command(SIGN_IN)
            elif action == "sign-out":
                self._command(SIGN_OUT)
            elif action == "start-at-login":
                self.platform.set_start_at_login(not self.platform.start_at_login().enabled)
            elif action == "open-logs":
                self.platform.open_folder(self.home.logs)
            elif action == "start-engine":
                self._start()
            elif action == "quit":
                self._quit()
            else:
                assert_never(action)
            return state

    def start(self) -> EngineState:
        """Start the engine, signing this folder in after it where the person keeps the bridge on
        and the store holds no credential, under the lock a poll and a menu action share."""
        with self._lock:
            return self._start()

    def _start(self) -> EngineState:
        """Start the engine, signing this folder in after it when the person keeps the bridge on and
        the store holds no credential: the engine serves this machine without the bridge until that
        sign-in ends 0, which turns the bridge on and starts the engine under it. A start that does
        not finish leaves the person's bridge setting as it was."""
        stored = self._stored()
        if self.engine.settings.bridge and not stored:
            kept = self.engine.settings
            try:
                state = self._unbridged()
                self._signing_in()
            except Exception:
                self.engine.settings = kept
                raise
            return dataclasses.replace(state, signed_in=False)
        return dataclasses.replace(self.engine.start(), signed_in=stored)

    def _unbridged(self) -> EngineState:
        """Start the engine without the bridge, turning the setting off in memory for the launch:
        the engine serves this machine while the browser's sign-in that follows lasts, and `_start`
        puts the setting back when the start does not finish."""
        self.engine.settings = self.engine.settings.model_copy(update={"bridge": False})
        return self.engine.start()

    def _state(self) -> EngineState:
        """The engine's state, with a finished bridge command acted on and the person told once
        about a bridge that signed out or an engine that failed. A health the tray refuses is
        written to its log once for each reason, and the engine reads as starting while the process
        still lives: it has not answered as our engine yet. Nothing is polled after quit."""
        if self.quit_requested:
            return self._last if self._last is not None else self._quiet()
        self._finished()
        try:
            state = self.engine.poll()
        except Unavailable as refusal:
            self._refused(str(refusal))
            state = self.engine.starting() if self.engine.running else self.engine.poll()
        state = dataclasses.replace(
            state, pending=self._pending is not None, signed_in=self._stored()
        )
        noticed = _noticed(state)
        if noticed is not None and noticed != self._notified:
            self.platform.notify(title=APP, text=self._notice(noticed))
        self._notified = noticed
        self._last = state
        return state

    def _quiet(self) -> EngineState:
        """A state for an action before any poll has run: the engine as this run leaves it."""
        return EngineState(
            kind="stopped",
            bridge="off",
            bridge_on=self.engine.settings.bridge,
            signed_in=self._stored(),
            pending=self._pending is not None,
        )

    def report(self, refusal: Conflict | Invalid | Unavailable) -> None:
        """Write what the core refused to the tray's log and tell the person, every time a menu
        action is refused: only the poll decides which repeats of a health refusal to keep."""
        with self._lock:
            self._write(f"{refusal}")
            self.platform.notify(title=APP, text=f"{refusal}")

    def report_error(self, error: BaseException) -> None:
        """Write an error no part of the core named to the tray's log with its traceback, and tell
        the person, each time it is reported: a poll decides for itself which repeats to keep."""
        reason = f"{type(error).__name__}: {error}"
        with self._lock:
            self._write(f"{reason}\n{''.join(traceback.format_exception(error))}")
            self.platform.notify(title=APP, text=f"The tray could not finish: {reason}")

    def _refused(self, reason: str) -> None:
        """Write a refusal the poll met to its log, once for each distinct reason, so a poll every
        two seconds does not grow it."""
        if reason in self._refusals:
            return
        self._refusals.add(reason)
        self._write(reason)

    def _write(self, line: str) -> None:
        """Append one line to the tray's log."""
        self.home.logs.mkdir(parents=True, exist_ok=True)
        with (self.home.logs / TRAY_LOG).open("a", encoding="utf-8") as log:
            log.write(f"{line}\n")

    def _quit(self) -> None:
        """Quit: end a bridge command that still runs, stop the engine, and start nothing again."""
        pending = self._pending
        if pending is not None:
            pending.process.terminate()
            self._pending = None
        self.quit_requested = True
        self.engine.stop()

    def _finished(self) -> None:
        """Act on a bridge command that has ended: the one that ended 0 turns the bridge on or off
        and starts the engine again, since only a new process reads a credential a sign-in left; a
        sign-in the tray starts by itself, on a start or on a Connect, that fails turns the bridge
        off, and any failure tells the person."""
        pending = self._pending
        if pending is None:
            return
        code = pending.process.poll()
        if code is None:
            return
        self._pending = None
        own = self._own_sign_in
        self._own_sign_in = False
        if code == 0:
            sign_in = pending.verb == SIGN_IN
            self._bridged(sign_in, restart=sign_in)
            return
        if own and pending.verb == SIGN_IN:
            self._save(self.engine.settings.model_copy(update={"bridge": False}))
        self.platform.notify(
            title=APP,
            text=f"{pending.wording} did not finish; see {self._bridge_log()}",
        )

    def _command(self, verb: tuple[str, str]) -> None:
        """Start one of the bridge's commands for this folder, whose ending the next state acts on;
        a second command is refused while one runs."""
        if self._pending is not None:
            raise Invalid("a bridge command is already running")
        command = core_command(
            self.python, *verb, "--systems-dir", str(self.engine.settings.models)
        )
        self._pending = Pending(
            verb=verb,
            process=self.platform.launcher.start(
                command, self.home.logs / BRIDGE_LOG, contained=False
            ),
        )

    def _stored(self) -> bool:
        """Whether this folder's credential store holds a sign-in."""
        return self.store.load() is not None

    def _signing_in(self) -> None:
        """Start the sign-in this folder needs, whose exit 0 turns the bridge on and starts the
        engine again under it, and whose failure turns the bridge off and leaves an engine without
        it running."""
        self._command(SIGN_IN)
        self._own_sign_in = True

    def _connect(self) -> None:
        """Turn the bridge on, signing in first when this folder holds no credential: the sign-in's
        exit 0 turns the bridge on, so no engine starts bridged without one."""
        if self._stored():
            self._bridged(True)
            return
        self._signing_in()

    def _bridged(self, enabled: bool, *, restart: bool = False) -> None:
        """Save whether the bridge is on and start the engine again under it, or for the first
        time; a sign-in's ending asks for the restart, since only a new process reads the credential
        that sign-in left."""
        self._save(self.engine.settings.model_copy(update={"bridge": enabled}), restart=restart)

    def _save(self, settings: TraySettings, *, restart: bool = False) -> None:
        """Write the settings where the tray reads them and start the engine under them, leaving an
        engine that already runs under them running unless a restart is asked for; an engine that
        will not stop keeps its settings, and the person is told once."""
        if self.engine.running and (restart or self.engine.settings != settings):
            self.engine.stop()
            if self.engine.running:
                self.platform.notify(title=APP, text=self._stuck())
                return
        settings.write(self.home.settings)
        self.engine.settings = settings
        if not self.engine.running:
            self.engine.start()

    def _notice(self, noticed: str) -> str:
        """What the person is told about the state the tray changed into."""
        if noticed == "failed":
            return f"The engine failed; see {self._log()}"
        return SIGNED_OUT_NOTICE

    def _stuck(self) -> str:
        """What the person is told about an engine that would not stop."""
        return f"The engine did not stop; see {self._log()}"

    def _log(self) -> str:
        """The engine's log, as a path under the folder the person installed."""
        return str(self.home.logs.relative_to(self.home.root) / LOG_FILE)

    def _bridge_log(self) -> str:
        """The bridge commands' log, as a path under the folder the person installed."""
        return str(self.home.logs.relative_to(self.home.root) / BRIDGE_LOG)


def _noticed(state: EngineState) -> str | None:
    """What the person is told about a state, if anything: an engine that failed, or a bridge that
    signed out."""
    if state.kind == "failed":
        return "failed"
    if state.bridge in SIGNED_OUT_STATES:
        return "signed-out"
    return None


def _known(value: str | None, *, what: str) -> str:
    """An address the engine's health names, refused by name when it names none, since a menu item
    that needs it is only enabled while it is there."""
    if value is None:
        raise Invalid(f"the engine's health names no {what} yet")
    return value


def dispatched(tray: Tray, action: Action) -> None:
    """One menu action as the tray's worker runs it: a refusal the core names is written to the
    tray's log and told to the person, so no traceback ends the worker thread."""
    try:
        tray.act(action)
    except REFUSALS as refusal:
        tray.report(refusal)
