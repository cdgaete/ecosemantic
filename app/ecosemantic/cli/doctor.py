"""What an install holds and lacks, as one report: the interpreter, the package, the solver, the
directories, the databases, the view's port, telemetry and each client's configuration."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import sys
from pathlib import Path

from ecosemantic.cli.clients import CLIENTS, SERVER, held, placed
from ecosemantic.errors import EcoSemanticError, Invalid, Unavailable
from ecosemantic.local import default_directories
from ecosemantic.serve import bind, settings_from
from ecosemantic.telemetry import status


def _directory(path: Path) -> dict[str, object]:
    return {"path": str(path), "exists": path.is_dir()}


def _view(systems: Path) -> dict[str, object]:
    settings = settings_from(os.environ, systems)
    try:
        bind(settings.host, settings.port).close()
    except OSError:
        return {"host": settings.host, "port": settings.port, "free": False}
    return {"host": settings.host, "port": settings.port, "free": True}


def _client(client: str) -> dict[str, object]:
    try:
        where = placed(client, None)
    except EcoSemanticError as error:
        return {"documented": False, "message": str(error)}
    if not where.path.is_file():
        return {"path": str(where.path), "present": False}
    try:
        _, servers = held(where)
    except EcoSemanticError as error:
        return {"path": str(where.path), "present": True, "error": str(error)}
    configured = servers.get(SERVER)
    if not isinstance(configured, dict):
        return {"path": str(where.path), "present": False}
    command = str(configured.get("command", ""))
    return {
        "path": str(where.path),
        "present": True,
        "command": command,
        "command_exists": Path(command).is_file(),
    }


def _telemetry(data: Path) -> dict[str, object]:
    try:
        return status(os.environ, data)
    except (Invalid, Unavailable) as error:
        return {"error": str(error)}


def directories(data: Path | None, systems: Path | None) -> tuple[Path, Path]:
    """The directories named, or this platform's defaults for the ones that are not; none is
    made."""
    default_data, default_systems = default_directories()
    return (
        data if data is not None else default_data,
        systems if systems is not None else default_systems,
    )


def report(data: Path, systems: Path, databases: object) -> dict[str, object]:
    """The install as it stands, with the databases the data directory holds as the command
    read them; nothing is made, started or written."""
    return {
        "python": {"executable": sys.executable, "version": platform.python_version()},
        "ecosemantic": importlib.metadata.version("ecosemantic"),
        "solver": {"pardiso": importlib.util.find_spec("pypardiso") is not None},
        "directories": {"data": _directory(data), "systems": _directory(systems)},
        "databases": databases,
        "view": _view(systems),
        "telemetry": _telemetry(data),
        "clients": {client: _client(client) for client in CLIENTS},
    }
