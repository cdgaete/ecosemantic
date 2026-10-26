"""The view application: the token gate, the routes and the page."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
from collections.abc import AsyncIterator, Sequence
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qsl

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Lifespan, Receive, Scope, Send

from ecosemantic.errors import NotFound, Unauthorised, Unavailable
from ecosemantic.events import pump_installs, pump_runs, pump_storage
from ecosemantic.mcp.context import ServerContext
from ecosemantic.view.activity import routes as activity_routes
from ecosemantic.view.api import GATE_PARAMETER
from ecosemantic.view.api import routes as api_routes
from ecosemantic.view.credentials import routes as credential_routes
from ecosemantic.view.handling import answering, error_response
from ecosemantic.view.installs import routes as install_routes
from ecosemantic.view.olca import routes as olca_routes
from ecosemantic.view.stream import routes as stream_routes
from ecosemantic.view.tables import routes as tables_routes

UNBUILT = (
    "<!doctype html><title>EcoSemantic</title>"
    "<p>The page is not built in this installation. The API answers under /api.</p>"
)


class TokenGate:
    """Refuse a call under /api, or under a prefix the caller gates, whose token query parameter
    is not the process's."""

    def __init__(self, app: ASGIApp, token: str, gated: tuple[str, ...] = ()) -> None:
        self.app = app
        self.token = token
        self.prefixes = ("/api", *gated)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.prefixes):
            query = dict(parse_qsl(scope.get("query_string", b"").decode()))
            if not hmac.compare_digest(query.get(GATE_PARAMETER, ""), self.token):
                refused = error_response(Unauthorised("the token in the link is required"))
                await refused(scope, receive, send)
                return
        await self.app(scope, receive, send)


def static_dir() -> Path:
    """Where the built page lives inside the package."""
    return Path(str(resources.files("ecosemantic.view") / "static"))


def page_routes(static: Path) -> list[BaseRoute]:
    """The built page with its assets, or the one line that says there is none."""
    if (static / "index.html").is_file():

        async def page(request: Request) -> Response:
            return FileResponse(static / "index.html")

        return [
            Mount("/assets", app=StaticFiles(directory=static / "assets", check_dir=False)),
            Route("/{path:path}", page),
        ]

    async def unbuilt(request: Request) -> Response:
        return HTMLResponse(UNBUILT)

    return [Route("/{path:path}", unbuilt)]


@answering
async def not_found(request: Request) -> Response:
    """A JSON 404 for any `/api/...` path no route above this one matched."""
    raise NotFound(f"no route /api/{request.path_params['path']}")


def pumping(context: ServerContext, inner: Lifespan[Starlette] | None) -> Lifespan[Starlette]:
    """The application's lifespan: publish what other processes write for as long as it serves."""

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        storage_ready = asyncio.Event()
        runs_ready = asyncio.Event()
        installs_ready = asyncio.Event()
        pumps = [
            asyncio.create_task(pump_storage(context.storage, context.events, storage_ready)),
            asyncio.create_task(pump_runs(context.runs, context.events, runs_ready)),
            asyncio.create_task(pump_installs(context.installs, context.events, installs_ready)),
        ]
        try:
            await _pumps_started(pumps, (storage_ready, runs_ready, installs_ready))
            if inner is None:
                yield
            else:
                async with inner(app):
                    yield
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)

    return lifespan


async def _pumps_started(pumps: list[asyncio.Task[None]], ready: tuple[asyncio.Event, ...]) -> None:
    """Wait until every pump is armed and has taken the stored state as published, or raise the
    error of one that ended first: a write the application goes on to serve is one a ready pump
    publishes."""
    waiting = asyncio.gather(*(event.wait() for event in ready))
    done, _ = await asyncio.wait([*pumps, waiting], return_when=asyncio.FIRST_COMPLETED)
    if waiting in done:
        return
    ended = await asyncio.gather(*pumps, return_exceptions=True)
    for outcome in ended:
        if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
            raise outcome
    raise Unavailable("a pump of the application ended before it was ready")


def build_view(
    context: ServerContext,
    server: FastMCP,
    token: str | None = None,
    static: Path | None = None,
    routes: Sequence[BaseRoute] = (),
    gated: tuple[str, ...] = (),
    inner: Lifespan[Starlette] | None = None,
) -> ASGIApp:
    """The page's API and the page. The caller's routes sit ahead of the page and its lifespan
    runs inside the view's; the token gates /api and every prefix in gated."""
    served: list[BaseRoute] = [
        *api_routes(server, context),
        *activity_routes(server, context),
        *stream_routes(context),
        *olca_routes(context),
        *install_routes(server, context),
        *credential_routes(context),
        *tables_routes(server, context),
        *routes,
        Route(
            "/api/{path:path}",
            not_found,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        ),
        *page_routes(static if static is not None else static_dir()),
    ]
    app = Starlette(routes=served, lifespan=pumping(context, inner))
    return TokenGate(app, token, gated) if token else app
