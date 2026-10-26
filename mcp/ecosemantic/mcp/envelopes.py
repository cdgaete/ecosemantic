"""What a tool returns and what it raises: one listing shape, one answer shape, one error."""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Generic, TypeVar

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.exceptions import ValidationError as ArgumentsInvalid
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams
from pydantic import BaseModel, Field, ValidationError

from ecosemantic.compute.consequences import Consequences
from ecosemantic.errors import (
    EcoSemanticError,
    ErrorEnvelope,
    Invalid,
    NotFound,
    OtherBuild,
    Remedies,
    StaleScenario,
    error_payload,
)
from ecosemantic.mcp.calls import note
from ecosemantic.model.summary import Summarising, Summary, listed
from ecosemantic.ports.types import LogEntry, Page

T = TypeVar("T")


class Listing(BaseModel, Generic[T]):
    """One page of results, with the cursor that fetches the next."""

    items: list[T]
    has_more: bool
    next_cursor: str | None = None
    hint: str | None = None
    view_url: str | None = None

    def summarise(self) -> Summary:
        """How many items the page held, whether there are more, and its first items."""
        return listed(self.items, self.has_more)


class Answer(BaseModel, Generic[T]):
    """One value, with a hint when the caller should do something next."""

    value: T
    hint: str | None = None
    view_url: str | None = None

    def summarise(self) -> Summary | None:
        """What the value held, in short; nothing for a value whose type defines no summary."""
        if isinstance(self.value, Summarising):
            return self.value.summarise()
        if isinstance(self.value, list):
            return listed(self.value, False)
        return None


class Written(BaseModel, Generic[T]):
    """A write's answer: the entity as stored, the entry, what the write left stale, the open
    requests, the link, a hint."""

    value: T
    entry: LogEntry
    consequences: Consequences = Field(default_factory=Consequences)
    open_requests: int = 0
    view_url: str | None = None
    hint: str | None = None


class WrittenPath(BaseModel):
    """A path a tool wrote outside the store, and the hash of the state it wrote there."""

    path: str
    hash: str


def written(
    value: T,
    entry: LogEntry,
    consequences: Consequences,
    open_requests: int = 0,
    view_url: str | None = None,
) -> Written[T]:
    """The entity as stored, the entry the write appended, what it left stale, and what the
    person should see."""
    return Written[T](
        value=value,
        entry=entry,
        consequences=consequences,
        open_requests=open_requests,
        view_url=view_url,
    )


def as_uuid(value: str) -> uuid.UUID:
    """A UUID a tool was given as a string, or Invalid naming what was sent."""
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise Invalid(f"{value!r} is not a UUID") from error


def listing(page: Page[T], hint: str | None = None) -> Listing[T]:
    """A port page as the tool layer's listing."""
    return Listing[T](
        items=page.items,
        has_more=page.has_more,
        next_cursor=page.next_cursor,
        hint=hint if hint is not None else page_hint(page),
    )


REMEDIES: Remedies = {
    StaleScenario: "run rebase_scenario first",
    OtherBuild: (
        "install the build the system names, or run rebase_database to move it onto the "
        "installed build"
    ),
}


def tool_error(exc: EcoSemanticError) -> ToolError:
    """The MCP boundary's rendering of a typed error, as JSON the caller can read or parse, with
    the tool that remedies it where there is one."""
    return ToolError(error_payload(exc, REMEDIES).model_dump_json())


def envelope_of(error: Exception) -> ErrorEnvelope:
    """The envelope a failed call carried: the one a tool rendered, or invalid in the failure's
    own words."""
    try:
        return ErrorEnvelope.model_validate_json(str(error))
    except ValidationError:
        return error_payload(Invalid(str(error)))


def applied_filters(filters: Mapping[str, object]) -> list[str]:
    """The names of the filters a search was given a value for."""
    return sorted(name for name, value in filters.items() if value is not None)


def empty_search_hint(filters: Mapping[str, object], words_match: bool) -> str:
    """What a search that returned nothing should change: the filters when the words alone match
    an entry, the words themselves otherwise."""
    named = applied_filters(filters)
    if named and words_match:
        return f"no matches with {', '.join(named)} applied; the words alone match: drop a filter"
    return "no entry holds every word of the query; name fewer words"


def empty_methods_hint(query: str) -> str:
    """Names the vocabulary that lists every method when a method search returned nothing."""
    return (
        f"no method matches {query!r}; list_vocabulary names every impact_methods family "
        "and every impact_categories pair"
    )


def page_hint(page: Page[T]) -> str | None:
    """Names the cursor when a page hit its limit."""
    if not page.has_more or page.next_cursor is None:
        return None
    return f"more results; call again with cursor={page.next_cursor!r}"


def suggestion_hint(reference: str, method_id: str) -> str:
    """Names the id that a near-miss method reference resolved to."""
    return f"{reference!r} is not a method specification; resolved to {method_id}, use the id"


def carried(
    call: Callable[..., Awaitable[T]], fn: Callable[..., Awaitable[T]]
) -> Callable[..., Awaitable[T]]:
    """A wrapper made by `functools.wraps`, carrying the annotations of the function it wraps,
    which `functools.wraps` copies only as `__annotate__` from Python 3.14, so a function whose
    annotations were assigned as a mapping would leave its wrapper with none."""
    call.__annotations__ = dict(fn.__annotations__)
    return call


def boundary(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """The one place a typed error is caught and rendered; nothing below this catches."""

    @functools.wraps(fn)
    async def call(**kwargs: object) -> T:
        try:
            answer = await fn(**kwargs)
        except EcoSemanticError as exc:
            raise tool_error(exc) from exc
        note(answer)
        return answer

    return carried(call, fn)


def serialised(
    lock: Callable[[uuid.UUID], asyncio.Lock],
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Hold the product system's lock across the whole tool call, so two writes never interleave."""

    def wrap(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def call(**kwargs: object) -> T:
            async with lock(as_uuid(str(kwargs["product_system_id"]))):
                return await fn(**kwargs)

        return carried(call, fn)

    return wrap


UNKNOWN_REMEDIES: dict[tuple[str, str], str] = {
    ("update_exchange", "input"): (
        "an exchange's input is set when it is created: delete_exchange, then create_exchange "
        "with the new input, once the scenarios that override it are deleted with "
        "delete_scenario or moved off it and pinned again with rebase_scenario"
    ),
}


UNKNOWN_ARGUMENT = frozenset({"unexpected_keyword_argument", "extra_forbidden"})


def bound(fn: Callable[..., Awaitable[T]], context: object) -> Callable[..., Awaitable[T]]:
    """A tool's function with the server's context bound to its first argument, carrying the
    name, signature and annotations a tool is registered from, less that argument."""

    @functools.wraps(fn)
    async def call(**kwargs: object) -> T:
        return await fn(context, **kwargs)

    signature = inspect.signature(fn)
    call.__dict__["__signature__"] = signature.replace(
        parameters=list(signature.parameters.values())[1:]
    )
    call.__annotations__ = {
        name: hint for name, hint in fn.__annotations__.items() if name != "context"
    }
    return call


def _sent(value: object) -> str:
    """What a string argument held, said so that a caller who encoded an object or an array
    as JSON text learns to send the value itself."""
    if not isinstance(value, str):
        return ""
    try:
        decoded = json.loads(value)
    except ValueError:
        return "; it got a string"
    if isinstance(decoded, dict | list):
        shape = "object" if isinstance(decoded, dict) else "array"
        return f"; it got a string holding JSON: send the {shape} itself, not its text"
    return "; it got a string"


def _refused(name: str, problem: Mapping[str, object]) -> str:
    """One validation problem as the sentence the caller reads: an argument the tool does not
    take, with its remedy where one is known, or a value of the wrong type."""
    loc = problem["loc"]
    field = ".".join(str(p) for p in loc) if isinstance(loc, tuple) else str(loc)
    if problem["type"] in UNKNOWN_ARGUMENT:
        remedy = UNKNOWN_REMEDIES.get((name, field))
        return f"{name} does not take {field!r}: {problem['msg']}" + (
            f"; {remedy}" if remedy else ""
        )
    return f"{name}: {field!r}: {problem['msg']}{_sent(problem['input'])}"


class ArgumentRefusal(Middleware):
    """Refuses a call whose arguments do not validate as the typed `Invalid` envelope: an
    argument the tool does not take, with the remedy where one is known, or a value of the
    wrong type, with what arrived; it names the arguments the tool takes. fastmcp validates
    arguments before `boundary` runs."""

    def __init__(self, server: FastMCP) -> None:
        self.server = server

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except ArgumentsInvalid as error:
            name = context.message.name
            tool = await self.server.get_tool(name)
            if tool is None:
                raise tool_error(NotFound(f"no tool {name!r}")) from error
            takes = sorted(tool.parameters["properties"])
            cause = error.__cause__
            if not isinstance(cause, ValidationError):
                raise tool_error(Invalid(f"{name}: {error}")) from error
            said = [_refused(name, problem) for problem in cause.errors()]
            raise tool_error(
                Invalid(f"{'; '.join(said)}. {name} takes {', '.join(takes)}")
            ) from error
