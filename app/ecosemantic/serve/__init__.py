"""The process that serves: binding, announcing and handing over the listener, and running the MCP
server over stdio beside the view, or over HTTP mounted on the view's listener."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import errno
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

import uvicorn
from fastmcp import FastMCP
from opentelemetry.metrics import MeterProvider
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route
from starlette.types import ASGIApp

from ecosemantic.errors import Invalid, Unauthorised, Unavailable
from ecosemantic.events import EventBus
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.view.api import GATE_PARAMETER
from ecosemantic.view.app import build_view
from ecosemantic.view.handling import answering

LOOPBACK = ("127.0.0.1", "localhost", "::1")
UNSPECIFIED = ("0.0.0.0", "::")
Transport = Literal["stdio", "http"]
TRANSPORTS: tuple[str, ...] = get_args(Transport)
SHUTDOWN_SECONDS = 5
OPEN_WAIT_SECONDS = 4.0
PORT_FLOOR = 10000
PORT_CEILING = 32767
YIELD_SECONDS = 5
SERVICE = "ecosemantic-view"
YIELD_NONCE_FILE = "yield-nonce"
MCP_PATH = "/mcp"


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


def _reachable(host: str) -> str:
    """The address that reaches a listener on this machine: loopback when it binds every one."""
    return host if host not in UNSPECIFIED else "127.0.0.1"


def _holder(host: str, port: int) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://{_reachable(host)}:{port}/health", timeout=2
        ) as answered:
            body = json.loads(answered.read())
    except Exception:
        return None
    return body if body.get("service") == SERVICE else None


def bind_or_yield(settings: ViewSettings, systems_dir: Path) -> socket.socket:
    """The listening socket, taking the derived port from a holder of this same workspace."""
    try:
        return bind(settings.host, settings.port)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
    holding = _holder(settings.host, settings.port)
    if holding is None:
        raise Invalid(f"port {settings.port} is held by another application; pass --view-port")
    if holding.get("workspace") != workspace_digest(systems_dir):
        raise Invalid(f"port {settings.port} is held for another workspace; pass --view-port")
    if holding.get("yields") is not True:
        raise Invalid(
            f"port {settings.port} is held by a server of this workspace that does not yield it, "
            "as one serving HTTP does; stop that server or pass --view-port"
        )
    _ask_to_yield(settings, systems_dir)
    deadline = time.monotonic() + YIELD_SECONDS
    while time.monotonic() < deadline:
        try:
            return bind(settings.host, settings.port)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            time.sleep(0.1)
    raise Invalid(f"the holder of port {settings.port} did not yield it")


def health_route(workspace: str, yields: bool) -> Route:
    """The one route a starting server reads to learn which directory the holder serves and
    whether it yields the port."""

    async def health(request: Request) -> Response:
        return JSONResponse({"service": SERVICE, "workspace": workspace, "yields": yields})

    return Route("/health", health)


def yield_route(systems_dir: Path, on_yield: Callable[[], None]) -> Route:
    """The route a starting server calls to take the port, proving it holds the directory."""

    @answering
    async def yielded(request: Request) -> Response:
        sent = (await request.json()).get("nonce", "")
        try:
            held = (systems_dir / YIELD_NONCE_FILE).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            held = ""
        if not held or not hmac.compare_digest(sent, held):
            raise Unauthorised("the nonce in the directory is required")
        on_yield()
        return JSONResponse({"yielded": True})

    return Route("/yield", yielded, methods=["POST"])


def _ask_to_yield(settings: ViewSettings, systems_dir: Path) -> None:
    nonce = secrets.token_urlsafe(24)
    (systems_dir / YIELD_NONCE_FILE).write_text(nonce, encoding="utf-8")
    asked = urllib.request.Request(
        f"http://{_reachable(settings.host)}:{settings.port}/yield",
        data=json.dumps({"nonce": nonce}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with contextlib.suppress(Exception):
        urllib.request.urlopen(asked, timeout=2).close()
    (systems_dir / YIELD_NONCE_FILE).unlink(missing_ok=True)


def token_for(systems_dir: Path, wanted: bool) -> str | None:
    """The workspace's token when the link carries one, minted on first use and kept at 0600."""
    if not wanted:
        return None
    stored = systems_dir / "token"
    try:
        handle = os.open(stored, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return stored.read_text(encoding="utf-8").strip()
    minted = secrets.token_urlsafe(24)
    with os.fdopen(handle, "w", encoding="utf-8") as opened:
        opened.write(minted)
    return minted


def routed_address() -> str:
    """The address this host's default route leaves by; connecting a UDP socket sends nothing,
    and OSError when the host has no route."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return str(probe.getsockname()[0])


def announced_host(settings: ViewSettings, environ: Mapping[str, str]) -> str:
    """The address the person reaches the server by, which a bind does not always name."""
    reached = environ.get("SSH_CONNECTION")
    if reached is not None:
        fields = reached.split()
        if len(fields) != 4:
            raise Invalid(f"SSH_CONNECTION {reached!r} is not four fields")
        return fields[2]
    if settings.host not in UNSPECIFIED:
        return settings.host
    try:
        found = routed_address()
    except OSError as error:
        raise Unavailable(
            f"this host has no route to announce the view by ({error}); name it with --view-url",
            hint="start the server with --view-url",
        ) from error
    if ipaddress.ip_address(found).is_loopback:
        raise Unavailable(
            f"this host's only address is loopback ({found}); name the view with --view-url",
            hint="start the server with --view-url",
        )
    return found


def announce(
    settings: ViewSettings, port: int, token: str | None, environ: Mapping[str, str]
) -> str:
    """The URL the person is given: the override, or the reached address and port, with the
    token."""
    if settings.url is not None:
        base = settings.url.rstrip("/")
    else:
        host = announced_host(settings, environ)
        if ":" in host:
            host = f"[{host}]"
        base = f"http://{host}:{port}"
    return f"{base}?{GATE_PARAMETER}={token}" if token else base


@dataclass(frozen=True)
class Listener:
    """A bound socket, what it is announced as, and the applications served on it."""

    socket: socket.socket
    url: str
    token: str | None
    server: FastMCP
    app: ASGIApp


def listener_for(
    context: ServerContext,
    settings: ViewSettings,
    systems_dir: Path,
    on_yield: Callable[[], None] | None = None,
    meter_provider: MeterProvider | None = None,
) -> Listener:
    """Bind, mint the token, announce, and build the server, counting on the meter provider
    handed, and the view on that URL, with the handover routes and, over HTTP, the MCP endpoint
    mounted beside the view's routes."""
    sock = bind_or_yield(settings, systems_dir)
    token = token_for(systems_dir, settings.token)
    url = announce(settings, sock.getsockname()[1], token, os.environ)
    bound = dataclasses.replace(context, view_url=url)
    server = build_server(bound, meter_provider=meter_provider)
    routes: list[BaseRoute] = [
        health_route(workspace_digest(systems_dir), yields=on_yield is not None)
    ]
    if on_yield is not None:
        routes.append(yield_route(systems_dir, on_yield))
    if settings.transport != "http":
        app = build_view(bound, server, token=token, routes=routes)
        return Listener(socket=sock, url=url, token=token, server=server, app=app)
    mounted = server.http_app(path=MCP_PATH)
    app = build_view(
        bound,
        server,
        token=token,
        routes=[*routes, Route(MCP_PATH, mounted)],
        gated=(MCP_PATH,),
        inner=mounted.lifespan,
    )
    return Listener(socket=sock, url=url, token=token, server=server, app=app)


def browser_reachable(environ: Mapping[str, str], platform: str) -> bool:
    """Whether this machine can show a browser: Windows and macOS always, elsewhere only with a
    display."""
    if platform in ("win32", "darwin"):
        return True
    return "DISPLAY" in environ or "WAYLAND_DISPLAY" in environ


def open_in_browser(url: str) -> None:
    """Show the address in the person's default browser, its output kept off the protocol's; a
    browser that will not start is reported and the server serves on."""
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            subprocess.Popen(
                ["open" if sys.platform == "darwin" else "xdg-open", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError as error:
        print(f"the page could not be opened: {error}", file=sys.stderr, flush=True)


async def open_unfollowed(
    bus: EventBus, url: str, opener: Callable[[str], None], wait: float = OPEN_WAIT_SECONDS
) -> None:
    """Open the address once `wait` passes with no page following the process-wide stream."""
    await asyncio.sleep(wait)
    if bus.followers() == 0:
        opener(url)


def opens(settings: ViewSettings, environ: Mapping[str, str], platform: str) -> bool:
    """Whether this start opens the page: a stdio server with the page on, its opening not
    turned off, on a machine that can show a browser."""
    if not settings.enabled or not settings.open or settings.transport != "stdio":
        return False
    return browser_reachable(environ, platform)


async def _stopped(task: asyncio.Task[None] | None) -> None:
    """Cancel a task the server no longer needs, and wait for it."""
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def run(
    context: ServerContext,
    settings: ViewSettings,
    systems_dir: Path,
    meter_provider: MeterProvider | None = None,
) -> None:
    """Serve stdio alone, stdio beside the view, or the view with the MCP endpoint mounted,
    counting tool calls on the meter provider handed."""
    if not settings.enabled:
        await build_server(context, meter_provider=meter_provider).run_stdio_async(
            show_banner=False
        )
        return
    yielded = asyncio.Event()
    on_yield = None if settings.transport == "http" else yielded.set
    listener = listener_for(
        context, settings, systems_dir, on_yield=on_yield, meter_provider=meter_provider
    )
    print(f"view: {listener.url}", file=sys.stderr, flush=True)
    web = uvicorn.Server(
        uvicorn.Config(
            listener.app,
            log_config=None,
            access_log=False,
            lifespan="on",
            timeout_graceful_shutdown=SHUTDOWN_SECONDS,
        )
    )
    if settings.transport == "http":
        await web.serve(sockets=[listener.socket])
        return
    opening = (
        asyncio.create_task(open_unfollowed(context.events, listener.url, open_in_browser))
        if opens(settings, os.environ, sys.platform)
        else None
    )
    stdio = asyncio.create_task(listener.server.run_stdio_async(show_banner=False))
    serving = asyncio.create_task(web.serve(sockets=[listener.socket]))
    giving = asyncio.create_task(yielded.wait())
    done, pending = await asyncio.wait(
        {stdio, serving, giving}, return_when=asyncio.FIRST_COMPLETED
    )
    if giving in done:
        web.should_exit = True
        await _stopped(opening)
        await asyncio.wait({serving}, timeout=SHUTDOWN_SECONDS * 2)
        await stdio
        return
    giving.cancel()
    pending.discard(giving)
    web.should_exit = True
    await _stopped(opening)
    if serving in pending:
        await asyncio.wait({serving}, timeout=SHUTDOWN_SECONDS * 2)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()
