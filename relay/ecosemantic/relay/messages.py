"""The tunnel's text messages: the opening exchange, a request's and a response's start, and a
stream's reset, each carried as one JSON document."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ecosemantic.relay.errors import RelayError

PROTOCOL = 1
Door = Literal["mcp", "page"]
ResetReason = Literal["cancelled", "failed"]
Header = tuple[str, str]


class _Message(BaseModel):
    """One message of the tunnel, frozen: what a text frame carries."""

    model_config = ConfigDict(frozen=True)


class Hello(_Message):
    """The engine opens the tunnel: the protocol it speaks, itself and the version it runs."""

    type: Literal["hello"] = "hello"
    protocol: int
    engine: UUID
    version: str


class Welcome(_Message):
    """The bridge answers: the protocol, the engine and its account, the handle it answers to, the
    moment of the exchange and the keys a bridged request's proof is checked against."""

    type: Literal["welcome"] = "welcome"
    protocol: int
    engine: UUID
    account: str
    handle: str
    now: datetime
    keys: list[dict[str, str]]


class RequestStart(_Message):
    """A request opens a stream: its door, its method, path and query, its headers and the proof
    that admits it."""

    type: Literal["request"] = "request"
    stream: int = Field(ge=1)
    door: Door
    method: str
    path: str
    query: str
    headers: list[Header]
    proof: str


class ResponseStart(_Message):
    """The engine answers a stream: the status and headers of the response its body follows."""

    type: Literal["response"] = "response"
    stream: int
    status: int
    headers: list[Header]


class Reset(_Message):
    """A stream ends without its answer: the reason it was cancelled or failed."""

    type: Literal["reset"] = "reset"
    stream: int
    reason: ResetReason


Message = Annotated[
    Hello | Welcome | RequestStart | ResponseStart | Reset, Field(discriminator="type")
]

_ADAPTER: TypeAdapter[Message] = TypeAdapter(Message)


def encode(message: Message) -> str:
    """The text frame that carries the message."""
    return _ADAPTER.dump_json(message).decode("utf-8")


def decode(text: str) -> Message:
    """The message a text frame carries, refused when the text is no message of this protocol."""
    try:
        return _ADAPTER.validate_json(text)
    except ValidationError as error:
        raise RelayError(f"no message of protocol {PROTOCOL} in {text!r}: {error}") from error


def door_of(path: str) -> Door:
    """The door a request's path belongs to: the chats' for `/mcp` and its subpaths, the page's for
    every other path."""
    return "mcp" if path == "/mcp" or path.startswith("/mcp/") else "page"
