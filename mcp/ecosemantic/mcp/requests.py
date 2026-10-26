"""The request tools, and the answer every write tool returns: the count and the link."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypeVar

from fastmcp import FastMCP

from ecosemantic.compute.consequences import consequences
from ecosemantic.compute.links import link_pin, pinned, pins
from ecosemantic.mcp.calls import about
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ, WRITE
from ecosemantic.mcp.envelopes import Answer, Written, as_uuid, bound, boundary, serialised, written
from ecosemantic.mcp.linking import others
from ecosemantic.mcp.treatments import treatments_in
from ecosemantic.model.entities import ProductSystem
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import LogEntry, Outcome, Request, Resolution

T = TypeVar("T")


async def open_requests(storage: StoragePort, product_system_id: uuid.UUID) -> int:
    """How many return or edit requests on a product system carry no outcome."""
    return len(await storage.list_requests(product_system_id, open_only=True))


async def answer_write(
    context: ServerContext,
    value: T,
    entry: LogEntry,
    before: ProductSystem | None,
    after: ProductSystem,
) -> Written[T]:
    """The write envelope: what writing `after` over `before` left stale, the open requests
    after the write and the product system's link, naming the system to the call in progress.
    An added entity is `value` or inside it, so the entry's add changes carry no `after`; the
    stored log keeps it."""
    about(after.id)
    count = await open_requests(context.storage, after.id)
    linking = [
        s
        for s in await others(context.storage, after.id)
        if any(ref.product_system_id == after.id for ref in pins(s))
    ]
    reached = {e.result_hash for e in await context.storage.log(after.id)}
    at_pins = {
        ref: link_pin(await context.storage.get_version(after.id, pinned(ref)), ref)
        if ref.at_hash in reached
        else None
        for system in linking
        for ref in pins(system)
        if ref.product_system_id == after.id
    }
    treatments = await treatments_in(context.inventory, [after])
    found = consequences(before, after, linking, at_pins, treatments)
    bare = entry.model_copy(
        update={
            "changes": [
                c.model_copy(update={"after": None}) if c.op == "add" else c for c in entry.changes
            ]
        }
    )
    return written(value, bare, found, count, context.deep_link(after.id))


async def list_requests(
    context: ServerContext, product_system_id: str, open_only: bool = True
) -> Answer[list[Request]]:
    system_id = as_uuid(product_system_id)
    return Answer[list[Request]](
        value=await context.storage.list_requests(system_id, open_only),
        view_url=context.deep_link(system_id),
    )


async def resolve_request(
    context: ServerContext,
    product_system_id: str,
    request_id: str,
    resolution: Resolution,
    message: str,
) -> Answer[Request]:
    system_id = as_uuid(product_system_id)
    outcome = Outcome(
        timestamp=datetime.now(UTC),
        actor=context.acting(),
        resolution=resolution,
        message=message,
    )
    request = await context.storage.resolve_request(system_id, as_uuid(request_id), outcome)
    return Answer[Request](value=request, view_url=context.deep_link(system_id))


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the two request tools, in roster order."""
    server.tool(
        name="list_requests",
        annotations=READ,
        description=(
            "What a person asked from the browser about a product system: return and edit "
            "requests without an outcome by default, everything with open_only=false. Answer "
            "a request in the conversation, then resolve_request."
        ),
    )(boundary(bound(list_requests, context)))
    server.tool(
        name="resolve_request",
        annotations=WRITE,
        description=(
            "Record the answer to an open request: accepted, with the fix as the next write, "
            "or overridden, with the reason. The person sees the outcome beside the request."
        ),
    )(boundary(serialised(context.lock)(bound(resolve_request, context))))
