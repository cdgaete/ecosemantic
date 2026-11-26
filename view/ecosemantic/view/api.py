"""The routes over the tools: each runs the tool the agent calls, in this process."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import metadata

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import JsonValue, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid
from ecosemantic.mcp.context import Callers, ServerContext
from ecosemantic.mcp.direct import run_tool
from ecosemantic.mcp.envelopes import Answer, Listing, as_uuid, envelope_of
from ecosemantic.mcp.parameters import ParameterSpace, space_of
from ecosemantic.mcp.systems import get_product_system
from ecosemantic.model.validation import anchors
from ecosemantic.ports.types import LogEntry, MonteCarloConfig, RequestDraft
from ecosemantic.view.handling import (
    ContextHandler,
    ToolRefused,
    created,
    envelope_response,
    for_caller,
)

GATE_PARAMETER = "token"
EXPANDED = "expanded"
IMPACT_TOOL = "calculate_impact"
STARTED_PARAMETER = "started"


async def structured(
    server: FastMCP,
    context: ServerContext,
    name: str,
    arguments: Mapping[str, JsonValue],
    started: bool = False,
) -> dict[str, JsonValue]:
    """A tool's structured content, run in this process, or ToolRefused carrying its error as the
    envelope a caller reads. A call a person started is marked so, and the recorder keeps such a
    calculation."""
    try:
        return await run_tool(server, context, name, arguments, started)
    except ToolError as error:
        raise ToolRefused(envelope_response(envelope_of(error))) from error


async def call_tool(
    server: FastMCP,
    context: ServerContext,
    name: str,
    arguments: Mapping[str, JsonValue],
    started: bool = False,
) -> Response:
    """One tool call rendered as an HTTP response: its structured content, or its error."""
    try:
        return JSONResponse(await structured(server, context, name, arguments, started))
    except ToolRefused as refused:
        return refused.response


async def json_object(request: Request) -> dict[str, JsonValue]:
    """The request body as a JSON object; Invalid when it is not one."""
    try:
        body = await request.json()
    except ValueError as error:
        raise Invalid("the body is not JSON") from error
    if not isinstance(body, dict):
        raise Invalid("the body is not a JSON object")
    return body


def arguments(query: Mapping[str, str]) -> dict[str, JsonValue]:
    """Query parameters as tool arguments; the token stays out, the tool's schema types the rest."""
    return {key: value for key, value in query.items() if key != GATE_PARAMETER}


def expansion(request: Request) -> list[str] | None:
    """The cards whose rows the page shows in full, each named once; None when it names none."""
    return request.query_params.getlist(EXPANDED) or None


def routes(server: FastMCP, callers: Callers) -> list[Route]:
    """Every JSON route under /api, each answering over the context the host binds to its
    request's caller."""

    @for_caller(callers)
    async def vocabulary(request: Request, context: ServerContext) -> Response:
        params = request.path_params
        return await call_tool(
            server, context, "list_vocabulary", {"database": params["name"], "kind": params["kind"]}
        )

    @for_caller(callers)
    async def processes(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server, context, "search_processes", {"database": request.path_params["name"], **args}
        )

    @for_caller(callers)
    async def elementary_flows(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            context,
            "search_elementary_flows",
            {"database": request.path_params["name"], **args},
        )

    @for_caller(callers)
    async def methods(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server, context, "search_methods", {"database": request.path_params["name"], **args}
        )

    @for_caller(callers)
    async def process(request: Request, context: ServerContext) -> Response:
        params = request.path_params
        return await call_tool(
            server,
            context,
            "get_background_process",
            {"database": params["name"], "process_id": params["ref"], "exchanges": True},
        )

    @for_caller(callers)
    async def elementary_flow(request: Request, context: ServerContext) -> Response:
        params = request.path_params
        return await call_tool(
            server,
            context,
            "get_elementary_flow",
            {"database": params["name"], "flow_id": params["ref"]},
        )

    @for_caller(callers)
    async def systems(request: Request, context: ServerContext) -> Response:
        return await call_tool(server, context, "list_product_systems", {})

    @for_caller(callers)
    async def system(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            context,
            "get_product_system",
            {"product_system_id": request.path_params["id"], "variant": args.get("variant")},
        )

    @for_caller(callers)
    async def parameters(request: Request, context: ServerContext) -> Response:
        query = request.query_params
        content_hash = query.get("hash")
        variant = query.get("variant")
        if content_hash is not None and variant is not None:
            raise Invalid("name a hash or a variant, not both")
        if variant is None:
            return await call_tool(
                server,
                context,
                "get_parameters",
                {"product_system_id": request.path_params["id"], "content_hash": content_hash},
            )
        read = await get_product_system(context, request.path_params["id"], variant)
        return JSONResponse(
            Answer[ParameterSpace](value=space_of(read.value)).model_dump(mode="json")
        )

    @for_caller(callers)
    async def log(request: Request, context: ServerContext) -> Response:
        entries: list[LogEntry] = []
        cursor: str | None = None
        while True:
            page = Listing[LogEntry].model_validate(
                await structured(
                    server,
                    context,
                    "get_product_system_log",
                    {"product_system_id": request.path_params["id"], "cursor": cursor},
                )
            )
            entries.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                return JSONResponse(Answer[list[LogEntry]](value=entries).model_dump(mode="json"))

    @for_caller(callers)
    async def version(request: Request, context: ServerContext) -> Response:
        params = request.path_params
        stored = await context.storage.get_version(as_uuid(params["id"]), params["hash"])
        return JSONResponse(stored.model_dump(mode="json"))

    @for_caller(callers)
    async def system_anchors(request: Request, context: ServerContext) -> Response:
        stored = await context.storage.get_product_system(as_uuid(request.path_params["id"]))
        return JSONResponse(Answer[list[str]](value=anchors(stored)).model_dump(mode="json"))

    @for_caller(callers)
    async def validation(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            context,
            "validate_product_system",
            {"product_system_id": request.path_params["id"], **args},
        )

    @for_caller(callers)
    async def monte_carlo(request: Request, context: ServerContext) -> Response:
        """What a simulation samples, at the defaults its form starts from."""
        return JSONResponse(
            Answer[MonteCarloConfig](value=MonteCarloConfig()).model_dump(mode="json")
        )

    @for_caller(callers)
    async def server_details(request: Request, context: ServerContext) -> Response:
        """The client that introduced itself, this package's version and the two directories."""
        return JSONResponse(
            {
                "client": context.client or None,
                "version": metadata.version("ecosemantic"),
                "data_dir": str(context.data_dir),
                "systems_dir": str(context.systems_dir),
            }
        )

    def calculation(tool: str, **fixed: JsonValue) -> ContextHandler:
        async def handler(request: Request, context: ServerContext) -> Response:
            body = await json_object(request)
            return await call_tool(
                server,
                context,
                tool,
                {"product_system_id": request.path_params["id"], **body, **fixed},
                started=request.query_params.get(STARTED_PARAMETER) == "true",
            )

        return handler

    @for_caller(callers)
    async def runs_listed(request: Request, context: ServerContext) -> Response:
        return await call_tool(
            server, context, "list_runs", {"product_system_id": request.path_params["id"]}
        )

    @for_caller(callers)
    async def run_read(request: Request, context: ServerContext) -> Response:
        return await call_tool(
            server, context, "get_run", {"run_id": request.path_params["run_id"], "samples": True}
        )

    @for_caller(callers)
    async def run_cancelled(request: Request, context: ServerContext) -> Response:
        return await call_tool(
            server, context, "cancel_run", {"run_id": request.path_params["run_id"]}
        )

    @for_caller(callers)
    async def requests_listed(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            context,
            "list_requests",
            {"product_system_id": request.path_params["id"], "open_only": False, **args},
        )

    @for_caller(callers)
    async def request_posted(request: Request, context: ServerContext) -> Response:
        body = await json_object(request)
        system_id = as_uuid(request.path_params["id"])
        try:
            draft = RequestDraft.model_validate(
                {
                    "actor": context.posted_by(str(body.get("actor", ""))),
                    "kind": body.get("kind"),
                    "at_hash": body.get("at_hash", ""),
                    "message": body.get("message", ""),
                    "entity": body.get("entity"),
                    "entity_id": body.get("entity_id"),
                }
            )
        except ValidationError as exc:
            raise Invalid(str(exc)) from exc
        posted = await context.storage.post_request(system_id, draft)
        return created(posted)

    @for_caller(callers)
    async def layout(request: Request, context: ServerContext) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            context,
            "graph_layout",
            {
                "product_system_id": request.path_params["id"],
                "variant": args.get("variant"),
                "expanded": expansion(request),
                "detail": "drawing",
            },
        )

    @for_caller(callers)
    async def place(request: Request, context: ServerContext) -> Response:
        body = await json_object(request)
        return await call_tool(
            server,
            context,
            "arrange_graph",
            {"product_system_id": request.path_params["id"], **body, "detail": "drawing"},
        )

    @for_caller(callers)
    async def release(request: Request, context: ServerContext) -> Response:
        return await call_tool(
            server,
            context,
            "arrange_graph",
            {
                "product_system_id": request.path_params["id"],
                "placements": [],
                "release_all": True,
                "variant": arguments(request.query_params).get("variant"),
                "expanded": expansion(request),
                "detail": "drawing",
            },
        )

    resolve = for_caller(callers)
    base = "/api/product-systems/{id}"
    return [
        Route("/api/server", server_details),
        Route("/api/monte-carlo", monte_carlo),
        Route("/api/databases/{name}/vocabulary/{kind}", vocabulary),
        Route("/api/databases/{name}/processes", processes),
        Route("/api/databases/{name}/elementary-flows", elementary_flows),
        Route("/api/databases/{name}/elementary-flows/{ref}", elementary_flow),
        Route("/api/databases/{name}/methods", methods),
        Route("/api/databases/{name}/processes/{ref}", process),
        Route("/api/product-systems", systems),
        Route(base, system),
        Route(f"{base}/parameters", parameters),
        Route(f"{base}/log", log),
        Route(f"{base}/versions/{{hash}}", version),
        Route(f"{base}/validation", validation),
        Route(f"{base}/anchors", system_anchors),
        Route(f"{base}/impact", resolve(calculation(IMPACT_TOOL, samples=True)), methods=["POST"]),
        Route(
            f"{base}/contributions",
            resolve(calculation("contribution_analysis")),
            methods=["POST"],
        ),
        Route(
            f"{base}/inventory",
            resolve(calculation("calculate_inventory")),
            methods=["POST"],
        ),
        Route(f"{base}/runs", runs_listed),
        Route(
            f"{base}/runs",
            resolve(calculation("start_monte_carlo")),
            methods=["POST"],
        ),
        Route("/api/runs/{run_id}", run_read),
        Route("/api/runs/{run_id}/cancel", run_cancelled, methods=["POST"]),
        Route(f"{base}/requests", requests_listed),
        Route(f"{base}/requests", request_posted, methods=["POST"]),
        Route(f"{base}/layout", layout),
        Route(f"{base}/layout", place, methods=["POST"]),
        Route(f"{base}/layout", release, methods=["DELETE"]),
    ]
