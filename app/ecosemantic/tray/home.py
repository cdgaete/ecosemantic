"""The tray's own files: the folder it keeps them in, and the settings the installer writes there
and the tray keeps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ecosemantic.errors import Invalid
from ecosemantic.files import write_whole

APP = "EcoSemantic Engine"
TRAY_ARGUMENTS = "-X utf8 -m ecosemantic.tray"
SETTINGS_FILE = "settings.json"
LOGS_DIR = "logs"
LOCK_FILE = "tray.lock"
PID_FILE = "tray.pid"
TRAY_LOG = "tray.log"
BRIDGE_LOG = "bridge.log"


@dataclass(frozen=True)
class Home:
    """The folder the tray owns: the settings it reads, the logs it writes, the lock one tray holds
    and the pid that tray writes."""

    root: Path

    @property
    def settings(self) -> Path:
        """The file the installer writes at a fresh install and every start reads, which the tray
        writes back when the person turns the bridge on or off."""
        return self.root / SETTINGS_FILE

    @property
    def logs(self) -> Path:
        """The folder the tray's log and the engine's log are written to."""
        return self.root / LOGS_DIR

    @property
    def lock(self) -> Path:
        """The file one tray holds for as long as it runs."""
        return self.root / LOCK_FILE

    @property
    def pid(self) -> Path:
        """The file a running tray writes its process id to, which `--quit` reads."""
        return self.root / PID_FILE


def home_for(environ: Mapping[str, str]) -> Home:
    """The tray's folder on this machine, under the local application data the environment names."""
    local = environ.get("LOCALAPPDATA")
    if not local:
        raise Invalid("LOCALAPPDATA is not set, and the tray keeps its settings and logs under it")
    return Home(Path(local) / APP)


def written(path: Path, text: str) -> None:
    r"""Write a small file whole, its `\n` line endings kept, so a reader never sees half of it."""
    write_whole(path, text.encode("utf-8"))


class TraySettings(BaseModel):
    """What the tray acts on: the two folders the engine serves, which the installer writes at a
    fresh install, and whether the bridge is on, which the installer leaves out and which reads as
    on."""

    model_config = ConfigDict(frozen=True)

    databases: Path
    models: Path
    bridge: bool = True

    @classmethod
    def read(cls, path: Path) -> TraySettings:
        """The settings a file holds, written as UTF-8 with or without a byte-order mark."""
        return cls.model_validate_json(path.read_text(encoding="utf-8-sig"))

    def write(self, path: Path) -> None:
        """Save the settings where that file is, replaced whole so a reader never sees half of
        them."""
        written(path, f"{self.model_dump_json(indent=2)}\n")


def windowless(executable: Path) -> Path:
    """The `pythonw.exe` beside the interpreter the tray runs as, refused when it is not there."""
    console = executable.with_name("pythonw.exe")
    if not console.is_file():
        raise Invalid(f"{console} is missing, and Windows runs the tray with it at login")
    return console


def login_command(executable: Path) -> str:
    """The command Windows runs at login, as the product's Run value holds it: the `pythonw.exe`
    beside this interpreter, quoted, with the arguments the tray is started with."""
    return f'"{windowless(executable)}" {TRAY_ARGUMENTS}'
