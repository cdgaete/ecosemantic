"""The routes over the tools: each calls the tool the agent calls, through the in-process client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from importlib import metadata

from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, Implementation
from pydantic import JsonValue, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import Answer, Listing, as_uuid, envelope_of
from ecosemantic.mcp.recording import STARTED, VIEW
from ecosemantic.model.validation import anchors
from ecosemantic.ports.types import Layout, LogEntry, RequestDraft
from ecosemantic.view.handling import (
    ToolRefused,
    answering,
    created,
    envelope_response,
    error_response,
)

GATE_PARAMETER = "token"
IMPACT_TOOL = "calculate_impact"
STARTED_PARAMETER = "started"


async def structured(
    server: FastMCP, name: str, arguments: Mapping[str, JsonValue], started: bool = False
) -> dict[str, JsonValue]:
    """A tool's structured content, or ToolRefused carrying its error as the envelope. A call the
    server refuses as invalid parameters carries the invalid envelope. A call a person started is
    marked so, and the recorder keeps such a calculation."""
    try:
        async with Client(
            server,
            client_info=Implementation(name=VIEW, version=metadata.version("ecosemantic-view")),
        ) as client:
            result = await client.call_tool(
                name, dict(arguments), meta={STARTED: True} if started else None
            )
    except MCPError as error:
        if error.code != INVALID_PARAMS:
            raise
        raise ToolRefused(error_response(Invalid(f"{name}: {error.message}"))) from error
    except ToolError as error:
        raise ToolRefused(envelope_response(envelope_of(error))) from error
    return result.structured_content


async def call_tool(
    server: FastMCP, name: str, arguments: Mapping[str, JsonValue], started: bool = False
) -> Response:
    """One tool call rendered as an HTTP response: its structured content, or its error."""
    try:
        return JSONResponse(await structured(server, name, arguments, started))
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


def routes(server: FastMCP, context: ServerContext) -> list[Route]:
    """Every JSON route under /api, in the order the spec lists them."""

    async def databases(request: Request) -> Response:
        return await call_tool(server, "list_databases", {})

    async def vocabulary(request: Request) -> Response:
        params = request.path_params
        return await call_tool(
            server, "list_vocabulary", {"database": params["name"], "kind": params["kind"]}
        )

    async def processes(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server, "search_processes", {"database": request.path_params["name"], **args}
        )

    async def elementary_flows(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server, "search_elementary_flows", {"database": request.path_params["name"], **args}
        )

    async def methods(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server, "search_methods", {"database": request.path_params["name"], **args}
        )

    async def process(request: Request) -> Response:
        params = request.path_params
        return await call_tool(
            server,
            "get_background_process",
            {"database": params["name"], "process_id": params["ref"], "exchanges": True},
        )

    async def elementary_flow(request: Request) -> Response:
        params = request.path_params
        return await call_tool(
            server, "get_elementary_flow", {"database": params["name"], "flow_id": params["ref"]}
        )

    async def systems(request: Request) -> Response:
        return await call_tool(server, "list_product_systems", {})

    async def system(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            "get_product_system",
            {"product_system_id": request.path_params["id"], "variant": args.get("variant")},
        )

    async def parameters(request: Request) -> Response:
        args = arguments(request.query_params)
        content_hash = args.pop("hash", None)
        return await call_tool(
            server,
            "get_parameters",
            {"product_system_id": request.path_params["id"], "content_hash": content_hash},
        )

    @answering
    async def log(request: Request) -> Response:
        entries: list[LogEntry] = []
        cursor: str | None = None
        while True:
            page = Listing[LogEntry].model_validate(
                await structured(
                    server,
                    "get_product_system_log",
                    {"product_system_id": request.path_params["id"], "cursor": cursor},
                )
            )
            entries.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                return JSONResponse(Answer[list[LogEntry]](value=entries).model_dump(mode="json"))

    @answering
    async def version(request: Request) -> Response:
        params = request.path_params
        stored = await context.storage.get_version(as_uuid(params["id"]), params["hash"])
        return JSONResponse(stored.model_dump(mode="json"))

    @answering
    async def system_anchors(request: Request) -> Response:
        stored = await context.storage.get_product_system(as_uuid(request.path_params["id"]))
        return JSONResponse(Answer[list[str]](value=anchors(stored)).model_dump(mode="json"))

    async def validation(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            "validate_product_system",
            {"product_system_id": request.path_params["id"], **args},
        )

    async def server_details(request: Request) -> Response:
        """The client that introduced itself, this package's version and the two directories."""
        return JSONResponse(
            {
                "client": context.client or None,
                "version": metadata.version("ecosemantic"),
                "data_dir": str(context.data_dir),
                "systems_dir": str(context.systems_dir),
            }
        )

    def calculation(tool: str) -> Callable[[Request], Awaitable[Response]]:
        @answering
        async def handler(request: Request) -> Response:
            body = await json_object(request)
            return await call_tool(
                server,
                tool,
                {"product_system_id": request.path_params["id"], **body},
                started=request.query_params.get(STARTED_PARAMETER) == "true",
            )

        return handler

    async def runs_listed(request: Request) -> Response:
        return await call_tool(
            server, "list_runs", {"product_system_id": request.path_params["id"]}
        )

    async def run_read(request: Request) -> Response:
        return await call_tool(server, "get_run", {"run_id": request.path_params["run_id"]})

    async def run_cancelled(request: Request) -> Response:
        return await call_tool(server, "cancel_run", {"run_id": request.path_params["run_id"]})

    async def requests_listed(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            "list_requests",
            {"product_system_id": request.path_params["id"], "open_only": False, **args},
        )

    @answering
    async def request_posted(request: Request) -> Response:
        body = await json_object(request)
        system_id = as_uuid(request.path_params["id"])
        try:
            draft = RequestDraft.model_validate(
                {
                    "actor": {"kind": "person", "name": str(body.get("actor", ""))},
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

    async def layout(request: Request) -> Response:
        args = arguments(request.query_params)
        return await call_tool(
            server,
            "graph_layout",
            {"product_system_id": request.path_params["id"], "variant": args.get("variant")},
        )

    @answering
    async def place(request: Request) -> Response:
        body = await json_object(request)
        return await call_tool(
            server, "arrange_graph", {"product_system_id": request.path_params["id"], **body}
        )

    @answering
    async def release(request: Request) -> Response:
        system_id = as_uuid(request.path_params["id"])
        await context.storage.put_layout(system_id, Layout())
        args = arguments(request.query_params)
        return await call_tool(
            server,
            "graph_layout",
            {"product_system_id": str(system_id), "variant": args.get("variant")},
        )

    base = "/api/product-systems/{id}"
    return [
        Route("/api/server", server_details),
        Route("/api/databases", databases),
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
        Route(f"{base}/impact", calculation(IMPACT_TOOL), methods=["POST"]),
        Route(f"{base}/contributions", calculation("contribution_analysis"), methods=["POST"]),
        Route(f"{base}/inventory", calculation("calculate_inventory"), methods=["POST"]),
        Route(f"{base}/runs", runs_listed),
        Route(f"{base}/runs", calculation("start_monte_carlo"), methods=["POST"]),
        Route("/api/runs/{run_id}", run_read),
        Route("/api/runs/{run_id}/cancel", run_cancelled, methods=["POST"]),
        Route(f"{base}/requests", requests_listed),
        Route(f"{base}/requests", request_posted, methods=["POST"]),
        Route(f"{base}/layout", layout),
        Route(f"{base}/layout", place, methods=["POST"]),
        Route(f"{base}/layout", release, methods=["DELETE"]),
    ]
