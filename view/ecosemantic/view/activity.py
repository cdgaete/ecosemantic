"""The activity routes: the agents, their calls, the trail of a log entry, an agent's open
trail, a call run again, and a system's calculations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from fastmcp import FastMCP
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid
from ecosemantic.mcp.context import Callers, ServerContext
from ecosemantic.mcp.envelopes import as_uuid
from ecosemantic.mcp.host import refuse_replayed_path
from ecosemantic.mcp.recording import current_hash
from ecosemantic.ports.types import open_trail, trail
from ecosemantic.view.api import IMPACT_TOOL, structured
from ecosemantic.view.handling import for_caller


def _listed(items: Sequence[BaseModel]) -> JSONResponse:
    return JSONResponse({"value": [item.model_dump(mode="json") for item in items]})


def _time(text: str | None) -> datetime | None:
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError as error:
        raise Invalid(f"after={text!r} is not an ISO 8601 time") from error


def routes(server: FastMCP, callers: Callers) -> list[Route]:
    """The six activity routes, each over the context its request's caller resolves to."""

    @for_caller(callers)
    async def agents(request: Request, context: ServerContext) -> Response:
        return _listed(await context.activity.list_agents())

    @for_caller(callers)
    async def calls(request: Request, context: ServerContext) -> Response:
        query = request.query_params
        named = query.get("product_system_id")
        return _listed(
            await context.activity.list_calls(
                agent=query.get("agent"),
                product_system_id=as_uuid(named) if named is not None else None,
                after=_time(query.get("after")),
            )
        )

    @for_caller(callers)
    async def entry_trail(request: Request, context: ServerContext) -> Response:
        system_id = as_uuid(request.path_params["id"])
        await context.storage.get_product_system(system_id)
        recorded = await context.activity.list_calls()
        return _listed(trail(recorded, system_id, request.path_params["seq"]))

    @for_caller(callers)
    async def calculations(request: Request, context: ServerContext) -> Response:
        system_id = as_uuid(request.path_params["id"])
        await context.storage.get_product_system(system_id)
        recorded = await context.activity.list_calls(product_system_id=system_id)
        return _listed([call for call in reversed(recorded) if call.tool == IMPACT_TOOL])

    @for_caller(callers)
    async def agent_trail(request: Request, context: ServerContext) -> Response:
        recorded = await context.activity.list_calls()
        named = request.query_params.get("product_system_id")
        system_id = as_uuid(named) if named is not None else None
        return _listed(open_trail(recorded, request.path_params["agent"], system_id))

    @for_caller(callers)
    async def rerun(request: Request, context: ServerContext) -> Response:
        call = await context.activity.get_call(as_uuid(request.path_params["call_id"]))
        refuse_replayed_path(call.tool, call.arguments)
        if call.effect in ("write", "delete"):
            raise Invalid(f"{call.tool} changes a model; the page reruns reads and calculations")
        result = await structured(server, context, call.tool, call.arguments, started=True)
        hash_now = (
            await current_hash(context.storage, call.product_system_id)
            if call.product_system_id is not None
            else None
        )
        return JSONResponse(
            {"value": {"result": result, "at_hash": call.at_hash, "hash_now": hash_now}}
        )

    return [
        Route("/api/agents", agents),
        Route("/api/agents/{agent}/trail", agent_trail),
        Route("/api/activity", calls),
        Route("/api/activity/{call_id}/rerun", rerun, methods=["POST"]),
        Route("/api/product-systems/{id}/log/{seq:int}/trail", entry_trail),
        Route("/api/product-systems/{id}/calculations", calculations),
    ]
