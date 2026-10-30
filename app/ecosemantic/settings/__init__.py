"""The server's settings: the transport it serves under, the port a systems directory always
answers on, the socket it binds, and what serve was told about them, none of which loads the
server or the page."""

from __future__ import annotations

import hashlib
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from ecosemantic.errors import Invalid

LOOPBACK = ("127.0.0.1", "localhost", "::1")
Transport = Literal["stdio", "http"]
TRANSPORTS: tuple[str, ...] = get_args(Transport)
PORT_FLOOR = 10000
PORT_CEILING = 32767


def _workspace_bytes(systems_dir: Path) -> bytes:
    return hashlib.sha256(str(systems_dir.resolve()).encode()).digest()


def derived_port(systems_dir: Path) -> int:
    """The port one systems directory always answers on, clear of every ephemeral range."""
    span = PORT_CEILING - PORT_FLOOR + 1
    return PORT_FLOOR + int.from_bytes(_workspace_bytes(systems_dir)[:4], "big") % span


def workspace_digest(systems_dir: Path) -> str:
    """What a holder of the port answers to identify the directory it serves."""
    return _workspace_bytes(systems_dir).hex()[:16]


@dataclass(frozen=True)
class ViewSettings:
    """What serve was told about the listener and the transport."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 0
    url: str | None = None
    transport: Transport = "stdio"
    token: bool = False
    open: bool = True


def settings_from(
    environ: Mapping[str, str],
    systems_dir: Path,
    enabled: bool | None = None,
    host: str | None = None,
    port: int | None = None,
    url: str | None = None,
    transport: str | None = None,
    token: bool | None = None,
    opening: bool | None = None,
) -> ViewSettings:
    """The settings: a flag wins over its variable, and a variable over the default."""
    chosen = transport if transport is not None else environ.get("ECOSEMANTIC_TRANSPORT", "stdio")
    if chosen not in TRANSPORTS:
        raise Invalid(f"transport {chosen!r} is neither stdio nor http")
    from_env = environ.get("ECOSEMANTIC_VIEW", "on").lower() != "off"
    resolved_enabled = enabled if enabled is not None else from_env
    if chosen == "http" and not resolved_enabled:
        raise Invalid("transport http serves on the view's listener; it needs the view on")
    resolved_host = host if host is not None else environ.get("ECOSEMANTIC_VIEW_HOST", "127.0.0.1")
    named_port = port if port is not None else _named_port(environ)
    resolved_port = named_port if named_port is not None else derived_port(systems_dir)
    named_token = token if token is not None else _named_switch(environ, "ECOSEMANTIC_VIEW_TOKEN")
    if named_token is None and resolved_host not in LOOPBACK:
        raise Invalid(f"a bind to {resolved_host!r} reaches a network; pass --token or --no-token")
    named_open = opening if opening is not None else _named_switch(environ, "ECOSEMANTIC_VIEW_OPEN")
    return ViewSettings(
        enabled=resolved_enabled,
        host=resolved_host,
        port=resolved_port,
        url=url if url is not None else environ.get("ECOSEMANTIC_VIEW_URL"),
        transport=cast(Transport, chosen),
        token=bool(named_token),
        open=True if named_open is None else named_open,
    )


def _named_port(environ: Mapping[str, str]) -> int | None:
    named = environ.get("ECOSEMANTIC_VIEW_PORT")
    return None if named is None else int(named)


def _named_switch(environ: Mapping[str, str], name: str) -> bool | None:
    named = environ.get(name)
    if named is None:
        return None
    if named.lower() not in ("on", "off"):
        raise Invalid(f"{name} {named!r} is neither on nor off")
    return named.lower() == "on"


def bind(host: str, port: int) -> socket.socket:
    """A listening socket on the host and port, IPv4 or IPv6; port 0 takes a free one."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    return socket.create_server((host, port), family=family, backlog=128)
