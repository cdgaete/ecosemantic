"""What the Windows installer does on a runner, from the first silent install to the last silent
uninstall: a databases folder past the length Windows reads is refused before anything is copied; a
silent install into a folder named with a space and an accented letter makes both data folders and
writes `settings.json`, the Run value and the Start menu shortcut; the engine the tray starts
answers `/health` and stops on its own nonce; the tray builds its icon, starts an engine of its own
and quits; a silent upgrade over both keeps `settings.json` byte for byte and leaves no process of
the install behind; and a silent uninstall removes the program, the app's own folder and the Run
value while both data folders stay.

A failing check prints the logs the install and the uninstall wrote, the process table, both
folders the install writes, the Run value, `settings.json` and the logs the tray and the engine
wrote, so one run says what went wrong, and every process this script starts is ended before it
returns.

    python -X utf8 scripts/installer_check.py INSTALLER
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.settings import derived_port
from ecosemantic.settings.handover import ask_to_stop
from ecosemantic.tray.engine import engine_command, read_health
from ecosemantic.tray.home import APP, Home, TraySettings, login_command

if sys.platform == "win32":
    import winreg

REPOSITORY = Path(__file__).resolve().parents[1]
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
TASKKILL = r"C:\Windows\System32\taskkill.exe"
CREATE_NO_WINDOW = 0x08000000
QUIET = {"ECOSEMANTIC_TELEMETRY": "off"}
SILENT = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")
TRAY = ("-X", "utf8", "-m", "ecosemantic.tray")
LOOPBACK = "127.0.0.1"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "EcoSemantic Engine"
FOLDER = "EcoSemantic José Muñoz"
LIMIT = 259
OVERLONG = 200
INSTALL_SECONDS = 900.0
UNINSTALL_SECONDS = 300.0
HEALTH_SECONDS = 60.0
TRAY_SECONDS = 120.0
QUIT_SECONDS = 120.0
SETTLE_SECONDS = 90.0
SETTLE_POLL = 2.0
POLL_SECONDS = 0.5
DUMPED_LINES = 200
PROCESS_TABLE = (
    "$ProgressPreference = 'SilentlyContinue'; "
    "$ErrorActionPreference = 'Stop'; "
    "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
    "@(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, CommandLine) "
    "| ConvertTo-Json -Depth 3"
)


class Unmet(Exception):
    """One check that did not hold, its message saying what it saw instead."""


@dataclass(frozen=True)
class Installed:
    """Where a silent install of this product puts what it installs."""

    program: Path
    home: Home

    @property
    def python(self) -> Path:
        """The console interpreter the payload carries, which runs the engine."""
        return self.program / "python" / "python.exe"

    @property
    def pythonw(self) -> Path:
        """The windowless interpreter the tray runs as."""
        return self.program / "python" / "pythonw.exe"

    @property
    def uninstaller(self) -> Path:
        """The uninstaller Inno writes beside the payload."""
        return self.program / "unins000.exe"


def env() -> dict[str, str]:
    """This machine's environment with the product's telemetry off: a run of the installer is not a
    person's use of it, and a server counts its starts unless it is told not to."""
    return {**os.environ, **QUIET}


def long(path: Path) -> Path:
    """The path by its long name: a runner's temporary folder is spelled with the 8.3 name of the
    account that made it, and Windows reads the two spellings as different folders."""
    return Path(os.path.realpath(path))


def where_installed() -> Installed:
    """The two folders a per-user install of this product writes, by their long names."""
    held = os.environ.get("LOCALAPPDATA")
    if not held:
        raise SystemExit("LOCALAPPDATA is unset, and the install's folders are named under it")
    local = long(Path(held))
    return Installed(program=local / "Programs" / APP, home=Home(local / APP))


def budgets() -> dict[str, int]:
    """The two folders' budgets the installer was compiled with, read from the defines the build
    writes beside its script."""
    held = REPOSITORY / "installer" / "windows" / "defines.iss"
    defines = dict(
        re.findall(r"^#define (\w+) (\d+)$", held.read_text(encoding="utf-8"), re.MULTILINE)
    )
    return {name: int(value) for name, value in defines.items() if name.endswith("Budget")}


def room(folder: Path, budget: int) -> str:
    """How much of Windows' path limit a folder leaves, as its length, the separator and the budget
    the build measured beneath it against the 259 characters Windows reads."""
    reach = len(str(folder)) + 1 + budget
    return f"{len(str(folder))} + 1 + {budget} = {reach} of {LIMIT}"


def run(command: list[str], seconds: float, what: str) -> tuple[int, str]:
    """Run one program to its end and answer its exit code and its standard output. Its standard
    error is printed when it said anything: the product's own programs are given `-X utf8`, so a
    diagnostic there is UTF-8. A program still running at `seconds` is ended, and the wait refused
    naming it."""
    try:
        ended = subprocess.run(
            command,
            capture_output=True,
            timeout=seconds,
            creationflags=CREATE_NO_WINDOW,
            env=env(),
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        raise Unmet(f"{what} did not end within {seconds:g} s: {command}") from expired
    errors = ended.stderr.decode("utf-8", errors="replace")
    if errors.strip():
        print(errors.strip())
    return ended.returncode, ended.stdout.decode("utf-8", errors="replace")


def started(command: list[str], log: Path) -> subprocess.Popen[bytes]:
    """Start one of the product's programs the way the tray starts its engine: no console window,
    its input the null device, its output appended to `log`, and no telemetry counted."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
            env=env(),
        )


def wait_for(what: str, seconds: float, probe: Callable[[], bool]) -> float:
    """Poll `probe` until it answers True and answer how long that took; a wait that runs out is
    refused naming what it waited for and for how long."""
    began = time.monotonic()
    deadline = began + seconds
    while time.monotonic() < deadline:
        if probe():
            return time.monotonic() - began
        time.sleep(POLL_SECONDS)
    raise Unmet(f"waited {seconds:g} s for {what}")


def processes() -> list[dict[str, object]]:
    """Every process this machine runs, with its command line, as Windows reports them: the command
    sets PowerShell's output encoding to UTF-8, since a pipe otherwise carries the console's code
    page and a command line holding an accented letter would not survive it."""
    code, text = run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", PROCESS_TABLE],
        120,
        "the process table",
    )
    if code != 0:
        raise Unmet(f"the process table could not be read, PowerShell answered {code}")
    found = json.loads(text) if text.strip() else []
    return found if isinstance(found, list) else [found]


def named(folder: Path) -> list[int]:
    """The processes whose command line names a folder, which is how a process of the install is
    told from every other one on the machine."""
    return sorted(
        int(row["ProcessId"])
        for row in processes()
        if isinstance(row.get("CommandLine"), str) and str(folder) in str(row["CommandLine"])
    )


def wait_for_removal(folder: Path, seconds: float) -> float:
    """Wait until a folder is gone and no process's command line names it, answering how long that
    took. Inno's uninstaller exits before the clone it starts removes `{app}`, so the folder
    outlives the process a caller waited on."""
    began = time.monotonic()
    deadline = began + seconds
    while time.monotonic() < deadline and folder.exists():
        time.sleep(POLL_SECONDS)
    if folder.exists():
        raise Unmet(f"waited {seconds:g} s for {folder} to be removed")
    while time.monotonic() < deadline:
        left = named(folder)
        if not left:
            return time.monotonic() - began
        time.sleep(SETTLE_POLL)
    raise Unmet(f"the processes {named(folder)} still name {folder} after {seconds:g} s")


def wait_then_kill(folders: tuple[Path, ...], seconds: float) -> list[int]:
    """Wait for the processes whose command lines name these folders, and answer the ones still
    there when the wait ran out: an uninstall clone removing `{app}` is waited for, and killed only
    once it has had its time. Prints what it waits for, and how long the wait took."""
    began = time.monotonic()
    deadline = began + seconds
    left = sorted({pid for folder in folders for pid in named(folder)})
    if left:
        print(
            f"waiting up to {seconds:g} s for {left} to end, whose command lines name the install"
        )
    while left and time.monotonic() < deadline:
        time.sleep(SETTLE_POLL)
        left = sorted({pid for folder in folders for pid in named(folder)})
    if left:
        print(f"waited {time.monotonic() - began:.1f} s and {left} still run, so they are ended")
    for pid in left:
        subprocess.run(
            [TASKKILL, "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            env=env(),
            check=False,
        )
    return left


def run_value() -> str | None:
    """The command the Run value holds, or None when the value is not there."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            held, _ = winreg.QueryValueEx(key, RUN_VALUE)
    except FileNotFoundError:
        return None
    return str(held)


def shortcut() -> Path:
    """The Start menu shortcut the install writes, under the per-user Programs folder."""
    roaming = os.environ.get("APPDATA")
    if not roaming:
        raise SystemExit("APPDATA is unset, and the shortcut is named under it")
    programs = long(Path(roaming)) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / f"{APP}.lnk"


def tail(path: Path) -> str:
    """The last lines of a log — Inno writes its own as UTF-8 with a byte-order mark and the
    product's Python as UTF-8 — or a line saying the file is not there."""
    if not path.is_file():
        return f"{path} is not there"
    held = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    return "\n".join(held[-DUMPED_LINES:])


def listing(folder: Path) -> str:
    """One folder's own entries, each marked as a folder or given with its size, or a line saying
    the folder is not there."""
    if not folder.is_dir():
        return f"{folder} is not there"
    held = [
        f"{entry.name}\\" if entry.is_dir() else f"{entry.name} ({entry.stat().st_size} bytes)"
        for entry in sorted(folder.iterdir())
    ]
    return ", ".join(held) if held else "empty"


def section(what: str, produce: Callable[[], str]) -> str:
    """One section of the dump, or what reading it raised: a dump that fails must not hide the
    check that failed before it."""
    try:
        return f"--- {what}\n{produce()}"
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, Unmet) as error:
        return f"--- {what}\n{type(error).__name__}: {error}"


def dump(where: Installed, logs: tuple[Path, ...]) -> None:
    """Print what a failed check saw: the logs the install and the uninstall wrote, the process
    table, both folders the install writes, the Run value, `settings.json` and the logs the product
    wrote."""
    for log in logs:
        print(section(f"the log {log}", lambda log=log: tail(log)))
    print(
        section(
            "the processes this machine runs",
            lambda: "\n".join(
                f"{row['ProcessId']} (parent {row['ParentProcessId']}): {row['CommandLine']}"
                for row in processes()
            ),
        )
    )
    print(section(f"{where.program}", lambda: listing(where.program)))
    print(section(f"{where.program / 'python'}", lambda: listing(where.program / "python")))
    print(section(f"{where.home.root}", lambda: listing(where.home.root)))
    print(section(f"the Run value {RUN_VALUE}", lambda: str(run_value())))
    print(
        section(
            f"{where.home.settings}",
            lambda: where.home.settings.read_text(encoding="utf-8"),
        )
    )
    held = sorted(where.home.logs.glob("*.log")) if where.home.logs.is_dir() else []
    for written in held:
        print(section(str(written), lambda written=written: tail(written)))


def end_everything(where: Installed, ours: list[subprocess.Popen[bytes]]) -> None:
    """End what the install and this script started, the product's own way first: the tray's
    `--quit`, which stops its engine and gives up its lock; then whatever still names one of the
    install's folders, waited for before it is killed; then the handles this script holds. Each
    stage stands alone, so one that raises does not skip the others. Prints what it ended."""
    try:
        if where.pythonw.is_file():
            code, _ = run([str(where.pythonw), *TRAY, "--quit"], QUIT_SECONDS, "the tray's --quit")
            print(f"the tray's --quit answered {code}")
    except Exception as failure:
        print(f"the tray's --quit raised {type(failure).__name__}: {failure}")
    try:
        for pid in wait_then_kill((where.program, where.home.root), SETTLE_SECONDS):
            print(f"ended {pid}, whose command line names one of the install's folders")
    except Exception as failure:
        print(
            f"the processes naming the install's folders raised {type(failure).__name__}: {failure}"
        )
    for held in ours:
        try:
            if held.poll() is None:
                held.terminate()
                try:
                    held.wait(timeout=SETTLE_SECONDS)
                except subprocess.TimeoutExpired:
                    held.kill()
                    held.wait(timeout=SETTLE_SECONDS)
            print(f"the process this script started, {held.pid}, ended {held.returncode}")
        except Exception as failure:
            print(f"the process {held.pid} raised {type(failure).__name__}: {failure}")


def install(setup: Path, arguments: list[str], log: Path) -> int:
    """Run the installer silently with these arguments, each written whole because Inno reads its
    own command line, and answer its exit code."""
    began = time.monotonic()
    code, output = run(
        [str(setup), *arguments, *SILENT, f"/LOG={log}"], INSTALL_SECONDS, "the install"
    )
    if output.strip():
        print(output.strip())
    print(f"the installer ended {code} after {time.monotonic() - began:.1f} s")
    return code


def refused_folder(setup: Path, where: Installed, databases: Path, log: Path) -> None:
    """The first check: a databases folder whose longest path passes what Windows reads is refused
    before anything is copied."""
    over = Path(f"{databases.drive}\\{'d' * (OVERLONG - 3)}")
    code = install(setup, [f"/DATABASES={over}"], log)
    if code == 0:
        raise Unmet(f"the install took {over}, which is {len(str(over))} characters long")
    if where.pythonw.exists():
        raise Unmet(f"the install refused {over} and copied the payload into {where.program}")
    print(
        f"refused a databases folder of {len(str(over))} characters: "
        f"the install ended {code}, copying nothing"
    )


def installed(setup: Path, where: Installed, databases: Path, models: Path, log: Path) -> None:
    """The second check: a silent install into both folders makes them, and writes the payload,
    `settings.json` with exactly those folders, the Run value and the Start menu shortcut."""
    code = install(setup, [f"/DATABASES={databases}", f"/MODELS={models}"], log)
    if code != 0:
        raise Unmet(f"the silent install into {databases} and {models} ended {code}")
    if not where.pythonw.is_file():
        raise Unmet(f"the install left no {where.pythonw}")
    saved = TraySettings.read(where.home.settings)
    if str(saved.databases) != str(databases) or str(saved.models) != str(models):
        raise Unmet(
            f"{where.home.settings} holds {str(saved.databases)!r} and {str(saved.models)!r}, "
            f"and the install was given {str(databases)!r} and {str(models)!r}"
        )
    for made in (databases, models):
        if not made.is_dir():
            raise Unmet(f"the install made no {made}, so the engine it starts cannot serve it")
    held = run_value()
    wanted = login_command(where.pythonw)
    if held != wanted:
        raise Unmet(f"the Run value holds {held!r}, and the tray's command is {wanted!r}")
    start = shortcut()
    if not start.is_file():
        raise Unmet(f"the install wrote no Start menu shortcut at {start}")
    measured = budgets()
    print(
        f"installed on {databases} ({room(databases, measured['DatabasesBudget'])}) and "
        f"{models} ({room(models, measured['ModelsBudget'])}), with the Run value and {start.name}"
    )


def engine_answers(where: Installed, settings: TraySettings, log: Path) -> None:
    """The third check: the engine the tray starts, run here, serves both folders, answers `/health`
    within a minute and stops on the nonce its systems folder proves."""
    port = derived_port(settings.models)
    engine = started(
        engine_command(where.python, settings.model_copy(update={"bridge": False})), log
    )
    try:
        answered = wait_for(
            f"the engine's /health on port {port}",
            HEALTH_SECONDS,
            lambda: read_health(port) is not None,
        )
        print(f"the engine answered /health on port {port} after {answered:.1f} s")
        if not ask_to_stop(LOOPBACK, port, settings.models):
            raise Unmet(f"the engine on port {port} refused the nonce its systems folder proves")
        stopped = wait_for(
            f"the engine {engine.pid} to end", SETTLE_SECONDS, lambda: engine.poll() is not None
        )
        print(f"the engine ended on its nonce after {stopped:.1f} s")
    finally:
        if engine.poll() is None:
            engine.terminate()
            try:
                engine.wait(timeout=SETTLE_SECONDS)
            except subprocess.TimeoutExpired:
                engine.kill()
                engine.wait(timeout=SETTLE_SECONDS)


def tray_answers(
    where: Installed, settings: TraySettings, log: Path, ours: list[subprocess.Popen[bytes]]
) -> None:
    """The fourth check: the tray builds its icon and its platform without showing them, and, with
    the bridge turned off in `settings.json`, starts an engine that answers `/health`."""
    code, _ = run([str(where.pythonw), *TRAY, "--check"], SETTLE_SECONDS, "the tray's --check")
    if code != 0:
        raise Unmet(f"the tray's --check ended {code}")
    without = TraySettings(databases=settings.databases, models=settings.models, bridge=False)
    without.write(where.home.settings)
    port = derived_port(without.models)
    tray = started([str(where.pythonw), *TRAY], log)
    ours.append(tray)
    answered = wait_for(
        f"the tray's engine on port {port}",
        TRAY_SECONDS,
        lambda: read_health(port) is not None,
    )
    print(
        f"the tray built its icon and started an engine that answered /health on port {port} "
        f"after {answered:.1f} s"
    )


def upgraded(setup: Path, where: Installed, log: Path) -> None:
    """The fifth check: a silent upgrade over the running tray and its engine keeps `settings.json`
    byte for byte and the Run value, and leaves no process of the install behind."""
    before = where.home.settings.read_bytes()
    code = install(setup, [], log)
    if code != 0:
        raise Unmet(f"the silent upgrade over a running tray ended {code}")
    after = where.home.settings.read_bytes()
    if after != before:
        raise Unmet(
            f"the upgrade rewrote {where.home.settings}: it held {before.decode('utf-8')!r} "
            f"and holds {after.decode('utf-8')!r}"
        )
    if run_value() is None:
        raise Unmet(f"the upgrade removed the Run value {RUN_VALUE}")
    left = named(where.program) + named(where.home.root)
    if left:
        raise Unmet(f"the upgrade left the processes {left} that name the install's folders")
    print(
        f"the upgrade ended {code}, kept {where.home.settings.name} byte for byte, "
        "and left no process of the install"
    )


def uninstalled(where: Installed, databases: Path, models: Path, log: Path) -> None:
    """The sixth check: a silent uninstall removes the program, the app's own folder and the Run
    value, and keeps both data folders."""
    began = time.monotonic()
    code, _ = run(
        [str(where.uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", f"/LOG={log}"],
        UNINSTALL_SECONDS,
        "the uninstall",
    )
    print(f"the uninstaller ended {code} after {time.monotonic() - began:.1f} s")
    if code != 0:
        raise Unmet(f"the silent uninstall ended {code}")
    took = wait_for_removal(where.program, UNINSTALL_SECONDS)
    print(f"{where.program} and the processes naming it were gone after {took:.1f} s")
    if where.home.root.exists():
        raise Unmet(f"the uninstall left {where.home.root}")
    if run_value() is not None:
        raise Unmet(f"the uninstall left the Run value {RUN_VALUE}")
    for kept in (databases, models):
        if not kept.is_dir():
            raise Unmet(f"the uninstall removed the data folder {kept}")
    print(
        f"the uninstall removed the program, {where.home.root.name} and the Run value, "
        f"and kept {databases} and {models}"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the six checks in the order a person meets them, print what each proved, and print what
    a failing check saw."""
    parser = argparse.ArgumentParser(prog="installer_check", description=__doc__)
    parser.add_argument("installer", type=Path, help="the installer the workflow built")
    arguments = parser.parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("this check proves the Windows installer: it runs on Windows")
    setup = long(arguments.installer)
    if not setup.is_file():
        raise SystemExit(f"{setup} is not there")
    where = where_installed()
    if where.program.exists() or where.home.settings.exists():
        raise SystemExit(
            f"{where.program} or {where.home.settings} is already there, "
            "and this check installs where neither is"
        )
    with tempfile.TemporaryDirectory(prefix=FOLDER) as temporary:
        work = long(Path(temporary))
        databases, models = work / "databases", work / "models"
        logs = (work / "install.log", work / "uninstall.log")
        ours: list[subprocess.Popen[bytes]] = []
        try:
            refused_folder(setup, where, databases, logs[0])
            installed(setup, where, databases, models, logs[0])
            settings = TraySettings.read(where.home.settings)
            engine_answers(where, settings, where.home.logs / "engine.log")
            tray_answers(where, settings, where.home.logs / "check-tray.log", ours)
            upgraded(setup, where, logs[0])
            uninstalled(where, databases, models, logs[1])
            return 0
        except Unmet as failure:
            print(f"FAILED: {failure}")
            dump(where, logs)
            return 1
        except Exception as failure:
            print(traceback.format_exc())
            print(f"FAILED: {type(failure).__name__}: {failure}")
            dump(where, logs)
            return 1
        finally:
            end_everything(where, ours)


if __name__ == "__main__":
    raise SystemExit(main())
