"""A bridge on loopback for the relay's tests: one WebSocket endpoint that checks the bearer,
answers the engine's hello with a welcome, mints the proofs its requests carry, and collects what
the engine answers under each stream."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from ecosemantic.relay.discovery import BridgeConfiguration
from ecosemantic.relay.frames import Chunk, chunks, pack, unpack
from ecosemantic.relay.messages import (
    PROTOCOL,
    Door,
    Header,
    Hello,
    Message,
    RequestStart,
    Reset,
    ResetReason,
    ResponseStart,
    Welcome,
    decode,
    door_of,
    encode,
)
from ecosemantic.relay.proof import mint_proof, public_jwk

ISSUER = "https://bridge.test"
ACCOUNT = "account-1"
HANDLE = "carlos"
KID = "the-bridge-key"
BRIDGED_HOST = "carlos.bridge.test"
TUNNEL_PATH = "/tunnel"
BEARER = "at-1"
SECONDS = 5
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))


def configuration(tunnel_url: str) -> BridgeConfiguration:
    """The bridge's discovery document, naming the tunnel an engine opens at this server."""
    return BridgeConfiguration(
        issuer=ISSUER,
        browser_client_id="the-engine-browser",
        device_client_id="the-engine-device",
        tunnel_resource=f"{ISSUER}/tunnel",
        tunnel_scope="tunnel",
        tunnel_url=tunnel_url,
        connector_url=f"{ISSUER}/mcp",
        registration_url=f"{ISSUER}/register",
    )


@dataclass
class Collected:
    """What the engine answered one stream: its response's start, the chunks of its body, and the
    reset that ended it instead."""

    status: int | None = None
    headers: list[Header] = field(default_factory=list)
    chunks: list[bytes] = field(default_factory=list)
    reset: Reset | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    ended: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def body(self) -> bytes:
        """The bytes the engine answered, its chunks joined."""
        return b"".join(self.chunks)


class FakeBridge:
    """One bridge's tunnel: it holds an Ed25519 key, refuses the bearers it does not accept, and
    records what each stream of the engine answered."""

    def __init__(
        self,
        engine: UUID,
        *,
        account: str = ACCOUNT,
        handle: str = HANDLE,
        protocol: int = PROTOCOL,
        now: Callable[[], datetime] | None = None,
        accepted: Iterable[str] = (BEARER,),
        denial: int = 401,
    ) -> None:
        self.engine = engine
        self.account = account
        self.handle = handle
        self.protocol = protocol
        self.now = now or (lambda: datetime.now(UTC))
        self.accepted = set(accepted)
        self.denial = denial
        self.key = KEY
        self.kid = KID
        self.hello: Hello | None = None
        self.tunnel: WebSocket | None = None
        self.welcomes: asyncio.Queue[None] = asyncio.Queue()
        self.starts: list[RequestStart] = []
        self.streams: dict[int, Collected] = {}

    def welcome(self) -> Welcome:
        """The message this bridge answers an engine's hello with, holding its clock and its
        key."""
        return Welcome(
            protocol=self.protocol,
            engine=self.engine,
            account=self.account,
            handle=self.handle,
            now=self.now(),
            keys=[public_jwk(self.key.public_key(), self.kid)],
        )

    def proof(
        self,
        path: str,
        *,
        account: str | None = None,
        engine: UUID | None = None,
        door: Door | None = None,
        now: datetime | None = None,
    ) -> str:
        """A proof for one request to the path, this account's and this engine's and for the door
        the path belongs to unless another is named."""
        return mint_proof(
            self.key,
            self.kid,
            ISSUER,
            self.account if account is None else account,
            self.engine if engine is None else engine,
            door_of(path) if door is None else door,
            self.now() if now is None else now,
        )

    def stream(self, stream: int) -> Collected:
        """What this stream has answered, collected from now on."""
        return self.streams.setdefault(stream, Collected())

    async def tunnel_endpoint(self, websocket: WebSocket) -> None:
        """The tunnel: a bearer this bridge accepts opens it, the engine's hello is answered with
        the welcome, and every frame after it is collected under its stream."""
        if _bearer(websocket) not in self.accepted:
            await websocket.send_denial_response(PlainTextResponse("", status_code=self.denial))
            return
        await websocket.accept()
        self.tunnel = websocket
        try:
            self.hello = decode(await websocket.receive_text())
            await websocket.send_text(encode(self.welcome()))
            self.welcomes.put_nowait(None)
            while True:
                frame = await websocket.receive()
                if frame["type"] == "websocket.disconnect":
                    return
                if frame.get("text") is not None:
                    self._message(decode(frame["text"]))
                elif frame.get("bytes") is not None:
                    self._chunk(unpack(frame["bytes"]))
        finally:
            self.tunnel = None

    async def start(
        self,
        stream: int,
        path: str = "/api/product-systems",
        *,
        method: str = "GET",
        query: str = "",
        headers: Iterable[Header] | None = None,
        body: bytes = b"",
        proof: str | None = None,
    ) -> None:
        """Open a stream on the tunnel: the request's start, with the bridged host and this
        bridge's proof unless another is named, then its body. A stream opened again is collected
        afresh, since a stream is one request."""
        started = RequestStart(
            stream=stream,
            door=door_of(path),
            method=method,
            path=path,
            query=query,
            headers=[("host", BRIDGED_HOST), *(headers or ())],
            proof=self.proof(path) if proof is None else proof,
        )
        self.starts.append(started)
        self.streams[stream] = Collected()
        await self._send_text(encode(started))
        await self.send(stream, body)

    async def raw(self, text: str) -> None:
        """Send a text frame that is no message of the protocol, as a broken bridge does."""
        await self._send_text(text)

    async def send(self, stream: int, body: bytes) -> None:
        """The body of a stream, in the chunks the tunnel carries it in."""
        for chunk in chunks(stream, body, end=True):
            await self._send_bytes(pack(chunk))

    async def reset(self, stream: int, reason: ResetReason = "cancelled") -> None:
        """End a stream without an answer, as the bridge does when the chat goes."""
        await self._send_text(encode(Reset(stream=stream, reason=reason)))

    async def drop(self, code: int = 1000) -> None:
        """Close the tunnel from this side: cleanly, or with another code as a failure does."""
        tunnel = self.tunnel
        assert tunnel is not None
        await tunnel.close(code=code)

    async def welcomed(self, number: int = 1, timeout: float = SECONDS) -> None:
        """Wait until this many tunnels have been welcomed."""
        for _ in range(number):
            await asyncio.wait_for(self.welcomes.get(), timeout)

    async def sent(self, stream: int, timeout: float = SECONDS) -> Collected:
        """Wait until a response's start has arrived, and return what the stream holds."""
        held = self.stream(stream)
        await asyncio.wait_for(held.started.wait(), timeout)
        return held

    async def finished(self, stream: int, timeout: float = SECONDS) -> Collected:
        """Wait until the stream has ended, by its last chunk or by a reset, and return what it
        holds."""
        held = self.stream(stream)
        await asyncio.wait_for(held.ended.wait(), timeout)
        return held

    async def until(
        self, stream: int, holding: Callable[[Collected], bool], timeout: float = SECONDS
    ) -> Collected:
        """Wait until the stream holds what the predicate names, and return it."""
        held = self.stream(stream)
        while not holding(held):
            held.arrived.clear()
            await asyncio.wait_for(held.arrived.wait(), timeout)
        return held

    def _message(self, message: Message) -> None:
        if isinstance(message, ResponseStart):
            held = self.stream(message.stream)
            held.status = message.status
            held.headers = list(message.headers)
            held.started.set()
            return
        if isinstance(message, Reset):
            held = self.stream(message.stream)
            held.reset = message
            held.ended.set()
            return
        raise AssertionError(f"the engine sent the bridge a {type(message).__name__}")

    def _chunk(self, chunk: Chunk) -> None:
        held = self.stream(chunk.stream)
        held.chunks.append(chunk.data)
        held.arrived.set()
        if chunk.end:
            held.ended.set()

    async def _send_text(self, text: str) -> None:
        tunnel = self.tunnel
        assert tunnel is not None
        await tunnel.send_text(text)

    async def _send_bytes(self, frame: bytes) -> None:
        tunnel = self.tunnel
        assert tunnel is not None
        await tunnel.send_bytes(frame)


def _bearer(websocket: WebSocket) -> str:
    """The token a tunnel opens with, as its Authorization header carries it."""
    return websocket.headers.get("authorization", "").removeprefix("Bearer ")


@contextlib.asynccontextmanager
async def serving(bridge: FakeBridge) -> AsyncIterator[str]:
    """The tunnel's address while a server on loopback answers it."""
    app = Starlette(routes=[WebSocketRoute(TUNNEL_PATH, bridge.tunnel_endpoint)])
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=0, log_config=None, access_log=False, lifespan="off"
        )
    )
    running = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"ws://127.0.0.1:{port}{TUNNEL_PATH}"
    finally:
        server.should_exit = True
        await running
