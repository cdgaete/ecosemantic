"""The tool call in progress: who is making it, and what the tool hands the recorder about it."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class InProgress:
    """One call while it runs: its agent and its client, the typed answer, and the system it is
    about."""

    agent: str
    client: str
    answer: object = None
    product_system_id: uuid.UUID | None = None


_call: ContextVar[InProgress | None] = ContextVar("ecosemantic_call", default=None)


def begin(call: InProgress) -> Token[InProgress | None]:
    """Make a call the one in progress, answering the token that ends it."""
    return _call.set(call)


def end(token: Token[InProgress | None]) -> None:
    """End the call in progress the token began."""
    _call.reset(token)


def current() -> InProgress | None:
    """The call in progress, or none outside a tool call."""
    return _call.get()


def note(answer: object) -> None:
    """Hand the call in progress its typed answer. Outside a call nobody reads one."""
    call = _call.get()
    if call is not None:
        call.answer = answer


def about(product_system_id: uuid.UUID) -> None:
    """Name the system the call in progress is about. Outside a call nobody reads it."""
    call = _call.get()
    if call is not None:
        call.product_system_id = product_system_id
