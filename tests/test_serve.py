from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import ipaddress
import socket
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import uvicorn
from fastmcp import Client, FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from ecosemantic import serve
from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.events import EventBus
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import ROSTER, build_server
from ecosemantic.serve import (
    OPEN_WAIT_SECONDS,
    ViewSettings,
    announce,
    announced_host,
    bind,
    bind_or_yield,
    derived_port,
    health_route,
    listener_for,
    open_in_browser,
    open_unfollowed,
    opens,
    run,
    settings_from,
    token_for,
    workspace_digest,
    yield_route,
)
from ecosemantic.view.app import build_view
from ecosemantic.view.stream import RETRY_MILLISECONDS

NOWHERE = Path("/nonexistent-static")


@pytest.fixture(autouse=True)
def _no_inherited_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    """The announced host is read from os.environ, so the shell that ran the suite must not
    set it."""
    monkeypatch.delenv("SSH_CONNECTION", raising=False)


ENV = {
    "ECOSEMANTIC_VIEW": "off",
    "ECOSEMANTIC_VIEW_HOST": "0.0.0.0",
    "ECOSEMANTIC_VIEW_PORT": "8765",
    "ECOSEMANTIC_VIEW_URL": "http://lab.example:8765",
    "ECOSEMANTIC_VIEW_TOKEN": "on",
    "ECOSEMANTIC_TRANSPORT": "stdio",
}


def test_defaults_are_loopback_the_derived_port_and_stdio(tmp_path: Path) -> None:
    assert settings_from({}, tmp_path) == ViewSettings(port=derived_port(tmp_path))
    assert ViewSettings() == ViewSettings(
        enabled=True, host="127.0.0.1", port=0, url=None, transport="stdio", token=False
    )


def test_variables_are_read_and_flags_win(tmp_path: Path) -> None:
    from_env = settings_from(ENV, tmp_path)
    assert from_env == ViewSettings(
        enabled=False,
        host="0.0.0.0",
        port=8765,
        url="http://lab.example:8765",
        transport="stdio",
        token=True,
    )
    from_flags = settings_from(
        ENV, tmp_path, enabled=True, host="127.0.0.1", port=0, transport="http", token=False
    )
    assert from_flags == ViewSettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        url="http://lab.example:8765",
        transport="http",
        token=False,
    )


def test_a_transport_that_is_neither_is_invalid(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="transport"):
        settings_from({"ECOSEMANTIC_TRANSPORT": "grpc"}, tmp_path)


def test_http_transport_without_the_view_is_invalid(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="view"):
        settings_from({"ECOSEMANTIC_TRANSPORT": "http", "ECOSEMANTIC_VIEW": "off"}, tmp_path)


def test_a_token_variable_that_is_neither_on_nor_off_is_invalid(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="ECOSEMANTIC_VIEW_TOKEN"):
        settings_from({"ECOSEMANTIC_VIEW_TOKEN": "yes"}, tmp_path)


def test_settings_read_ecosemantic_view_open(tmp_path: Path) -> None:
    assert settings_from({}, tmp_path).open is True
    assert settings_from({"ECOSEMANTIC_VIEW_OPEN": "on"}, tmp_path).open is True
    assert settings_from({"ECOSEMANTIC_VIEW_OPEN": "off"}, tmp_path).open is False
    assert settings_from({"ECOSEMANTIC_VIEW_OPEN": "off"}, tmp_path, opening=True).open is True
    assert settings_from({}, tmp_path, opening=False).open is False
    with pytest.raises(Invalid, match="ECOSEMANTIC_VIEW_OPEN"):
        settings_from({"ECOSEMANTIC_VIEW_OPEN": "yes"}, tmp_path)


async def test_the_page_opens_when_no_page_follows_within_the_wait() -> None:
    bus = EventBus()
    opened: list[str] = []
    await open_unfollowed(bus, "http://127.0.0.1:1/?token=abc", opened.append, wait=0.01)
    assert opened == ["http://127.0.0.1:1/?token=abc"]


async def test_no_page_opens_when_one_follows() -> None:
    bus = EventBus()
    held = bus.subscribe_all()
    opened: list[str] = []
    await open_unfollowed(bus, "http://127.0.0.1:1/?token=abc", opened.append, wait=0.01)
    assert opened == []
    bus.unsubscribe_all(held)


def test_nothing_opens_over_http_with_no_open_with_the_page_off_or_without_a_display() -> None:
    displayed = {"DISPLAY": ":0"}
    assert opens(ViewSettings(), displayed, "linux") is True
    assert opens(ViewSettings(), {"WAYLAND_DISPLAY": "wayland-0"}, "linux") is True
    assert opens(ViewSettings(transport="http"), displayed, "linux") is False
    assert opens(ViewSettings(open=False), displayed, "linux") is False
    assert opens(ViewSettings(enabled=False), displayed, "linux") is False
    assert opens(ViewSettings(), {}, "linux") is False
    assert opens(ViewSettings(), {}, "win32") is True
    assert opens(ViewSettings(), {}, "darwin") is True


def test_the_browser_is_started_with_its_output_away_from_standard_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[tuple[list[str], dict[str, object]]] = []

    def recorder(command: list[str], **named: object) -> object:
        started.append((command, named))
        return object()

    monkeypatch.setattr(subprocess, "Popen", recorder)
    open_in_browser("http://127.0.0.1:1/?token=abc")
    assert started == [
        (
            ["xdg-open", "http://127.0.0.1:1/?token=abc"],
            {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "start_new_session": True,
            },
        )
    ]


def test_a_browser_that_fails_to_start_is_reported_and_the_server_serves_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(command: list[str], **named: object) -> object:
        raise OSError("xdg-open is missing")

    monkeypatch.setattr(subprocess, "Popen", failing)
    open_in_browser("http://127.0.0.1:1/")
    assert capsys.readouterr().err.strip() == "the page could not be opened: xdg-open is missing"


def test_the_wait_is_longer_than_the_page_s_retry_interval() -> None:
    assert OPEN_WAIT_SECONDS * 1000 > RETRY_MILLISECONDS


async def test_run_opens_the_address_when_a_page_can_be_shown(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    async def opener(
        _bus: EventBus, url: str, _showing: Callable[[str], None], _wait: float = OPEN_WAIT_SECONDS
    ) -> None:
        opened.append(url)

    async def sleeper(self: FastMCP, **kwargs: object) -> None:
        await asyncio.sleep(0.05)

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(FastMCP, "run_stdio_async", sleeper)
    monkeypatch.setattr(serve, "open_unfollowed", opener)
    await asyncio.wait_for(run(context, ViewSettings(), systems_dir), 20)
    assert len(opened) == 1 and opened[0].startswith("http://127.0.0.1:")


def test_bind_takes_a_free_port() -> None:
    sock = bind("127.0.0.1", 0)
    try:
        assert sock.getsockname()[1] > 0
    finally:
        sock.close()


@pytest.mark.skipif(not socket.has_ipv6, reason="no IPv6")
def test_bind_takes_a_free_port_on_ipv6_too() -> None:
    sock = bind("::1", 0)
    try:
        assert sock.getsockname()[1] > 0 and sock.family == socket.AF_INET6
    finally:
        sock.close()


def test_announce_uses_the_override_and_carries_the_token() -> None:
    assert announce(ViewSettings(), 8765, None, {}) == "http://127.0.0.1:8765"
    assert (
        announce(ViewSettings(host="0.0.0.0", url="http://lab.example:8765/"), 8765, "abc", {})
        == "http://lab.example:8765?token=abc"
    )
    derived = announce(ViewSettings(host="0.0.0.0"), 8765, "abc", {})
    assert derived.startswith("http://") and derived.endswith(":8765?token=abc")
    assert announce(ViewSettings(host="::1"), 8765, None, {}) == "http://[::1]:8765"


def test_the_instructions_carry_the_link(context: ServerContext) -> None:
    bound = dataclasses.replace(context, view_url="http://127.0.0.1:1?token=x")
    assert "http://127.0.0.1:1?token=x" in (build_server(bound).instructions or "")
    assert "first reply" in (build_server(bound).instructions or "")
    assert "http://" not in (build_server(context).instructions or "")


async def _wait_until_started(web: uvicorn.Server, timeout: float = 10) -> None:
    """The server accepted connections, or the wait failed loudly instead of hanging."""

    async def _started() -> None:
        while not web.started:
            await asyncio.sleep(0.05)

    await asyncio.wait_for(_started(), timeout)


async def test_http_transport_serves_the_tools_and_the_page(
    context: ServerContext, systems_dir: Path
) -> None:
    listener = listener_for(context, ViewSettings(transport="http"), systems_dir)
    web = uvicorn.Server(
        uvicorn.Config(listener.app, log_config=None, access_log=False, lifespan="on")
    )
    serving = asyncio.create_task(web.serve(sockets=[listener.socket]))
    try:
        await _wait_until_started(web)
        assert listener.token is None
        async with Client(f"{listener.url}/mcp") as client:
            names = [t.name for t in await client.list_tools()]
        assert names == ROSTER and len(names) == 48
        page = await asyncio.to_thread(
            lambda: urllib.request.urlopen(f"{listener.url}/systems/x", timeout=5).read()
        )
        assert b"not built" in page or b"<div id=" in page
    finally:
        web.should_exit = True
        await serving


async def test_run_with_the_view_off_serves_stdio_alone(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    async def recorder(self: FastMCP, **kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(FastMCP, "run_stdio_async", recorder)
    await run(context, ViewSettings(enabled=False), systems_dir)
    assert calls == [{"show_banner": False}]


async def test_run_with_the_view_off_hands_the_meter_provider_to_the_server(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opentelemetry.sdk.metrics import MeterProvider

    handed: list[object] = []

    def recording(bound: ServerContext, meter_provider: object = None) -> FastMCP:
        handed.append(meter_provider)
        return build_server(bound, meter_provider=meter_provider)

    async def recorder(self: FastMCP, **kwargs: object) -> None:
        pass

    monkeypatch.setattr(serve, "build_server", recording)
    monkeypatch.setattr(FastMCP, "run_stdio_async", recorder)
    provider = MeterProvider()
    await run(context, ViewSettings(enabled=False), systems_dir, meter_provider=provider)
    assert handed == [provider]


async def test_run_serves_stdio_beside_the_view_and_closes_the_listener_after(
    context: ServerContext,
    systems_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def sleeper(self: FastMCP, **kwargs: object) -> None:
        await asyncio.sleep(0.2)

    monkeypatch.setattr(FastMCP, "run_stdio_async", sleeper)
    await asyncio.wait_for(run(context, ViewSettings(), systems_dir), 20)
    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(lines) == 1 and lines[0].startswith("view: http://127.0.0.1:")
    port = int(lines[0].rsplit(":", 1)[1])
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


async def test_run_re_raises_a_failing_stdio(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(self: FastMCP, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(FastMCP, "run_stdio_async", failing)
    with pytest.raises(RuntimeError, match="boom"):
        await asyncio.wait_for(run(context, ViewSettings(), systems_dir), 20)


async def test_run_with_the_http_transport_serves_only_the_listener(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_calls: list[list[socket.socket]] = []

    async def serve_recorder(
        self: uvicorn.Server, sockets: list[socket.socket] | None = None
    ) -> None:
        serve_calls.append(sockets or [])
        for sock in sockets or []:
            sock.close()

    stdio_calls: list[dict[str, object]] = []

    async def stdio_recorder(self: FastMCP, **kwargs: object) -> None:
        stdio_calls.append(kwargs)

    monkeypatch.setattr(uvicorn.Server, "serve", serve_recorder)
    monkeypatch.setattr(FastMCP, "run_stdio_async", stdio_recorder)
    await run(context, ViewSettings(transport="http"), systems_dir)
    assert len(serve_calls) == 1 and len(serve_calls[0]) == 1
    assert stdio_calls == []


def test_the_port_derives_from_the_directory_and_stays_in_band(tmp_path: Path) -> None:
    one = tmp_path / "alpha"
    other = tmp_path / "beta"
    one.mkdir()
    other.mkdir()
    assert derived_port(one) == derived_port(one)
    assert derived_port(one) != derived_port(other)
    assert 10000 <= derived_port(one) <= 32767
    assert 10000 <= derived_port(other) <= 32767


def test_the_digest_names_the_workspace_without_naming_the_path(tmp_path: Path) -> None:
    systems = tmp_path / "systems"
    systems.mkdir()
    digest = workspace_digest(systems)
    assert digest == workspace_digest(systems)
    assert str(systems) not in digest
    assert len(digest) == 16


def test_the_port_is_derived_unless_a_flag_or_a_variable_names_one(tmp_path: Path) -> None:
    resolved = settings_from({}, tmp_path)
    assert resolved.port == derived_port(tmp_path)
    assert settings_from({"ECOSEMANTIC_VIEW_PORT": "8765"}, tmp_path).port == 8765
    assert settings_from({}, tmp_path, port=8765).port == 8765
    assert settings_from({}, tmp_path, port=0).port == 0


def test_the_link_carries_no_token_on_loopback(tmp_path: Path) -> None:
    assert settings_from({}, tmp_path).token is False
    assert settings_from({}, tmp_path, token=True).token is True


def test_a_bind_beyond_loopback_needs_the_token_said_either_way(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="token"):
        settings_from({}, tmp_path, host="0.0.0.0")
    assert settings_from({}, tmp_path, host="0.0.0.0", token=False).token is False
    assert settings_from({}, tmp_path, host="0.0.0.0", token=True).token is True


def test_the_token_is_the_workspace_s_and_survives_a_restart(tmp_path: Path) -> None:
    assert token_for(tmp_path, False) is None
    minted = token_for(tmp_path, True)
    assert minted is not None
    assert token_for(tmp_path, True) == minted
    stored = tmp_path / "token"
    assert stored.read_text().strip() == minted
    assert stored.stat().st_mode & 0o777 == 0o600


def test_deleting_the_file_rotates_the_token(tmp_path: Path) -> None:
    first = token_for(tmp_path, True)
    (tmp_path / "token").unlink()
    assert token_for(tmp_path, True) != first


SSH = {"SSH_CONNECTION": "192.0.2.130 43600 192.0.2.86 22"}


def test_ssh_names_the_address_the_client_reached() -> None:
    settings = ViewSettings(host="0.0.0.0")
    assert announced_host(settings, SSH) == "192.0.2.86"
    assert announced_host(ViewSettings(host="127.0.0.1"), SSH) == "192.0.2.86"


def test_without_ssh_an_unspecified_bind_takes_an_address_of_this_host() -> None:
    found = announced_host(ViewSettings(host="0.0.0.0"), {})
    assert found != socket.gethostname()
    assert not ipaddress.ip_address(found).is_loopback
    assert announced_host(ViewSettings(host="10.0.0.4"), {}) == "10.0.0.4"


def test_a_host_with_only_loopback_is_unavailable_naming_the_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(serve, "routed_address", lambda: "127.0.0.1")
    with pytest.raises(Unavailable, match="--view-url"):
        announced_host(ViewSettings(host="0.0.0.0"), {})

    def unrouted() -> str:
        raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(serve, "routed_address", unrouted)
    with pytest.raises(Unavailable, match="--view-url"):
        announced_host(ViewSettings(host="0.0.0.0"), {})


def test_an_unparseable_ssh_connection_is_invalid() -> None:
    with pytest.raises(Invalid, match="SSH_CONNECTION"):
        announced_host(ViewSettings(), {"SSH_CONNECTION": "192.0.2.130 43600"})


def test_the_override_still_wins_over_ssh() -> None:
    settings = ViewSettings(host="0.0.0.0", url="http://example.test:9000")
    assert announce(settings, 39029, None, SSH) == "http://example.test:9000"


@contextlib.contextmanager
def serving_health(digest: str, yields: bool = False) -> Iterator[int]:
    """A holder of a port: it answers /health, and /yield stops it when it is meant to."""
    probe = bind("127.0.0.1", 0)
    port = probe.getsockname()[1]
    probe.close()

    async def health(request: Request) -> Response:
        return JSONResponse({"service": "ecosemantic-view", "workspace": digest, "yields": yields})

    async def yielded(request: Request) -> Response:
        if yields:
            server.should_exit = True
        return JSONResponse({"yielded": yields})

    app = Starlette(routes=[Route("/health", health), Route("/yield", yielded, methods=["POST"])])
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_a_port_held_by_another_application_is_invalid(tmp_path: Path) -> None:
    held = bind("127.0.0.1", 0)
    port = held.getsockname()[1]
    settings = ViewSettings(host="127.0.0.1", port=port)
    with pytest.raises(Invalid, match="another application"):
        bind_or_yield(settings, tmp_path)
    held.close()


def test_a_port_held_for_another_workspace_is_invalid(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    with serving_health(workspace_digest(other)) as port:
        settings = ViewSettings(host="127.0.0.1", port=port)
        with pytest.raises(Invalid, match="another workspace"):
            bind_or_yield(settings, tmp_path)


def test_a_holder_of_this_workspace_yields_the_port(tmp_path: Path) -> None:
    with serving_health(workspace_digest(tmp_path), yields=True) as port:
        settings = ViewSettings(host="127.0.0.1", port=port)
        taken = bind_or_yield(settings, tmp_path)
        assert taken.getsockname()[1] == port
        taken.close()


def test_a_holder_of_this_workspace_that_does_not_yield_is_refused_at_once(
    tmp_path: Path,
) -> None:
    with serving_health(workspace_digest(tmp_path), yields=False) as port:
        settings = ViewSettings(host="127.0.0.1", port=port)
        started = time.monotonic()
        with pytest.raises(Invalid, match=f"port {port} is held by a server of this workspace"):
            bind_or_yield(settings, tmp_path)
        # refused without waiting out the yield
        assert time.monotonic() - started < 1


def test_an_http_listener_says_it_does_not_yield_and_serves_no_yield_route(
    context: ServerContext, systems_dir: Path
) -> None:
    listener = listener_for(context, ViewSettings(transport="http"), systems_dir)
    listener.socket.close()
    with TestClient(listener.app) as client:
        assert client.get("/health").json()["yields"] is False
        # only the page's catch-all answers the path, and it takes GET alone
        assert client.post("/yield", json={"nonce": "any"}).status_code == 405


async def test_run_over_http_registers_no_yield(
    context: ServerContext, systems_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[object] = []
    built = listener_for

    def recording(*args: object, **kwargs: object) -> object:
        given.append(kwargs.get("on_yield"))
        return built(*args, **kwargs)

    async def serve_recorder(
        self: uvicorn.Server, sockets: list[socket.socket] | None = None
    ) -> None:
        for sock in sockets or []:
            sock.close()

    monkeypatch.setattr(serve, "listener_for", recording)
    monkeypatch.setattr(uvicorn.Server, "serve", serve_recorder)
    await run(context, ViewSettings(transport="http"), systems_dir)
    assert given == [None]


def test_health_names_the_workspace_and_needs_no_token(context: ServerContext) -> None:
    app = build_view(
        context,
        build_server(context),
        token="secret",
        static=NOWHERE,
        routes=[health_route("abcd1234abcd1234", yields=True)],
    )
    with TestClient(app) as client:
        answered = client.get("/health")
        assert answered.status_code == 200
        assert answered.json() == {
            "service": "ecosemantic-view",
            "workspace": "abcd1234abcd1234",
            "yields": True,
        }
        # the gate still covers the API
        refused = client.get("/api/product-systems")
        assert refused.status_code == 401
        assert refused.json() == {
            "error": "unauthorised",
            "message": "the token in the link is required",
            "details": {},
        }


def test_yield_needs_the_nonce_from_the_directory(context: ServerContext, tmp_path: Path) -> None:
    released: list[bool] = []
    app = build_view(
        context,
        build_server(context),
        static=NOWHERE,
        routes=[yield_route(tmp_path, lambda: released.append(True))],
    )
    with TestClient(app) as client:
        refused = client.post("/yield", json={"nonce": "guessed"})
        assert refused.status_code == 401
        assert refused.json() == {
            "error": "unauthorised",
            "message": "the nonce in the directory is required",
            "details": {},
        }
        assert released == []
        (tmp_path / "yield-nonce").write_text("the-real-nonce")
        assert client.post("/yield", json={"nonce": "guessed"}).status_code == 401
        assert released == []
        answered = client.post("/yield", json={"nonce": "the-real-nonce"})
        assert answered.status_code == 200
        assert released == [True]


def test_the_token_gates_the_mcp_endpoint_over_http(
    context: ServerContext, systems_dir: Path
) -> None:
    listener = listener_for(context, ViewSettings(transport="http", token=True), systems_dir)
    listener.socket.close()
    assert listener.token is not None
    with TestClient(listener.app) as client:
        refused = client.post("/mcp", json={})
        assert refused.status_code == 401
        assert refused.json()["error"] == "unauthorised"
        # the token lets the call through to the MCP endpoint
        passed = client.post(f"/mcp?token={listener.token}", json={})
        assert passed.status_code != 401


def tool_calls(reader: object) -> list[tuple[dict[str, str], int]]:
    data = reader.get_metrics_data()
    return [
        (dict(point.attributes), point.value)
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "ecosemantic.tool.calls"
        for point in metric.data.data_points
    ]


async def test_a_listener_counts_on_the_provider_it_is_handed(
    context: ServerContext, systems_dir: Path
) -> None:
    from mcp.types import Implementation
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    listener = listener_for(
        context, ViewSettings(transport="http"), systems_dir, meter_provider=provider
    )
    listener.socket.close()
    async with Client(listener.server, client_info=Implementation(name="agent", version="1")) as c:
        await c.call_tool("list_databases", {})
    assert tool_calls(reader) == [({"tool": "list_databases"}, 1)]


async def test_a_server_with_its_collector_out_of_service_answers_its_tools(
    context: ServerContext, systems_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from mcp.types import Implementation

    from ecosemantic.telemetry import begin, end

    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY", "on")
    environ = {
        "ECOSEMANTIC_TELEMETRY": "on",
        "ECOSEMANTIC_TELEMETRY_ENDPOINT": "http://127.0.0.1:9/v1/metrics",
    }
    provider = begin(environ, tmp_path, "stdio", io.StringIO())
    assert provider is not None
    listener = listener_for(
        context, ViewSettings(transport="http"), systems_dir, meter_provider=provider
    )
    listener.socket.close()
    async with Client(listener.server, client_info=Implementation(name="agent", version="1")) as c:
        for _ in range(3):
            answered = await c.call_tool("list_databases", {})
            assert answered.structured_content is not None
    stopping = time.monotonic()
    end(provider)
    assert time.monotonic() - stopping < 7
