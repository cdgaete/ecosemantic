"""The process that serves: binding, announcing and handing over the listener, and running the MCP
server over stdio beside the view, or over HTTP mounted on the view's listener."""

from __future__ import annotations

import asyncio
import dataclasses
import errno
import ipaddress
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastmcp import FastMCP
from opentelemetry.metrics import MeterProvider
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route
from starlette.types import ASGIApp

from ecosemantic.bridge.relay import Relay
from ecosemantic.bridge.start import BridgeStart, engine_version
from ecosemantic.errors import Invalid, Unauthorised, Unavailable
from ecosemantic.events import EventBus
from ecosemantic.mcp.accounts import ACCOUNTS_PATH
from ecosemantic.mcp.context import AccountStart, ServerContext, Start
from ecosemantic.mcp.server import build_server
from ecosemantic.settings import (
    LOOPBACK,
    TRANSPORTS,
    Transport,
    ViewSettings,
    bind,
    browser_reachable,
    derived_port,
    settings_from,
    workspace_digest,
)
from ecosemantic.settings.handover import (
    SERVICE,
    STOP_NONCE_FILE,
    UNSPECIFIED,
    YIELD_NONCE_FILE,
    BridgeHealth,
    Health,
    ask_to_stop,
    ask_to_yield,
    nonce_path,
    proven,
    reachable,
    read_health,
)
from ecosemantic.view.api import BRIDGE_EXTENSION, GATE_PARAMETER
from ecosemantic.view.app import build_view
from ecosemantic.view.handling import answering

SHUTDOWN_SECONDS = 5
OPEN_WAIT_SECONDS = 4.0
YIELD_SECONDS = 5
MCP_PATH = "/mcp"

__all__ = [
    "MCP_PATH",
    "OPEN_WAIT_SECONDS",
    "SHUTDOWN_SECONDS",
    "STOP_NONCE_FILE",
    "TRANSPORTS",
    "UNSPECIFIED",
    "YIELD_NONCE_FILE",
    "YIELD_SECONDS",
    "Listener",
    "Transport",
    "ViewSettings",
    "account_start",
    "announce",
    "announced_host",
    "ask_to_stop",
    "bind",
    "bind_or_yield",
    "browser_reachable",
    "derived_port",
    "health_route",
    "listener_for",
    "nonce_path",
    "open_in_browser",
    "open_unfollowed",
    "opens",
    "routed_address",
    "run",
    "settings_from",
    "stop_route",
    "token_for",
    "workspace_digest",
    "yield_route",
]


def bind_or_yield(settings: ViewSettings, systems_dir: Path) -> socket.socket:
    """The listening socket, taking the derived port from a holder of this same workspace."""
    try:
        return bind(settings.host, settings.port)
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
    holding = read_health(settings.host, settings.port, hint="pass --view-port")
    if holding is None:
        raise Invalid(f"port {settings.port} is held by another application; pass --view-port")
    if holding.workspace != workspace_digest(systems_dir):
        raise Invalid(f"port {settings.port} is held for another workspace; pass --view-port")
    if not holding.yields:
        raise Invalid(
            f"port {settings.port} is held by a server of this workspace that does not yield it, "
            "as one serving HTTP does; stop that server or pass --view-port"
        )
    ask_to_yield(settings.host, settings.port, systems_dir)
    deadline = time.monotonic() + YIELD_SECONDS
    while time.monotonic() < deadline:
        try:
            return bind(settings.host, settings.port)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            time.sleep(0.1)
    raise Invalid(f"the holder of port {settings.port} did not yield it")


def health_route(
    workspace: str,
    yields: bool,
    bridge: Callable[[], BridgeHealth] | None = None,
    accounts: str | None = None,
) -> Route:
    """The route a starting server and a tray read: which directory the holder serves, whether it
    yields the port, for a bridged server the tunnel's state and the addresses its owner needs, and
    the accounts screen's address where the engine serves one."""

    async def health(request: Request) -> Response:
        answered = Health(
            service=SERVICE,
            workspace=workspace,
            yields=yields,
            bridge=BridgeHealth(state="off") if bridge is None else bridge(),
            accounts=accounts,
        )
        return JSONResponse(answered.model_dump(mode="json"))

    return Route("/health", health)


async def _nonce_proven(request: Request, systems_dir: Path, nonce_file: str) -> None:
    """Refuse a request that does not carry the nonce written in the directory, which proves the
    caller can write there."""
    sent = (await request.json()).get("nonce", "")
    if not proven(sent, systems_dir, nonce_file):
        raise Unauthorised("the nonce in the directory is required")


def yield_route(systems_dir: Path, on_yield: Callable[[], None]) -> Route:
    """The route a starting server calls to take the port, proving it holds the directory."""

    @answering
    async def yielded(request: Request) -> Response:
        await _nonce_proven(request, systems_dir, YIELD_NONCE_FILE)
        on_yield()
        return JSONResponse({"yielded": True})

    return Route("/yield", yielded, methods=["POST"])


def stop_route(systems_dir: Path, on_stop: Callable[[], None]) -> Route:
    """The route a process that writes the systems directory calls to end an HTTP server."""

    @answering
    async def stopped(request: Request) -> Response:
        await _nonce_proven(request, systems_dir, STOP_NONCE_FILE)
        on_stop()
        return JSONResponse({"stopped": True})

    return Route("/stop", stopped, methods=["POST"])


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
    settings: ViewSettings,
    port: int,
    token: str | None,
    environ: Mapping[str, str],
    bridged: str | None = None,
) -> str:
    """The URL the person is given: the address the bridge was reached by, which carries no token,
    or the override, or the reached address and port, with the token."""
    if bridged is not None:
        return bridged.rstrip("/")
    if settings.url is not None:
        base = settings.url.rstrip("/")
    else:
        base = f"http://{_url_host(announced_host(settings, environ))}:{port}"
    return f"{base}?{GATE_PARAMETER}={token}" if token else base


@dataclass(frozen=True)
class Listener:
    """A bound socket, what it is announced as, and the applications served on it."""

    socket: socket.socket
    url: str
    token: str | None
    server: FastMCP
    app: ASGIApp


def account_start(
    settings: ViewSettings,
    port: int,
    token: str | None,
    bridged_url: str | None,
    environ: Mapping[str, str],
    platform: str,
) -> AccountStart:
    """How this engine was started, the accounts screen its listener serves at the port bound, and
    the bridge page's address where it is bridged. An engine carrying a token names no screen,
    since the page's calls need the token no advice carries, and neither does one bound to an
    address that is neither loopback nor every address, which a browser on its computer reaches
    from no loopback peer."""
    start: Start
    if settings.tray:
        start = "tray"
    elif browser_reachable(environ, platform):
        start = "terminal"
    else:
        start = "headless"
    looped = settings.host in LOOPBACK or settings.host in UNSPECIFIED
    screen = (
        f"http://{_url_host(reachable(settings.host))}:{port}{ACCOUNTS_PATH}"
        if token is None and looped
        else None
    )
    return AccountStart(start=start, screen=screen, page=bridged_url)


def _url_host(host: str) -> str:
    """A host as a URL names it: an IPv6 address in brackets."""
    return f"[{host}]" if ":" in host else host


def listener_for(
    context: ServerContext,
    settings: ViewSettings,
    systems_dir: Path,
    on_yield: Callable[[], None] | None = None,
    meter_provider: MeterProvider | None = None,
    bridged_url: str | None = None,
    bridged: Callable[[str, str], bool] | None = None,
    bridge: Callable[[], BridgeHealth] | None = None,
    on_stop: Callable[[], None] | None = None,
) -> Listener:
    """Bind, mint the token, announce, and build the server, counting on the meter provider
    handed, and the view on that URL, with the handover routes and, over HTTP, the MCP endpoint
    mounted beside the view's routes. A bridge names the announced address, reports its tunnel at
    the page's health and verifies the proof a bridged request carries; a stop callback mounts the
    route that ends the server."""
    sock = bind_or_yield(settings, systems_dir)
    token = token_for(systems_dir, settings.token)
    url = announce(settings, sock.getsockname()[1], token, os.environ, bridged=bridged_url)
    start = account_start(
        settings, sock.getsockname()[1], token, bridged_url, os.environ, sys.platform
    )
    bound = dataclasses.replace(context, view_url=url, accounts=start)
    server = build_server(bound, meter_provider=meter_provider)
    routes: list[BaseRoute] = [
        health_route(
            workspace_digest(systems_dir),
            yields=on_yield is not None,
            bridge=bridge,
            accounts=start.screen,
        )
    ]
    if on_yield is not None:
        routes.append(yield_route(systems_dir, on_yield))
    if on_stop is not None:
        routes.append(stop_route(systems_dir, on_stop))
    if settings.transport != "http":
        app = build_view(bound, server, token=token, routes=routes, bridged=bridged)
        return Listener(socket=sock, url=url, token=token, server=server, app=app)
    mounted = server.http_app(path=MCP_PATH)
    app = build_view(
        bound,
        server,
        token=token,
        routes=[*routes, Route(MCP_PATH, mounted)],
        gated=(MCP_PATH,),
        inner=mounted.lifespan,
        bridged=bridged,
    )
    return Listener(socket=sock, url=url, token=token, server=server, app=app)


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


def _reported(line: str) -> None:
    """One line the tunnel reports, written as it comes."""
    print(line, file=sys.stderr, flush=True)


async def _bridged(listener: Listener, web: uvicorn.Server, relay: Relay) -> None:
    """Serve the listener and its tunnel together: a listener that stops stops the relay, and a
    relay that stops — as a sign-out stops it — leaves the engine serving locally."""
    relaying = asyncio.create_task(relay.run())
    serving = asyncio.create_task(web.serve(sockets=[listener.socket]))
    try:
        done, _ = await asyncio.wait({relaying, serving}, return_when=asyncio.FIRST_COMPLETED)
        if relaying in done:
            relaying.result()
            await serving
        else:
            serving.result()
    finally:
        web.should_exit = True
        await _stopped(relaying)
        await asyncio.wait({serving}, timeout=SHUTDOWN_SECONDS * 2)


async def run(
    context: ServerContext,
    settings: ViewSettings,
    systems_dir: Path,
    meter_provider: MeterProvider | None = None,
    bridge: BridgeStart | None = None,
) -> None:
    """Serve stdio alone, stdio beside the view, or the view with the MCP endpoint mounted,
    counting tool calls on the meter provider handed. A bridge announces the page address it
    answers at, admits the requests its proofs name, and serves its tunnel beside the listener."""
    if not settings.enabled:
        await build_server(context, meter_provider=meter_provider).run_stdio_async(
            show_banner=False
        )
        return
    yielded = asyncio.Event()
    on_yield = None if settings.transport == "http" else yielded.set
    web: uvicorn.Server
    relay: Relay

    def on_stop() -> None:
        web.should_exit = True

    bridge_report: Callable[[], BridgeHealth] | None = None
    if bridge is not None:
        start = bridge

        def bridge_report() -> BridgeHealth:
            return BridgeHealth(
                state=relay.state(),
                handle=relay.handle(),
                page=start.page_url,
                connector=start.config.connector_url,
            )

    listener = listener_for(
        context,
        settings,
        systems_dir,
        on_yield=on_yield,
        meter_provider=meter_provider,
        bridged_url=None if bridge is None else bridge.page_url,
        bridged=None if bridge is None else bridge.check,
        bridge=bridge_report,
        on_stop=on_stop if settings.transport == "http" else None,
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
    if bridge is not None:
        print(f"connector: {bridge.config.connector_url}", file=sys.stderr, flush=True)
        relay = Relay(
            app=listener.app,
            session=bridge.session,
            config=bridge.config,
            engine=bridge.engine,
            account=bridge.account,
            handle=bridge.handle,
            version=engine_version(),
            check=bridge.check,
            extension=BRIDGE_EXTENSION,
            report=_reported,
        )
        await _bridged(listener, web, relay)
        return
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
