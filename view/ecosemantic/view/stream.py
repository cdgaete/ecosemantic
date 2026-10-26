"""The event streams: what happens to one product system, and what happens in the whole
process, as it happens."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ecosemantic.events import Event
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import as_uuid
from ecosemantic.view.handling import answering

PING_SECONDS = 15
RETRY_MILLISECONDS = 1000


async def _sending(
    queue: asyncio.Queue[Event], leaving: Callable[[], None]
) -> AsyncIterator[ServerSentEvent]:
    """The frames of a stream: the page's retry interval first, then each event as it arrives,
    the queue dropped when the page goes."""
    try:
        yield ServerSentEvent(retry=RETRY_MILLISECONDS)
        while True:
            event = await queue.get()
            yield ServerSentEvent(event=event.kind, data=event.model_dump_json())
    finally:
        leaving()


def routes(context: ServerContext) -> list[Route]:
    """The two streaming routes."""

    @answering
    async def events(request: Request) -> Response:
        system_id = as_uuid(request.path_params["id"])
        await context.storage.get_product_system(system_id)
        queue = context.events.subscribe(system_id)

        def leaving() -> None:
            context.events.unsubscribe(system_id, queue)

        return EventSourceResponse(_sending(queue, leaving), ping=PING_SECONDS)

    @answering
    async def everything(request: Request) -> Response:
        queue = context.events.subscribe_all()
        return EventSourceResponse(
            _sending(queue, lambda: context.events.unsubscribe_all(queue)), ping=PING_SECONDS
        )

    return [
        Route("/api/events", everything),
        Route("/api/product-systems/{id}/events", events),
    ]
