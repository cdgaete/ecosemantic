"""The tunnel's engine side: one WebSocket to the bridge, every request it carries run on this
engine's application in this process, and every response written back on the same connection."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from starlette.types import ASGIApp, Scope
from starlette.types import Message as AsgiMessage
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as tunnel_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from ecosemantic.bridge.proofs import ProofCheck
from ecosemantic.bridge.session import Session
from ecosemantic.bridge.signin import SignedOut, secure
from ecosemantic.errors import Unauthorised, Unavailable
from ecosemantic.relay.discovery import BridgeConfiguration
from ecosemantic.relay.errors import RelayError
from ecosemantic.relay.frames import Chunk, chunks, pack, unpack
from ecosemantic.relay.messages import (
    PROTOCOL,
    Hello,
    RequestStart,
    Reset,
    ResponseStart,
    Welcome,
    decode,
    encode,
)
from ecosemantic.relay.messages import Message as TunnelMessage
from ecosemantic.settings.handover import BridgeState

_LOGGER = logging.getLogger(__name__)

BACKOFF_SECONDS = 1
BACKOFF_CEILING_SECONDS = 60
NO_CLOSE_CODE = 1006
REASON_CHARACTERS = 200
SIGNED_OUT = "bridge: signed out; run `ecosemantic bridge sign-in`"
OTHER_ENGINE = "bridge: the bridge answers for another engine; this server's bridge stops"
OTHER_ACCOUNT = "bridge: the bridge answers for another account; this server's bridge stops"

Connector = Callable[..., Awaitable[ClientConnection]]
Sleeper = Callable[[float], Awaitable[None]]


def _connected(handle: str) -> str:
    """The line a welcome is reported with."""
    return f"bridge: connected as {handle}"


def _offline(reason: str, seconds: int) -> str:
    """The line a failed or dropped tunnel is reported with: the reason on one line whatever it
    carries, cut to REASON_CHARACTERS and an ellipsis when it runs longer."""
    one_line = " ".join(reason.split())
    if len(one_line) > REASON_CHARACTERS:
        one_line = f"{one_line[:REASON_CHARACTERS]}…"
    return f"bridge: offline ({one_line}); retrying in {seconds} s"


def _handle_now(handle: str) -> str:
    """The line a welcome that names another handle is reported with."""
    return f"bridge: the handle is now {handle}; the page address changes at the next start"


def _protocol(spoken: int) -> str:
    """The line a welcome that speaks another protocol is reported with."""
    return (
        f"bridge: the bridge speaks protocol {spoken} and this engine speaks {PROTOCOL}; "
        "update ecosemantic"
    )


def _closed(code: int | None) -> str:
    """What a tunnel that closed with this code, or with none, is reported as."""
    return f"the tunnel closed with code {NO_CLOSE_CODE if code is None else code}"


def _close_code(closed: ConnectionClosed) -> int | None:
    """The code either side closed the connection with, or None when it closed without one."""
    frame = closed.rcvd or closed.sent
    return None if frame is None else frame.code


async def _uninterrupted(work: Awaitable[None]) -> None:
    """Let the work finish even while the task awaiting it is being cancelled, as the cleanup of a
    cancelled relay must."""
    task = asyncio.ensure_future(work)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class Relay:
    """The engine's side of the tunnel: it opens one WebSocket to the bridge, runs every request
    the bridge sends on the application in this process, and writes each answer back under its
    stream. It returns when the engine is signed out, or when the welcome names another engine,
    account or protocol. A token request that cannot reach the bridge, a handshake that fails, a
    tunnel that drops, and a message that is no message of the protocol or a stream opened twice
    end the tunnel: every request in flight is told the client went, the reason is reported, and
    the tunnel is opened again, waiting longer after each attempt that fails before a welcome
    arrives. An answer the tunnel cannot carry ends its own stream alone. An application that fails
    while its answer is open ends its stream as failed and is logged with its traceback; the tunnel
    serves on."""

    def __init__(
        self,
        app: ASGIApp,
        session: Session,
        config: BridgeConfiguration,
        engine: UUID,
        account: str,
        handle: str,
        version: str,
        check: ProofCheck,
        extension: str,
        report: Callable[[str], None],
        connect: Connector = tunnel_connect,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self.app = app
        self.extension = extension
        self._session = session
        self._config = config
        self._engine = engine
        self._account = account
        self._handle = handle
        self._version = version
        self._check = check
        self._report = report
        self._connect = connect
        self._sleep = sleep
        self._connection: ClientConnection | None = None
        self._sending = asyncio.Lock()
        self._streams: dict[int, _Stream] = {}
        self._state: BridgeState = "connecting"

    def state(self) -> BridgeState:
        """How the tunnel stands, as the page's health reports it to the tray: connecting before a
        handshake, connected while it serves, offline between attempts, signed out where the
        credential was refused, and stopped once a relay that was not signed out ends."""
        return self._state

    def handle(self) -> str:
        """The handle the bridge last named: the one this relay was built with until a welcome
        carries another, which the page reports beside the tunnel's state."""
        return self._handle

    async def run(self) -> None:
        """Serve the bridge's requests until the engine is signed out or the bridge answers for
        another engine, account or protocol. A tunnel that drops or fails is opened again, after a
        wait that doubles up to a minute and returns to a second once a welcome arrives."""
        try:
            backoff = BACKOFF_SECONDS
            while True:
                self._state = "connecting"
                try:
                    token = await self._token()
                    if token is None:
                        return
                    connection = await self._opened(token)
                except Unavailable as failure:
                    self._state = "offline"
                    self._report(_offline(str(failure), backoff))
                    await self._sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_CEILING_SECONDS)
                    continue
                if connection is None:
                    return
                self._connection = connection
                stop = False
                try:
                    await self._write(
                        encode(Hello(protocol=PROTOCOL, engine=self._engine, version=self._version))
                    )
                    async for frame in connection:
                        if isinstance(frame, bytes):
                            self._carried(unpack(frame))
                            continue
                        message = decode(frame)
                        if isinstance(message, Welcome):
                            if not self._welcomed(message):
                                stop = True
                                break
                            backoff = BACKOFF_SECONDS
                            continue
                        await self._accepted(message)
                except ConnectionClosed as closed:
                    reason = _closed(_close_code(closed))
                except Unavailable as failure:
                    reason = str(failure)
                except RelayError as failure:
                    reason = str(failure)
                else:
                    reason = _closed(connection.close_code)
                finally:
                    await _uninterrupted(self._dropped())
                if stop:
                    return
                self._state = "offline"
                self._report(_offline(reason, backoff))
                await self._sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_CEILING_SECONDS)
        finally:
            if self._state != "signed-out":
                self._state = "stopped"

    async def _token(self, force: bool = False) -> str | None:
        """A token to open the tunnel with, or None when this engine stops: a credential the bridge
        signed out, or a store holding none, is the signed-out line, and any other refusal is
        reported with the session's own words."""
        try:
            return await self._session.access_token(force=force)
        except SignedOut:
            self._state = "signed-out"
            self._report(SIGNED_OUT)
            return None
        except Unauthorised as refusal:
            self._report(f"bridge: {refusal}")
            return None

    async def _opened(self, token: str) -> ClientConnection | None:
        """The tunnel opened with the token, renewed once when the bridge refuses the held one, or
        None when the renewed token is refused too, which is the engine signed out."""
        url = secure(self._config.tunnel_url)
        connection = await self._handshake(url, token)
        if connection is not None:
            return connection
        renewed = await self._token(force=True)
        if renewed is None:
            return None
        connection = await self._handshake(url, renewed)
        if connection is not None:
            return connection
        self._state = "signed-out"
        self._report(SIGNED_OUT)
        return None

    async def _handshake(self, url: str, token: str) -> ClientConnection | None:
        """The tunnel this token opens, or None when the bridge refuses it; another refusal, and a
        connection that does not complete, is Unavailable."""
        try:
            return await self._connect(url, additional_headers={"Authorization": f"Bearer {token}"})
        except InvalidStatus as refused:
            if refused.response.status_code == 401:
                return None
            raise Unavailable(
                f"the bridge refused the tunnel with {refused.response.status_code}"
            ) from refused
        except OSError as failure:
            raise Unavailable(str(failure)) from failure

    async def _write(self, frame: str | bytes) -> None:
        """Send one frame, one at a time: two streams writing at once would interleave inside the
        WebSocket's own send, which refuses concurrent senders."""
        connection = self._connection
        if connection is None:
            raise Unavailable("the tunnel is closed")
        async with self._sending:
            try:
                await connection.send(frame)
            except ConnectionClosed as closed:
                raise Unavailable(
                    f"the tunnel closed while a stream was being sent ({closed})"
                ) from closed

    def _welcomed(self, message: Welcome) -> bool:
        """Say whether this engine serves the welcome's tunnel, reporting what differs. The keys
        and the clock the welcome carries are handed to the proof check, and a handle that differs
        is reported once and remembered, so a reconnect does not report it again."""
        if message.protocol != PROTOCOL:
            self._report(_protocol(message.protocol))
            return False
        if message.engine != self._engine:
            self._report(OTHER_ENGINE)
            return False
        if message.account != self._account:
            self._report(OTHER_ACCOUNT)
            return False
        self._check.welcome(message)
        self._state = "connected"
        self._report(_connected(message.handle))
        if message.handle != self._handle:
            self._report(_handle_now(message.handle))
            self._handle = message.handle
        return True

    def _carried(self, chunk: Chunk) -> None:
        """Hand a body chunk to its stream; one whose stream has ended arrived too late and is
        dropped."""
        stream = self._streams.get(chunk.stream)
        if stream is not None:
            stream.take(chunk)

    async def _accepted(self, message: TunnelMessage) -> None:
        """A message of a bridged request: its start, which runs the application, or a reset,
        which ends the stream it names."""
        if isinstance(message, RequestStart):
            if message.stream in self._streams:
                raise RelayError(f"the bridge opened the stream {message.stream} again")
            stream = _Stream(self, message)
            self._streams[message.stream] = stream
            stream.begin()
            return
        if isinstance(message, Reset):
            stream = self._streams.pop(message.stream, None)
            if stream is not None:
                await stream.finish()
            return
        raise RelayError(f"the bridge sent the engine a {message.type}")

    def _forget(self, stream: _Stream) -> None:
        """Forget a stream whose application has ended."""
        if self._streams.get(stream.identity) is stream:
            del self._streams[stream.identity]

    async def _dropped(self) -> None:
        """The tunnel is gone: no stream can be answered any more, so the relay holds none, each is
        told the client went and stopped, and the connection is closed."""
        connection = self._connection
        self._connection = None
        streams = list(self._streams.values())
        self._streams.clear()
        if connection is not None:
            await connection.close()
        for stream in streams:
            await stream.finish()


class _Stream:
    """One request on the tunnel: the scope the engine's application runs on, and the body the
    bridge sends it, handed over as it arrives."""

    def __init__(self, relay: Relay, start: RequestStart) -> None:
        self.identity = start.stream
        self._relay = relay
        self._start = start
        self._body: asyncio.Queue[Chunk | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._answer_ended = False
        self._closed = False

    def begin(self) -> None:
        """Run the application on this stream."""
        self._task = asyncio.create_task(self._serve())
        self._task.add_done_callback(self._ended)

    def take(self, chunk: Chunk) -> None:
        """Queue a body chunk for the application to read."""
        self._body.put_nowait(chunk)

    async def finish(self) -> None:
        """End the application: it is told the client disconnected, and its task is stopped even
        when it does not answer that. A stream ended here answers no failure with a reset."""
        self._closed = True
        self._body.put_nowait(None)
        task = self._task
        if task is None:
            return
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _serve(self) -> None:
        """Run the application, ending this stream as failed and logging the failure when it raises
        while its answer is open; the tunnel may be gone before the answer is written."""
        try:
            await self._relay.app(self._scope(), self._receive, self._send)
        except Unavailable:
            return
        except Exception:
            _LOGGER.exception("the application on the stream %d failed", self.identity)
            await self._failed()

    async def _failed(self) -> None:
        """End this stream as failed, unless the bridge or the tunnel ended it or its answer did; a
        tunnel gone by the write ends the reset quietly."""
        if self._closed or self._answer_ended:
            return
        with contextlib.suppress(Unavailable):
            await self._relay._write(encode(Reset(stream=self.identity, reason="failed")))

    def _ended(self, _: asyncio.Task[None]) -> None:
        """Forget this stream once its application has ended."""
        self._relay._forget(self)

    def _scope(self) -> Scope:
        """The scope the application runs on: the bridge's request as an https request, with the
        proof in the extension no request over a network carries."""
        start = self._start
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": start.method,
            "scheme": "https",
            "path": start.path,
            "raw_path": start.path.encode("latin-1"),
            "query_string": start.query.encode("latin-1"),
            "root_path": "",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in start.headers
            ],
            "client": ("bridge", 0),
            "server": self._server(),
            "extensions": {self._relay.extension: {"proof": start.proof}},
        }

    def _server(self) -> tuple[str, int] | None:
        """The host the bridge's request names and the port the door answers on, or None when the
        request names no host."""
        host = next((value for name, value in self._start.headers if name.lower() == "host"), None)
        return None if host is None else (host, 443)

    async def _receive(self) -> AsgiMessage:
        """The request's body as the bridge sends it, and the client's disconnect once the stream
        is reset or the tunnel drops."""
        chunk = await self._body.get()
        if chunk is None:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": chunk.data, "more_body": not chunk.end}

    async def _send(self, message: AsgiMessage) -> None:
        """Write the response's start and its body on the tunnel, the body in chunks of at most
        64 KiB."""
        if message["type"] == "http.response.start":
            await self._relay._write(
                encode(
                    ResponseStart(
                        stream=self.identity,
                        status=message["status"],
                        headers=[
                            (name.decode("latin-1"), value.decode("latin-1"))
                            for name, value in message["headers"]
                        ],
                    )
                )
            )
            return
        if message["type"] == "http.response.body":
            body = message.get("body", b"")
            ends = not message.get("more_body", False)
            for chunk in chunks(self.identity, body, end=ends):
                if chunk.data or chunk.end:
                    await self._relay._write(pack(chunk))
            self._answer_ended = ends
            return
        raise RelayError(f"the tunnel carries no {message['type']}")
