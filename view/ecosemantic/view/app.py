"""The view application: the token gate, the routes and the page."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
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

from ecosemantic.access import secret_matches
from ecosemantic.errors import NotFound, Unauthorised
from ecosemantic.mcp.context import Callers
from ecosemantic.mcp.reach import BRIDGE_EXTENSION, reach
from ecosemantic.view.activity import routes as activity_routes
from ecosemantic.view.api import GATE_PARAMETER
from ecosemantic.view.api import routes as api_routes
from ecosemantic.view.credentials import routes as credential_routes
from ecosemantic.view.explorer import routes as explorer_routes
from ecosemantic.view.handling import answering, error_response
from ecosemantic.view.home import routes as home_routes
from ecosemantic.view.installs import routes as install_routes
from ecosemantic.view.olca import routes as olca_routes
from ecosemantic.view.stream import routes as stream_routes
from ecosemantic.view.tables import routes as tables_routes

UNBUILT = (
    "<!doctype html><title>EcoSemantic</title>"
    "<p>The page is not built in this installation. The API answers under /api.</p>"
)


def _proof(extension: object) -> str | None:
    """The proof a scope's bridge extension carries, or None when it carries none."""
    if not isinstance(extension, Mapping):
        return None
    proof = extension.get("proof")
    return proof if isinstance(proof, str) else None


class TokenGate:
    """Refuse a call under /api, or under a prefix the caller gates, whose token query parameter
    is not the process's, and admit a call whose scope carries the bridge's proof on every path.
    A process with no token to require gates nothing, so a server started with the bridge alone
    serves its local page. Only the application itself can hand in a scope with that extension,
    so a request over the network never reaches an application this way."""

    def __init__(
        self,
        app: ASGIApp,
        token: str | None,
        gated: tuple[str, ...] = (),
        bridged: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.prefixes = ("/api", *gated)
        self.bridged = bridged

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            if reach(scope) == "bridge":
                extensions = scope.get("extensions") or {}
                proof = _proof(extensions[BRIDGE_EXTENSION])
                if proof is None or self.bridged is None or not self.bridged(proof, scope["path"]):
                    await self._refuse(scope, receive, send, "the bridge's proof is required")
                    return
            elif scope["path"].startswith(self.prefixes) and not self._local(scope):
                await self._refuse(scope, receive, send, "the token in the link is required")
                return
        await self.app(scope, receive, send)

    def _local(self, scope: Scope) -> bool:
        """Whether the request's query carries the process's token."""
        if self.token is None:
            return True
        query = dict(parse_qsl(scope.get("query_string", b"").decode()))
        return secret_matches(query.get(GATE_PARAMETER, ""), self.token)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send, message: str) -> None:
        """Answer the request with the 401 the message states."""
        await error_response(Unauthorised(message))(scope, receive, send)


def static_dir() -> Path:
    """Where the built page lives inside the package."""
    return Path(str(resources.files("ecosemantic.view") / "static"))


def page_routes(static: Path) -> list[BaseRoute]:
    """The built page with its assets, or the one line that says there is none. A browser asks
    again for the page each time, since a build replaces it under one name, and keeps the assets,
    which a build names by their content."""
    if (static / "index.html").is_file():

        async def page(request: Request) -> Response:
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})

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


def pumping(callers: Callers, inner: Lifespan[Starlette] | None) -> Lifespan[Starlette]:
    """The application's lifespan: publish what other processes write to the stores the host
    serves, for as long as it serves them."""

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with callers.serving():
            if inner is None:
                yield
            else:
                async with inner(app):
                    yield

    return lifespan


def build_view(
    context: Callers,
    server: FastMCP,
    token: str | None = None,
    static: Path | None = None,
    routes: Sequence[BaseRoute] = (),
    gated: tuple[str, ...] = (),
    inner: Lifespan[Starlette] | None = None,
    bridged: Callable[[str, str], bool] | None = None,
) -> ASGIApp:
    """The page's API and the page. Every route under /api answers over the context the host
    binds to its request's caller. The caller's routes sit ahead of the page and its lifespan
    runs inside the view's; the token gates /api and every prefix in gated, and a request
    carrying the bridge's proof in its scope is admitted on it."""
    served: list[BaseRoute] = [
        *api_routes(server, context),
        *activity_routes(server, context),
        *stream_routes(context),
        *olca_routes(context),
        *install_routes(server, context),
        *credential_routes(context),
        *explorer_routes(context),
        *home_routes(context),
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
    return TokenGate(app, token, gated, bridged) if token or bridged else app
