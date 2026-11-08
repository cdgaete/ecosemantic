"""The relay: this engine's application answering the requests one tunnel carries, and the proof
a bridged request is admitted on."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
import socket
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from websockets.asyncio.client import connect as tunnel_connect
from websockets.exceptions import ConnectionClosedError
from websockets.protocol import Close

from ecosemantic.bridge.credentials import Credential
from ecosemantic.bridge.proofs import ProofCheck
from ecosemantic.bridge.relay import Relay
from ecosemantic.bridge.session import EngineTokenSession, TunnelSession
from ecosemantic.bridge.signin import OpenIdProvider, SignedOut, provider
from ecosemantic.errors import Unauthorised, Unavailable
from ecosemantic.events import Event
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.relay.frames import CHUNK_BYTES
from ecosemantic.relay.messages import PROTOCOL, Welcome
from ecosemantic.relay.proof import public_jwk
from ecosemantic.serve import Listener, ViewSettings, listener_for
from ecosemantic.view.api import BRIDGE_EXTENSION
from tests.bridge.fake_bridge import (
    ACCOUNT,
    BEARER,
    HANDLE,
    ISSUER,
    FakeBridge,
    configuration,
    serving,
)
from tests.bridge.fake_logto import ISSUER as LOGTO_ISSUER
from tests.bridge.fake_logto import TOKEN_PATH, FakeLogto

ENGINE = uuid.uuid4()
OTHER_ENGINE = uuid.uuid4()
VERSION = "0.1.12"
SIGNED_OUT = "bridge: signed out; run `ecosemantic bridge sign-in`"
OTHER_ENGINE_LINE = "bridge: the bridge answers for another engine; this server's bridge stops"
OTHER_ACCOUNT_LINE = "bridge: the bridge answers for another account; this server's bridge stops"
SIGNED_IN_AGAIN_LINE = (
    "bridge: this systems directory was signed in again; this server's bridge stops"
)
ENGINE_REFUSED_LINE = (
    "bridge: the bridge refused this engine's engine token; the bridge's account page issues a "
    "new one"
)
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "the-bridge", "version": "1"},
    },
}
MCP_HEADERS = [
    ("content-type", "application/json"),
    ("accept", "application/json, text/event-stream"),
]


def utcnow() -> datetime:
    """This machine's clock."""
    return datetime.now(UTC)


def a_credential() -> Credential:
    """The credential this systems directory was signed in with."""
    return Credential(
        bridge_url=ISSUER,
        client_id="the-engine-browser",
        engine=ENGINE,
        account=ACCOUNT,
        handle=HANDLE,
        page_url=f"https://{HANDLE}.bridge.test",
        refresh_token="rt-1",
    )


def oidc() -> OpenIdProvider:
    """Logto's endpoints, as the bridge's discovery document names them."""
    return OpenIdProvider(
        authorization_endpoint=f"{ISSUER}/auth",
        token_endpoint=f"{ISSUER}/token",
        device_authorization_endpoint=f"{ISSUER}/device",
        revocation_endpoint=f"{ISSUER}/revoke",
        jwks_uri=f"{ISSUER}/jwks",
    )


async def unreachable(request: httpx2.Request) -> httpx2.Response:
    """A Logto no session with an empty store may ask."""
    raise AssertionError(f"no request reaches Logto: {request.url}")


class Emptied:
    """A credential store the person emptied while the relay ran."""

    where = "the emptied store"

    def load(self) -> Credential | None:
        return None

    def save(self, credential: Credential) -> None:
        raise AssertionError("a session whose store is empty saves nothing")

    def delete(self) -> None:
        raise AssertionError("a session whose store is empty has nothing to delete")


class Holding:
    """A credential store holding one credential, saving what a session hands it."""

    where = "the holding store"

    def __init__(self, credential: Credential) -> None:
        self.credential = credential

    def load(self) -> Credential | None:
        return self.credential

    def save(self, credential: Credential) -> None:
        self.credential = credential

    def delete(self) -> None:
        self.credential = None


class ClosingAtOnce:
    """A tunnel the bridge accepts and closes before the engine's hello reaches it."""

    close_code: int | None = None

    async def send(self, frame: str | bytes) -> None:
        raise ConnectionClosedError(None, Close(1006, ""))

    async def close(self) -> None:
        """Nothing to close: the bridge closed it first."""


class Session:
    """A session handing out the tokens it is given, recording what it was asked for."""

    def __init__(self, *tokens: str) -> None:
        self.tokens = list(tokens)
        self.asked: list[bool] = []

    async def access_token(self, force: bool = False) -> str:
        self.asked.append(force)
        return self.tokens.pop(0) if len(self.tokens) > 1 else self.tokens[0]


class Refusing:
    """A session whose credential the bridge signed out."""

    async def access_token(self, force: bool = False) -> str:
        raise SignedOut("the bridge signed this engine out; run ecosemantic bridge sign-in")


class SignedInAgain:
    """A session whose credential this systems directory signed in again meanwhile."""

    async def access_token(self, force: bool = False) -> str:
        raise Unauthorised("this systems directory was signed in again; this server's bridge stops")


class Unreachable:
    """A session whose first token request cannot reach Logto, and whose second answers."""

    def __init__(self, token: str = BEARER) -> None:
        self.token = token
        self.asked = 0

    async def access_token(self, force: bool = False) -> str:
        self.asked += 1
        if self.asked == 1:
            raise Unavailable("the renewal could not reach the bridge")
        return self.token


class Lapsing:
    """A session holding a token the bridge refuses, whose renewal finds the credential signed in
    again meanwhile."""

    async def access_token(self, force: bool = False) -> str:
        if force:
            raise Unauthorised(
                "this systems directory was signed in again; this server's bridge stops"
            )
        return "stale"


class Enough(Exception):
    """The test has seen the attempts it wanted."""


@dataclass
class Running:
    """A relay on a tunnel, and what it has reported and slept."""

    bridge: FakeBridge
    relay: Relay
    listener: Listener | None
    lines: list[str] = field(default_factory=list)
    task: asyncio.Task[None] | None = None


def recording(sleeps: list[float], limit: int | None = None) -> Callable[[float], Awaitable[None]]:
    """A sleep that records the wait instead of taking it, ending the relay once the limit is
    reached."""

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if limit is not None and len(sleeps) >= limit:
            raise Enough

    return sleep


@contextlib.asynccontextmanager
async def lifespan(app: ASGIApp) -> AsyncIterator[None]:
    """The application's own lifespan, which the process serving it would run."""
    held: Any = app
    while not hasattr(held, "router"):
        held = held.app
    async with held.router.lifespan_context(held):
        yield


@contextlib.asynccontextmanager
async def relaying(
    context: ServerContext,
    systems_dir: Path,
    *,
    app: ASGIApp | None = None,
    session: Session | Refusing | SignedInAgain | Unreachable | TunnelSession | None = None,
    clock: Callable[[], datetime] | None = None,
    bridge: FakeBridge | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    connect: Callable[..., Awaitable[Any]] | None = None,
) -> AsyncIterator[Running]:
    """A relay serving the engine's application over one tunnel to a bridge on loopback. The
    engine is the listener built over the context, with its local token on, unless another
    application is named; the bridge accepts the token the session hands it unless another is
    named."""
    check = ProofCheck(ISSUER, ACCOUNT, ENGINE, clock or utcnow)
    listener = None
    if app is None:
        listener = listener_for(
            dataclasses.replace(context, client={}),
            ViewSettings(transport="http", token=True),
            systems_dir,
            bridged_url=f"https://{HANDLE}.bridge.test",
            bridged=check,
        )
        listener.socket.close()
        app = listener.app
    held = listener.app if listener is not None else None
    lines: list[str] = []
    sleeps: list[float] = []
    bridge = bridge if bridge is not None else FakeBridge(ENGINE)
    async with serving(bridge) as tunnel_url:
        async with lifespan(held) if held is not None else contextlib.nullcontext():
            relay = Relay(
                app=app,
                session=session if session is not None else Session(BEARER),
                config=configuration(tunnel_url),
                engine=ENGINE,
                account=ACCOUNT,
                handle=HANDLE,
                version=VERSION,
                check=check,
                extension=BRIDGE_EXTENSION,
                report=lines.append,
                sleep=sleep if sleep is not None else recording(sleeps),
                connect=connect if connect is not None else tunnel_connect,
            )
            running = Running(bridge=bridge, relay=relay, listener=listener, lines=lines)
            running.task = asyncio.create_task(relay.run())
            try:
                yield running
            finally:
                running.task.cancel()
                await asyncio.gather(running.task, return_exceptions=True)


async def answered(app: ASGIApp, path: str, query: str = "") -> tuple[int, bytes]:
    """The status and the body an application answers on one GET, driven without a socket."""
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"view")],
        "client": ("test", 0),
        "server": ("view", 80),
    }
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], body


async def reported(lines: list[str], wanted: str, count: int = 1, timeout: float = 5) -> None:
    """Wait until the relay has reported the line this many times."""

    async def reached() -> None:
        while lines.count(wanted) < count:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(reached(), timeout)


async def settled(before: set[asyncio.Task[Any]], timeout: float = 5) -> None:
    """Wait until the loop holds no task the relay or its application started after `before`. The
    event-stream library keeps one watcher of its own for the whole loop, which is not a task of
    a stream."""

    async def reached() -> None:
        while True:
            extra = {
                task
                for task in asyncio.all_tasks() - before
                if "_shutdown_watcher" not in repr(task.get_coro())
            }
            if not extra:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(reached(), timeout)


def payload(body: bytes) -> dict[str, Any]:
    """The JSON-RPC message a bridged answer carries, over JSON or a server-sent event."""
    text = body.decode()
    data = next((line[5:].strip() for line in text.splitlines() if line.startswith("data:")), text)
    return json.loads(data)


async def ended_in_time(task: asyncio.Task[None]) -> None:
    """The relay stopped on its own."""
    await asyncio.wait_for(task, 5)


@pytest.fixture
def empty_context(bundle_dir: Path, tmp_path: Path) -> Iterator[ServerContext]:
    """A context bound to a product systems directory of its own, so the page it serves lists no
    system whatever another test file left in the session's directory."""
    built = build_context(bundle_dir, tmp_path)
    yield built
    built.close()


async def test_a_bridged_mcp_initialize_reaches_the_engine_and_answers(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir) as running:
        await running.bridge.welcomed()
        await running.bridge.start(
            1, "/mcp", method="POST", headers=MCP_HEADERS, body=json.dumps(INITIALIZE).encode()
        )
        held = await running.bridge.finished(1)
    assert held.status == 200
    assert payload(held.body)["result"]["serverInfo"]["name"] == "ecosemantic"
    assert dict(held.headers)["mcp-session-id"]


async def test_a_bridged_page_call_needs_no_local_token(empty_context: ServerContext) -> None:
    async with relaying(empty_context, empty_context.systems_dir) as running:
        await running.bridge.welcomed()
        assert running.listener is not None and running.listener.token is not None
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert running.bridge.starts[0].query == ""
    assert held.status == 200
    assert payload(held.body)["value"] == []


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"account": "account-2"}, id="another account"),
        pytest.param({"engine": OTHER_ENGINE}, id="another engine"),
        pytest.param({"door": "mcp"}, id="another door"),
        pytest.param({"now": utcnow() - timedelta(seconds=61)}, id="past its time"),
    ],
)
async def test_a_proof_for_another_account_engine_or_door_or_past_its_time_is_answered_401(
    claims: dict[str, Any], context: ServerContext, systems_dir: Path
) -> None:
    path = "/api/product-systems"
    async with relaying(context, systems_dir) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, path, proof=running.bridge.proof(path, **claims))
        held = await running.bridge.finished(1)
    assert held.status == 401


async def test_a_proof_is_judged_on_the_bridge_s_clock() -> None:
    bridge_time = datetime.now(UTC)
    check = ProofCheck(ISSUER, ACCOUNT, ENGINE, lambda: bridge_time + timedelta(minutes=5))
    bridge = FakeBridge(ENGINE, now=lambda: bridge_time)
    assert check(bridge.proof("/api/product-systems"), "/api/product-systems") is False
    check.welcome(
        Welcome(
            protocol=PROTOCOL,
            engine=ENGINE,
            account=ACCOUNT,
            handle=HANDLE,
            now=bridge_time,
            keys=[public_jwk(bridge.key.public_key(), bridge.kid)],
        )
    )
    assert check(bridge.proof("/api/product-systems"), "/api/product-systems") is True
    stale = bridge.proof("/api/product-systems", now=bridge_time - timedelta(seconds=61))
    assert check(stale, "/api/product-systems") is False


async def test_an_event_stream_reaches_the_bridge_before_it_ends_and_ends_on_reset(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir) as running:
        await running.bridge.welcomed()
        before = set(asyncio.all_tasks())
        following = context.events.followers()
        await running.bridge.start(1, "/api/events")
        started = await running.bridge.sent(1)
        assert started.status == 200
        assert dict(started.headers)["content-type"].startswith("text/event-stream")
        context.events.publish(Event(kind="layout"))
        held = await running.bridge.until(1, lambda held: b'"layout"' in held.body)
        assert not held.ended.is_set()
        await running.bridge.reset(1)
        await settled(before)
        assert context.events.followers() == following
    assert b"retry: 1000" in held.body


async def test_a_binary_body_crosses_byte_for_byte(
    context: ServerContext, systems_dir: Path
) -> None:
    body = os.urandom(200_000)

    async def exporting(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/octet-stream")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async with relaying(context, systems_dir, app=exporting) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems/export")
        held = await running.bridge.finished(1)
    assert held.status == 200
    assert held.body == body
    assert [len(chunk) for chunk in held.chunks] == [CHUNK_BYTES, CHUNK_BYTES, CHUNK_BYTES, 3_392]


@pytest.mark.parametrize("code", [1000, 1011], ids=["closed cleanly", "broken"])
async def test_requests_in_flight_end_when_the_tunnel_drops(
    code: int, context: ServerContext, systems_dir: Path
) -> None:
    seen: list[Message] = []
    entered = asyncio.Event()

    async def waiting(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        while True:
            message = await receive()
            seen.append(message)
            if message["type"] == "http.disconnect":
                return

    async with relaying(context, systems_dir, app=waiting) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        await asyncio.wait_for(entered.wait(), 5)
        await running.bridge.drop(code)
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
    assert [message["type"] for message in seen] == ["http.request", "http.disconnect"]
    assert running.lines[0] == f"bridge: connected as {HANDLE}"
    assert (
        running.lines[1] == f"bridge: offline (the tunnel closed with code {code}); retrying in 1 s"
    )
    assert running.lines[2] == f"bridge: connected as {HANDLE}"


async def test_an_unreadable_frame_bounds_the_reason_it_reports(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir) as running:
        await running.bridge.welcomed()
        await running.bridge.raw("x" * 10_000)
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
    reason = running.lines[1].removeprefix("bridge: offline (").rsplit("); retrying in ", 1)[0]
    opening = "no message of protocol 1 in '"
    assert reason == f"{opening}{'x' * (200 - len(opening))}…"


async def test_a_stream_id_is_free_again_after_the_tunnel_drops(
    context: ServerContext, systems_dir: Path
) -> None:
    async def answering(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"answered"})

    async with relaying(context, systems_dir, app=answering) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        await running.bridge.finished(1)
        await running.bridge.drop()
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert held.body == b"answered"


async def test_an_answer_the_tunnel_went_before_is_not_sent(
    context: ServerContext, systems_dir: Path
) -> None:
    entered = asyncio.Event()

    async def late(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        while (await receive())["type"] != "http.disconnect":
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async with relaying(context, systems_dir, app=late) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        await asyncio.wait_for(entered.wait(), 5)
        await running.bridge.drop()
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
    assert running.bridge.stream(1).status is None


async def test_a_token_request_that_cannot_reach_the_bridge_is_reported_and_retried(
    context: ServerContext, systems_dir: Path
) -> None:
    session = Unreachable()
    async with relaying(context, systems_dir, session=session) as running:
        await reported(running.lines, f"bridge: connected as {HANDLE}")
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert session.asked == 2
    assert running.lines == [
        "bridge: offline (the renewal could not reach the bridge); retrying in 1 s",
        f"bridge: connected as {HANDLE}",
    ]
    assert held.status == 200


async def test_a_renewal_that_cannot_reach_the_bridge_is_reported_and_retried(
    context: ServerContext, systems_dir: Path
) -> None:
    logto = FakeLogto()
    logto.live_refresh.add("rt-1")
    refused: list[str] = []

    async def answering(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == TOKEN_PATH and not refused:
            refused.append(str(request.url))
            raise httpx2.ConnectError("connection refused")
        return await logto.answer(request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(answering)) as http:
        session = TunnelSession(
            http,
            configuration("ws://127.0.0.1:1/tunnel"),
            await provider(http, LOGTO_ISSUER),
            Holding(a_credential()),
            a_credential(),
            utcnow,
        )
        async with relaying(context, systems_dir, session=session) as running:
            await reported(running.lines, f"bridge: connected as {HANDLE}")
            await running.bridge.start(1, "/api/product-systems")
            held = await running.bridge.finished(1)
    assert refused == [f"{LOGTO_ISSUER}/token"]
    assert held.status == 200
    assert running.lines == [
        f"bridge: offline (Logto at {LOGTO_ISSUER}/token could not be reached: connection "
        "refused); retrying in 1 s",
        f"bridge: connected as {HANDLE}",
    ]


async def test_a_tunnel_that_closes_as_the_hello_is_sent_is_reported_and_retried(
    context: ServerContext, systems_dir: Path
) -> None:
    closed: list[str] = []

    async def connecting(url: str, additional_headers: Any = None) -> Any:
        if not closed:
            closed.append(url)
            return ClosingAtOnce()
        return await tunnel_connect(url, additional_headers=additional_headers)

    async with relaying(context, systems_dir, connect=connecting) as running:
        await reported(running.lines, f"bridge: connected as {HANDLE}")
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert len(closed) == 1
    assert held.status == 200
    assert running.lines[0].startswith(
        "bridge: offline (the tunnel closed while a stream was being sent"
    )
    assert running.lines[0].endswith("); retrying in 1 s")
    assert running.lines[1] == f"bridge: connected as {HANDLE}"


async def test_a_store_emptied_while_the_relay_runs_reports_the_signed_out_line(
    context: ServerContext, systems_dir: Path
) -> None:
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(unreachable)) as http:
        session = TunnelSession(
            http,
            configuration("ws://127.0.0.1:1/tunnel"),
            oidc(),
            Emptied(),
            a_credential(),
            utcnow,
        )
        async with relaying(context, systems_dir, session=session) as running:
            assert running.task is not None
            await ended_in_time(running.task)
    assert running.lines == [SIGNED_OUT]


async def test_a_tunnel_refused_after_a_renewal_signs_the_relay_out_and_the_engine_serves_locally(
    empty_context: ServerContext,
) -> None:
    session = Session("stale", "renewed")
    refused = FakeBridge(ENGINE, accepted=())
    async with relaying(
        empty_context, empty_context.systems_dir, session=session, bridge=refused
    ) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [SIGNED_OUT]
        assert session.asked == [False, True]
        listener = running.listener
        assert listener is not None and listener.token is not None
        status, body = await answered(
            listener.app, "/api/product-systems", query=f"token={listener.token}"
        )
    assert status == 200
    assert payload(body)["value"] == []


async def test_an_engine_token_the_bridge_refuses_names_the_account_page_and_ends_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    presented: list[str] = []

    async def connecting(url: str, additional_headers: Any = None) -> Any:
        presented.append(additional_headers["Authorization"])
        return await tunnel_connect(url, additional_headers=additional_headers)

    refused = FakeBridge(ENGINE, accepted=())
    async with relaying(
        context,
        systems_dir,
        session=EngineTokenSession(BEARER),
        bridge=refused,
        connect=connecting,
    ) as running:
        assert running.task is not None
        await ended_in_time(running.task)
    assert presented == [f"Bearer {BEARER}"]
    assert running.lines == [ENGINE_REFUSED_LINE]


async def test_a_refused_token_is_renewed_once_and_the_tunnel_opens(
    context: ServerContext, systems_dir: Path
) -> None:
    session = Session("stale", "renewed")
    renewed = FakeBridge(ENGINE, accepted=("renewed",))
    async with relaying(context, systems_dir, session=session, bridge=renewed) as running:
        await running.bridge.welcomed()
        assert session.asked == [False, True]
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert held.status == 200


async def test_a_renewal_that_finds_the_credential_signed_in_again_ends_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    refused = FakeBridge(ENGINE, accepted=())
    async with relaying(context, systems_dir, session=Lapsing(), bridge=refused) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [SIGNED_IN_AGAIN_LINE]


async def test_a_credential_signed_in_again_ends_the_relay_with_its_own_words(
    context: ServerContext, systems_dir: Path
) -> None:
    refused = FakeBridge(ENGINE, accepted=())
    async with relaying(context, systems_dir, session=SignedInAgain(), bridge=refused) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [SIGNED_IN_AGAIN_LINE]


async def test_a_handshake_refused_for_another_reason_is_reported_and_retried(
    context: ServerContext, systems_dir: Path
) -> None:
    refusing = FakeBridge(ENGINE, accepted=(), denial=503)
    async with relaying(
        context, systems_dir, bridge=refusing, sleep=recording([], limit=1)
    ) as running:
        assert running.task is not None
        with pytest.raises(Enough):
            await running.task
        assert running.lines == [
            "bridge: offline (the bridge refused the tunnel with 503); retrying in 1 s"
        ]


async def test_a_stream_the_bridge_opens_twice_is_reported_and_the_relay_reconnects(
    context: ServerContext, systems_dir: Path
) -> None:
    seen: list[Message] = []
    entered = asyncio.Event()

    async def waiting(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        while True:
            message = await receive()
            seen.append(message)
            if message["type"] == "http.disconnect":
                return

    async with relaying(context, systems_dir, app=waiting) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        await asyncio.wait_for(entered.wait(), 5)
        await running.bridge.start(1, "/api/product-systems")
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
    assert [message["type"] for message in seen] == ["http.request", "http.disconnect"]
    assert running.lines == [
        f"bridge: connected as {HANDLE}",
        "bridge: offline (the bridge opened the stream 1 again); retrying in 1 s",
        f"bridge: connected as {HANDLE}",
    ]


async def test_a_message_the_engine_cannot_read_is_reported_and_the_relay_reconnects(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir) as running:
        await running.bridge.welcomed()
        await running.bridge.raw("not a message")
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
    assert running.lines[1].startswith(
        "bridge: offline (no message of protocol 1 in 'not a message'"
    )
    assert running.lines[1].endswith("); retrying in 1 s")
    assert "\n" not in running.lines[1]
    assert running.lines[2] == f"bridge: connected as {HANDLE}"


async def test_a_session_that_finds_the_engine_signed_out_ends_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir, session=Refusing()) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [SIGNED_OUT]
        assert running.relay.state() == "signed-out"


async def test_a_welcome_for_another_engine_stops_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir, bridge=FakeBridge(OTHER_ENGINE)) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [OTHER_ENGINE_LINE]


async def test_a_welcome_that_speaks_another_protocol_stops_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    speaking = FakeBridge(ENGINE, protocol=PROTOCOL + 1)
    async with relaying(context, systems_dir, bridge=speaking) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [
            f"bridge: the bridge speaks protocol {PROTOCOL + 1} and this engine speaks "
            f"{PROTOCOL}; update ecosemantic"
        ]


async def test_a_welcome_for_another_account_stops_the_relay(
    context: ServerContext, systems_dir: Path
) -> None:
    another = FakeBridge(ENGINE, account="account-2")
    async with relaying(context, systems_dir, bridge=another) as running:
        assert running.task is not None
        await ended_in_time(running.task)
        assert running.lines == [OTHER_ACCOUNT_LINE]


async def test_a_welcome_that_names_another_handle_is_reported_and_the_engine_serves_on(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir, bridge=FakeBridge(ENGINE, handle="ana")) as running:
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert held.status == 200
    assert running.lines == [
        "bridge: connected as ana",
        "bridge: the handle is now ana; the page address changes at the next start",
    ]


async def test_a_handle_that_changed_is_reported_once_and_not_at_every_reconnect(
    context: ServerContext, systems_dir: Path
) -> None:
    async with relaying(context, systems_dir, bridge=FakeBridge(ENGINE, handle="ana")) as running:
        await running.bridge.welcomed()
        await reported(running.lines, "bridge: connected as ana")
        assert running.relay.handle() == "ana"
        await running.bridge.drop()
        await running.bridge.welcomed()
        await running.bridge.start(1, "/api/product-systems")
        held = await running.bridge.finished(1)
    assert held.status == 200
    assert running.lines.count("bridge: connected as ana") == 2
    assert (
        running.lines.count(
            "bridge: the handle is now ana; the page address changes at the next start"
        )
        == 1
    )


async def test_the_relay_s_state_follows_the_tunnel(
    context: ServerContext, systems_dir: Path
) -> None:
    bridge = FakeBridge(ENGINE)
    released = asyncio.Event()

    async def wait_for_the_test(seconds: float) -> None:
        await released.wait()

    async with relaying(context, systems_dir, bridge=bridge, sleep=wait_for_the_test) as running:
        assert running.relay.state() == "connecting"
        await bridge.welcomed()
        await reported(running.lines, f"bridge: connected as {HANDLE}")
        assert running.relay.state() == "connected"
        await bridge.drop()
        await reported(
            running.lines,
            "bridge: offline (the tunnel closed with code 1000); retrying in 1 s",
        )
        assert running.relay.state() == "offline"
        released.set()
        await bridge.welcomed()
        await reported(running.lines, f"bridge: connected as {HANDLE}", 2)
        assert running.relay.state() == "connected"
    assert running.relay.state() == "stopped"


async def test_the_retry_waits_longer_after_each_failure_up_to_a_minute() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    lines: list[str] = []
    sleeps: list[float] = []

    async def nothing(scope: Scope, receive: Receive, send: Send) -> None:
        pass

    relay = Relay(
        app=nothing,
        session=EngineTokenSession(BEARER),
        config=configuration(f"ws://127.0.0.1:{port}/tunnel"),
        engine=ENGINE,
        account=ACCOUNT,
        handle=HANDLE,
        version=VERSION,
        check=ProofCheck(ISSUER, ACCOUNT, ENGINE, utcnow),
        extension=BRIDGE_EXTENSION,
        report=lines.append,
        sleep=recording(sleeps, limit=8),
    )
    with pytest.raises(Enough):
        await relay.run()
    assert sleeps == [1, 2, 4, 8, 16, 32, 60, 60]
    assert all(line.startswith("bridge: offline (") for line in lines)
    assert [line.rsplit("; retrying in ", 1)[1] for line in lines] == [
        f"{wait} s" for wait in sleeps
    ]
