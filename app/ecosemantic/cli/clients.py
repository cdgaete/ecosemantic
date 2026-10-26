"""The chatbots `ecosemantic connect` configures: where each keeps its MCP configuration on this
platform, as its own documentation states, and the entry that starts this server over stdio.

Claude Desktop keeps `claude_desktop_config.json` under `~/Library/Application Support/Claude`
on macOS and `%APPDATA%\\Claude` on Windows, servers under `mcpServers`
(modelcontextprotocol.io/quickstart/user); it documents no location on Linux. Cursor keeps
`~/.cursor/mcp.json`, servers under `mcpServers`, each with `type` `stdio`
(cursor.com/docs/context/mcp). VS Code keeps a workspace's `.vscode/mcp.json`, servers under
`servers`, each with `type` `stdio` (code.visualstudio.com/docs/copilot/customization/mcp-servers);
its user configuration has no documented path, only the command that opens it.
"""

from __future__ import annotations

import json
import os
import sys
import sysconfig
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.errors import Invalid, NotSupported, Unavailable

SERVER = "ecosemantic"
CLIENTS = ("claude-desktop", "cursor", "vscode")
DISPLAYS = ("DISPLAY", "WAYLAND_DISPLAY")


@dataclass(frozen=True)
class Placed:
    """Where one client keeps its configuration, the key its servers sit under, and whether an
    entry names its transport."""

    client: str
    path: Path
    key: str
    typed: bool


def installed_command() -> Path:
    """The `ecosemantic` command installed beside the interpreter running this one."""
    name = "ecosemantic.exe" if sys.platform == "win32" else "ecosemantic"
    return Path(sysconfig.get_path("scripts")) / name


def placed(client: str, workspace: Path | None) -> Placed:
    """Where `client` keeps its configuration on this platform; NotSupported on a platform it
    has no build for, Invalid for VS Code with no workspace named. Claude Desktop on Linux keeps
    it in Electron's application data, `$XDG_CONFIG_HOME` or `~/.config`."""
    if client == "claude-desktop":
        if sys.platform == "darwin":
            folder = Path.home() / "Library" / "Application Support" / "Claude"
        elif sys.platform == "win32":
            folder = Path(os.environ["APPDATA"]) / "Claude"
        elif sys.platform == "linux":
            configured = os.environ.get("XDG_CONFIG_HOME")
            folder = (Path(configured) if configured else Path.home() / ".config") / "Claude"
        else:
            raise NotSupported(f"Claude Desktop has no build for {sys.platform}")
        return Placed(client, folder / "claude_desktop_config.json", "mcpServers", False)
    if client == "cursor":
        return Placed(client, Path.home() / ".cursor" / "mcp.json", "mcpServers", True)
    if workspace is None:
        raise Invalid(
            "VS Code documents a path only for a workspace's configuration: name the folder "
            "with --workspace"
        )
    return Placed(client, workspace / ".vscode" / "mcp.json", "servers", True)


def found() -> list[str]:
    """The chatbots this platform holds a configuration folder for, in `CLIENTS` order. One whose
    location its documentation does not name, and VS Code with no workspace, are not found."""
    found_clients: list[str] = []
    for client in CLIENTS:
        try:
            where = placed(client, None)
        except (Invalid, NotSupported):
            continue
        if where.path.parent.is_dir():
            found_clients.append(client)
    return found_clients


def entry(where: Placed, command: Path, environ: Mapping[str, str]) -> dict[str, object]:
    """The entry that starts this server over stdio with the command named, and on Linux the
    non-empty display variables of `environ` beside it: Claude Desktop starts its servers
    without either, and the server opens no page without one."""
    started: dict[str, object] = {"command": str(command), "args": ["serve"]}
    shown = {name: environ[name] for name in DISPLAYS if environ.get(name)}
    if sys.platform == "linux" and shown:
        started["env"] = shown
    return {"type": "stdio", **started} if where.typed else started


def held(where: Placed) -> tuple[dict[str, object], dict[str, object]]:
    """The configuration the client holds and the servers in it, both empty when it holds none;
    Invalid naming the file when it is not a JSON object whose servers are an object."""
    if not where.path.is_file():
        return {}, {}
    try:
        document = json.loads(where.path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Invalid(
            f"{where.path} is not valid JSON: {error.msg} at line {error.lineno}"
        ) from error
    if not isinstance(document, dict):
        raise Invalid(f"{where.path} holds no JSON object")
    servers = document.get(where.key, {})
    if not isinstance(servers, dict):
        raise Invalid(f"{where.path} holds {where.key!r} as something other than an object")
    return document, servers


def connect(client: str, workspace: Path | None, command: Path | None) -> dict[str, object]:
    """Write this server into `client`'s configuration beside the servers it holds, and answer
    where, with which command and whether it replaced an entry of the same name."""
    started = command if command is not None else installed_command()
    if not started.is_file():
        raise Unavailable(f"no ecosemantic command at {started}", "pass --command")
    where = placed(client, workspace)
    if client == "vscode":
        if workspace is None or not workspace.is_dir():
            raise Unavailable(f"the workspace {workspace} does not exist")
        where.path.parent.mkdir(exist_ok=True)
    elif not where.path.parent.is_dir():
        raise Unavailable(f"{where.path.parent} does not exist", f"install and open {client} first")
    document, servers = held(where)
    replaced = SERVER in servers
    servers = {**servers, SERVER: entry(where, started, os.environ)}
    staged = where.path.with_name(where.path.name + ".partial")
    staged.write_text(json.dumps({**document, where.key: servers}, indent=2) + "\n", "utf-8")
    os.replace(staged, where.path)
    return {
        "client": client,
        "path": str(where.path),
        "server": SERVER,
        "command": str(started),
        "replaced": replaced,
    }
