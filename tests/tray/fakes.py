"""What the tray's tests put in place of the machine: a platform that records what it was asked to
do, a launcher whose processes the test ends, and a health reader the test sets."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ecosemantic.bridge.credentials import Credential
from ecosemantic.tray.menu import StartAtLogin


@dataclass
class FakeProcess:
    """A process the test ends: it answers the code it was given, and records a terminate, which a
    process that ignores one does not take."""

    pid: int
    command: list[str]
    log: Path
    code: int | None = None
    terminated: bool = False
    stubborn: bool = False

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        if not self.stubborn:
            self.code = -15

    def ended(self, code: int = 0) -> None:
        """End the process, as an engine ending by itself does."""
        self.code = code


@dataclass
class FakeLauncher:
    """A launcher that records each command it was given and answers a process the test ends. A
    bridge command ends at once with 0, as that command does, unless the test keeps it running; a
    launcher holding a refusal for the engine records the engine's command and raises it, and
    starts the bridge's."""

    processes: list[FakeProcess] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    logs: list[Path] = field(default_factory=list)
    contained: list[bool] = field(default_factory=list)
    ends_bridge: bool = True
    slowness: float = 0.0
    refuses_engine: Exception | None = None

    def start(self, command: list[str], log: Path, contained: bool) -> FakeProcess:
        if self.slowness:
            time.sleep(self.slowness)
        self.commands.append(command)
        if self.refuses_engine is not None and "serve" in command:
            raise self.refuses_engine
        process = FakeProcess(pid=1000 + len(self.processes), command=command, log=log)
        self.contained.append(contained)
        if "bridge" in command and self.ends_bridge:
            process.ended(0)
        self.processes.append(process)
        self.logs.append(log)
        return process


@dataclass
class FakeStore:
    """The credential store the tray reads: the credential the test keeps there, and how many reads
    it answered."""

    credential: Credential | None = None
    loads: int = 0
    where = "the test's store"

    def load(self) -> Credential | None:
        self.loads += 1
        return self.credential

    def save(self, credential: Credential) -> None:
        self.credential = credential

    def delete(self) -> None:
        self.credential = None


@dataclass
class Health:
    """The health reader: the document the engine answers, and the ports it was asked on."""

    document: dict[str, object] | None = None
    ports: list[int] = field(default_factory=list)

    def __call__(self, port: int) -> Mapping[str, object] | None:
        self.ports.append(port)
        return self.document


@dataclass
class Time:
    """A clock the test advances, and a sleep that advances it."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@dataclass
class FakePlatform:
    """The machine the tray acts on, recording what it was asked for."""

    launcher: FakeLauncher = field(default_factory=FakeLauncher)
    login: StartAtLogin = field(default_factory=lambda: StartAtLogin(enabled=False))
    urls: list[str] = field(default_factory=list)
    folders: list[Path] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    notices: list[tuple[str, str]] = field(default_factory=list)
    refusals: list[tuple[str, str]] = field(default_factory=list)
    logins: list[bool] = field(default_factory=list)

    def notify(self, *, title: str, text: str) -> None:
        self.notices.append((title, text))

    def refuse(self, *, title: str, text: str) -> None:
        self.refusals.append((title, text))

    def open_url(self, url: str) -> None:
        self.urls.append(url)

    def open_folder(self, path: Path) -> None:
        self.folders.append(path)

    def copy(self, text: str) -> None:
        self.copied.append(text)

    def start_at_login(self) -> StartAtLogin:
        return self.login

    def set_start_at_login(self, enabled: bool) -> None:
        self.logins.append(enabled)
        self.login = StartAtLogin(enabled=enabled)
