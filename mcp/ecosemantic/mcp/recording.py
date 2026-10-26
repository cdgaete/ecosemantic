"""The one place a tool call is recorded: who made it, what it was called with and what it
answered."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams
from pydantic import JsonValue

from ecosemantic.errors import ErrorEnvelope, Invalid, NotFound
from ecosemantic.events import Event, EventBus
from ecosemantic.mcp.calls import InProgress, begin, end
from ecosemantic.mcp.effects import effect_of
from ecosemantic.mcp.envelopes import envelope_of, tool_error
from ecosemantic.model.refs import slug
from ecosemantic.model.summary import Summarising
from ecosemantic.ports.activity import ActivityPort
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import CallDraft, Effect, LogEntry, Origin, checked_agent

VIEW = "view"
AGENT_PARAMETER = "agent"
STARTED = "ecosemantic/started"


@runtime_checkable
class Logged(Protocol):
    entry: LogEntry


def client_name(context: MiddlewareContext[CallToolRequestParams]) -> str | None:
    """The name the session's client introduced itself with; None when the call has no server
    context or the client has not introduced itself."""
    served = context.fastmcp_context
    if served is None:
        return None
    introduced = served.session.client_params
    return None if introduced is None else introduced.client_info.name


def agent_named(on_url: str | None, configured: str | None, client: str) -> str:
    """The calling agent's name: the one on the URL it calls, else the one the server was given,
    else its client's name as a slug. The page's name is the page's alone."""
    if on_url is not None:
        name = on_url
    elif configured is not None:
        name = configured
    else:
        name = slug(client, "-")
    if name == VIEW and client != VIEW:
        raise Invalid(f"{VIEW!r} names the page; name the agent otherwise")
    return checked_agent(name)


async def current_hash(storage: StoragePort, product_system_id: uuid.UUID) -> str | None:
    """The hash of a product system as it is stored now, or none when no such system is stored:
    a call may name one nobody stored, and one a call named may since be deleted."""
    try:
        log = await storage.log(product_system_id)
    except NotFound:
        return None
    return log[-1].result_hash


def _named_system(arguments: Mapping[str, object]) -> uuid.UUID | None:
    named = arguments.get("product_system_id")
    if not isinstance(named, str):
        return None
    try:
        return uuid.UUID(named)
    except ValueError:
        return None


class Recorder(Middleware):
    """Records every tool call an agent makes, and every calculation a person starts from the
    page; the calculations the page makes to draw a result are not recorded."""

    def __init__(
        self,
        activity: ActivityPort,
        storage: StoragePort,
        events: EventBus,
        configured: str | None,
    ) -> None:
        self.activity = activity
        self.storage = storage
        self.events = events
        self.configured = configured

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        served = context.fastmcp_context
        if served is None:
            raise RuntimeError("a tool call arrived without its server context")
        tool = await served.fastmcp.get_tool(context.message.name)
        if tool is None:
            return await call_next(context)
        client = client_name(context)
        if client is None:
            raise RuntimeError("a tool call arrived before its client introduced itself")
        request = served.request_context.request if served.request_context else None
        on_url = request.query_params.get(AGENT_PARAMETER) if request is not None else None
        meta = served.request_context.meta if served.request_context else None
        started = isinstance(meta, dict) and meta.get(STARTED) is True
        try:
            agent = agent_named(on_url, self.configured, client)
        except Invalid as refused:
            raise tool_error(refused) from refused
        origin: Origin = "view" if client == VIEW else "agent"
        effect = effect_of(tool.annotations, tool.tags)
        progress = InProgress(agent=agent, client=client)
        token = begin(progress)
        started_at = datetime.now(UTC)
        clock = time.perf_counter()
        failed: ErrorEnvelope | None = None
        try:
            return await call_next(context)
        except Exception as raised:
            failed = envelope_of(raised)
            raise
        finally:
            end(token)
            if origin == "agent" or (effect == "compute" and started):
                await self._record(
                    progress,
                    origin,
                    context.message.name,
                    effect,
                    dict(context.message.arguments or {}),
                    started_at,
                    round((time.perf_counter() - clock) * 1000),
                    failed,
                )

    async def _record(
        self,
        progress: InProgress,
        origin: Origin,
        tool: str,
        effect: Effect,
        arguments: dict[str, JsonValue],
        started_at: datetime,
        duration_ms: int,
        failed: ErrorEnvelope | None,
    ) -> None:
        answer = progress.answer
        system = progress.product_system_id or _named_system(arguments)
        entry = answer.entry if isinstance(answer, Logged) else None
        at_hash = entry.result_hash if entry is not None else None
        if at_hash is None and system is not None and failed is None:
            at_hash = await current_hash(self.storage, system)
        call = await self.activity.record(
            CallDraft(
                agent=progress.agent,
                client=progress.client,
                origin=origin,
                tool=tool,
                effect=effect,
                arguments=arguments,
                product_system_id=system,
                at_hash=at_hash,
                entry_seq=entry.seq if entry is not None else None,
                started_at=started_at,
                duration_ms=duration_ms,
                outcome="ok" if failed is None else "error",
                summary=answer.summarise() if isinstance(answer, Summarising) else None,
                error=failed,
            )
        )
        self.events.publish(Event(kind="call", product_system_id=system, call=call))
