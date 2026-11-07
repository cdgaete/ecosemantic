"""The tray as a process: one for each person, its standard streams in a log, its pid written where
`--quit` reads it, and this machine's platform built where the tray starts."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from filelock import FileLock, Timeout

from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.settings import derived_port
from ecosemantic.settings.handover import ask_to_stop
from ecosemantic.tray.app import Platform, Tray
from ecosemantic.tray.engine import Engine, EngineState, asked, read_health, rotate
from ecosemantic.tray.home import APP, Home, TraySettings, home_for, written
from ecosemantic.tray.home import TRAY_LOG as LOG_FILE
from ecosemantic.tray.icons import icon_image

QUIT_SECONDS = 15.0
CHECKS = (
    EngineState(kind="starting", bridge="connecting", bridge_on=True),
    EngineState(kind="running", bridge="connected", bridge_on=True),
    EngineState(kind="running", bridge="offline", bridge_on=True),
    EngineState(kind="running", bridge="off", bridge_on=False),
    EngineState(kind="stopped", bridge="off", bridge_on=False),
    EngineState(kind="failed", bridge="off", bridge_on=False),
)
ENGINE_SECONDS = 10.0
LOCK_SECONDS = 0.1
WINDOWS_INVALID_ARGUMENT = 87


class QuitRefused(Exception):
    """A quit that cannot go on, which has written why to the tray's log."""


def streams_to(home: Home) -> None:
    """Give each standard stream this process does not have the tray's log for its output and the
    null device for its input, as a windowless interpreter starts with none of the three."""
    home.logs.mkdir(parents=True, exist_ok=True)
    written = home.logs / LOG_FILE
    written.touch()
    if sys.stdin is None:
        sys.stdin = open(os.devnull, encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = written.open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = written.open("a", encoding="utf-8", buffering=1)


def interpreter() -> Path:
    """The interpreter the tray runs the engine and the bridge's commands with: the `python.exe`
    beside the `pythonw.exe` a windowless tray runs as, refused when this machine has none."""
    console = Path(sys.executable).with_name("python.exe")
    if not console.is_file():
        raise Invalid(f"{console} is missing, and the tray runs the engine with it")
    return console


def platform_and_runner() -> tuple[Platform, Callable[[Tray], None]]:
    """This machine's platform and the loop that shows it, for the machine the tray runs on:
    another one refuses, naming it, since there is no tray without Windows' notification area."""
    if sys.platform == "win32":
        from ecosemantic.tray.windows import WindowsPlatform, run_tray

        return WindowsPlatform(), run_tray
    raise Invalid(f"the tray runs on Windows, and this machine is {sys.platform}")


def checked() -> int:
    """Build this machine's platform and the icon of every state the tray shows, and answer 0
    without showing any of them."""
    platform_and_runner()
    for state in CHECKS:
        icon_image(state)
    return 0


def quit_tray(
    home: Home,
    *,
    ask: Callable[[str, int, Path], bool] = ask_to_stop,
    health: Callable[[int], Mapping[str, object] | None] = read_health,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Ask the engine to stop and end the tray this folder's lock proves is running, answering 0
    when the folder came free of both, 3 when something of this tray still runs and 4 when the
    settings this folder holds cannot be read.

    The engine is asked first, from the settings this folder holds, and waited out: an engine that
    still answers its health after ten seconds stops the quit, and so does a settings file that
    cannot be read, which names that file and answers 4 so a caller tells the two apart. The lock
    then says whether a tray runs at all: one that comes free means no tray does, so `tray.pid` is
    stale and only removed. A lock a tray holds makes `tray.pid` current, and that process is
    ended. Neither answer is 1 or 2: a Python that fails to start exits 1, and one given an
    argument it does not know exits 2, so a caller reads those two as a tray that never answered."""
    try:
        settings = _settings(home)
    except QuitRefused:
        return 4
    if settings is not None and not _engine_stopped(settings, ask, health, clock, sleep):
        return 3
    try:
        with FileLock(home.lock, timeout=0):
            home.pid.unlink(missing_ok=True)
            return 0
    except Timeout:
        pass
    try:
        pid = _pid(home)
    except QuitRefused:
        return 3
    if pid is not None and not _ended(pid):
        return 3
    deadline = clock() + QUIT_SECONDS
    while clock() < deadline:
        try:
            with FileLock(home.lock, timeout=0):
                return 0
        except Timeout:
            sleep(LOCK_SECONDS)
    return 3


def _settings(home: Home) -> TraySettings | None:
    """The settings this folder holds, or none when it holds no file; a file that cannot be read
    stops the quit, naming it and the error."""
    if not home.settings.is_file():
        return None
    try:
        return TraySettings.read(home.settings)
    except (OSError, ValueError) as error:
        print(f"{home.settings} cannot be read: {error}", file=sys.stderr, flush=True)
        raise QuitRefused from error


def _engine_stopped(
    settings: TraySettings,
    ask: Callable[[str, int, Path], bool],
    health: Callable[[int], Mapping[str, object] | None],
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Ask the engine these settings name to stop, and say whether its health stopped answering
    within the wait. One that still answers is printed with its port and what it said, and so is a
    port that answers what no health of this tray is: another program holding it is not our engine,
    which cannot hold a port another one holds, so neither is waited out."""
    if not settings.models.is_dir():
        return True
    port = derived_port(settings.models)
    asked(settings, ask)
    deadline = clock() + ENGINE_SECONDS
    try:
        answered = health(port)
        while answered is not None and clock() < deadline:
            sleep(LOCK_SECONDS)
            answered = health(port)
    except Unavailable as other:
        print(f"{other}; no engine of this tray holds that port", file=sys.stderr, flush=True)
        return True
    if answered is not None:
        print(
            f"the engine on port {port} still answers {answered}",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def _pid(home: Home) -> int | None:
    """The process id this folder's pid file holds, or none when it holds no file; a file that
    cannot be read stops the quit, naming it."""
    if not home.pid.is_file():
        return None
    try:
        return int(home.pid.read_text(encoding="utf-8").strip())
    except ValueError as error:
        print(f"{home.pid} cannot be read: {error}", file=sys.stderr, flush=True)
        raise QuitRefused from error


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Run the tray: a second one for this folder leaves at once, `--quit` ends the first one, and
    `--first-run` signs the folder in before it starts the engine. The tray that runs rotates its
    log under the lock, before any stream opens it, since Windows renames no file another process
    holds open; a rotation the OS refuses is written as the first line this run writes, and the tray
    runs on."""
    home = home_for(os.environ if environ is None else environ)
    arguments = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    if arguments.quit:
        streams_to(home)
        return quit_tray(home)
    if arguments.check:
        return checked()
    lock = FileLock(home.lock, timeout=0)
    try:
        lock.acquire()
    except Timeout:
        streams_to(home)
        return 0
    try:
        home.logs.mkdir(parents=True, exist_ok=True)
        refused = ""
        try:
            rotate(home.logs / LOG_FILE)
        except OSError as error:
            refused = f"{home.logs / LOG_FILE} cannot be rotated: {error}"
        streams_to(home)
        if refused:
            print(refused, file=sys.stderr, flush=True)
        written(home.pid, f"{os.getpid()}\n")
        try:
            platform, run_tray = platform_and_runner()
        except (Invalid, Unavailable) as refusal:
            return _refused_at_start(home, str(refusal))
        try:
            settings = TraySettings.read(home.settings)
        except (OSError, ValueError) as error:
            return _refusal(home, platform, f"{home.settings} cannot be read: {error}")
        try:
            console = interpreter()
        except Invalid as error:
            return _refusal(home, platform, str(error))
        engine = _engine(home, platform, settings, console)
        tray = Tray(engine=engine, platform=platform, home=home, python=console)
        if arguments.first_run:
            tray.first_run()
        else:
            engine.start()
        run_tray(tray)
        return 0
    finally:
        home.pid.unlink(missing_ok=True)
        lock.release()


def _logged(home: Home, message: str) -> None:
    """Write a refusal to the tray's log, and to a terminal's standard error when that is not the
    log itself."""
    written = home.logs / LOG_FILE
    written.parent.mkdir(parents=True, exist_ok=True)
    with written.open("a", encoding="utf-8") as log:
        log.write(f"{message}\n")
        log.flush()
    if getattr(sys.stderr, "name", None) != str(written):
        print(message, file=sys.stderr, flush=True)


def _refusal(home: Home, platform: Platform, message: str) -> int:
    """Tell the person through the platform why the tray cannot start, and answer 1."""
    _logged(home, message)
    platform.refuse(title=APP, text=message)
    return 1


def _shown(message: str) -> None:
    """Show a refusal a person must dismiss; a machine without Windows' shell has no way of showing
    one, and its log line alone is the refusal there."""
    if sys.platform == "win32":
        from ecosemantic.tray.windows import refuse

        refuse(APP, message)


def _refused_at_start(home: Home, message: str) -> int:
    """Tell the person why the tray could not build its platform, through the message box that needs
    none, and answer 1."""
    _logged(home, message)
    _shown(message)
    return 1


def _parser() -> argparse.ArgumentParser:
    """The command's arguments: sign in on this first run, quit the tray that runs, or start one."""
    parser = argparse.ArgumentParser(
        prog="ecosemantic.tray",
        description="Manage the EcoSemantic Engine from the notification area.",
    )
    parser.add_argument(
        "--first-run", action="store_true", help="sign in before starting, when no sign-in is kept"
    )
    parser.add_argument("--quit", action="store_true", help="end the tray and the engine it runs")
    parser.add_argument(
        "--check",
        action="store_true",
        help="build the platform and the icons without showing them",
    )
    return parser


def _engine(home: Home, platform: Platform, settings: TraySettings, python: Path) -> Engine:
    """The engine these settings name, started through the platform's launcher with the console
    interpreter the tray runs it by."""
    return Engine(
        python=python,
        settings=settings,
        home=home,
        launcher=platform.launcher,
        health=read_health,
        stopper=ask_to_stop,
        clock=time.monotonic,
        sleep=time.sleep,
    )


def _ended(pid: int) -> bool:
    """End the process this pid names, which Windows ends with `TerminateProcess` and Linux with
    `SIGTERM`, and say whether it is gone; a process the person may not open stops the quit, naming
    the pid and the error."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as error:
        if _gone(error):
            return True
        print(f"the tray at pid {pid} cannot be ended: {error}", file=sys.stderr, flush=True)
        return False
    return True


def _gone(error: OSError) -> bool:
    """Whether ending a pid found nothing to end: a pid no process holds, on Windows as the invalid
    argument (WinError 87) that a pid no process holds answers with. A pid Windows has since given
    to another process opens as that process and would be ended, which is why `tray.pid` is trusted
    only while the tray's lock is held."""
    return isinstance(error, ProcessLookupError) or (
        getattr(error, "winerror", None) == WINDOWS_INVALID_ARGUMENT
    )


if __name__ == "__main__":
    raise SystemExit(main())
