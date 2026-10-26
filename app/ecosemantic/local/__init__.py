"""The local composition: one data directory and one product systems directory bound to the
server's ports, with a worker process on this machine for each run and each install, and the
accounts the environment holds."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from ecosemantic.backends.filesystem.activity import FilesystemActivity
from ecosemantic.backends.filesystem.installs import FilesystemInstalls, uploads_dir
from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.search import NativeSearch
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.compute.accounts import held_accounts
from ecosemantic.errors import Unavailable
from ecosemantic.events import EventBus, NotifyingStorage
from ecosemantic.installs.supervisor import LocalInstaller
from ecosemantic.mcp.context import AGENT, ServerContext
from ecosemantic.model.entities import Actor
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.runs.supervisor import LocalLauncher

DATA_DIR = "ECOSEMANTIC_DATA_DIR"
HOME = "ecosemantic"


def default_directories() -> tuple[Path, Path]:
    """The data directory and the product systems directory a command or a workspace takes when
    it is given none: `data` and `systems` under this person's EcoSemantic directory,
    `%LOCALAPPDATA%\\ecosemantic` on Windows, `~/Library/Application Support/ecosemantic` on macOS
    and `$XDG_DATA_HOME/ecosemantic` elsewhere, `~/.local/share` standing for an unset
    `XDG_DATA_HOME`; `ECOSEMANTIC_DATA_DIR` names the data directory instead. The caller makes
    the one it takes when it is missing."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise Unavailable("LOCALAPPDATA is unset", "pass --data-dir and --systems-dir")
        base = Path(local)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    named = os.environ.get(DATA_DIR)
    data = Path(named) if named else base / HOME / "data"
    return data, base / HOME / "systems"


def defaulted(path: Path | None, default: Path) -> Path:
    """The path given, or the default, made when it is missing."""
    if path is not None:
        return path
    default.mkdir(parents=True, exist_ok=True)
    return default


def _directory(path: Path, name: str) -> Path:
    if not path.is_dir():
        raise FileNotFoundError(f"{name} {str(path)!r} does not exist")
    return path


def build_context(
    data_dir: Path,
    systems_dir: Path,
    actor: Actor | None = None,
    view_url: str | None = None,
    agent: str | None = None,
    solver: str = "superlu",
    environ: Mapping[str, str] | None = None,
) -> ServerContext:
    """Bind one data directory and one product systems directory to the ports, calculating
    under the named solver, with the page's URL when one is served, the agent's name when the
    server was given one, and the accounts the environment holds."""
    data = _directory(data_dir, "data directory")
    systems = _directory(systems_dir, "product systems directory")
    store = NativeStore(data, solver)
    inventory = NativeInventory(store)
    resolver = InventoryResolver(inventory)
    bus = EventBus()

    def release() -> None:
        """Release what the bound backends and the resolver hold."""
        resolver.close()
        store.close()

    return ServerContext(
        inventory=inventory,
        search=NativeSearch(store),
        calculation=NativeCalculation(store),
        storage=NotifyingStorage(FilesystemStorage(systems, resolver), bus),
        resolver=resolver,
        actor=actor if actor is not None else AGENT,
        runs=FilesystemRuns(systems),
        activity=FilesystemActivity(systems),
        launcher=LocalLauncher(systems, data, systems, store.solver),
        installs=FilesystemInstalls(data),
        installer=LocalInstaller(data),
        systems_dir=systems,
        data_dir=data,
        uploads_dir=uploads_dir(data),
        credentials=held_accounts(os.environ if environ is None else environ),
        release=release,
        events=bus,
        view_url=view_url,
        agent=agent,
    )
