"""The page's own credential routes: which kinds this server holds, one entered and one cleared.
They answer a peer on this machine only, since the page's token travels over plain HTTP."""

from __future__ import annotations

from typing import get_args

from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid, Unauthorised
from ecosemantic.mcp.context import ServerContext
from ecosemantic.ports.types import Account, CredentialKind
from ecosemantic.view.api import json_object
from ecosemantic.view.handling import answering

LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1"})
HINT = "run ecosemantic setup, or reach the page through an SSH tunnel"
KIND = TypeAdapter(CredentialKind)
KINDS: tuple[str, ...] = get_args(CredentialKind)


def _peer(request: Request) -> None:
    """Unauthorised unless the request comes from this machine."""
    client = request.client
    peer = "" if client is None else client.host
    if peer not in LOOPBACK_PEERS:
        raise Unauthorised("a credential is entered only from this machine", hint=HINT)


def _kind(name: str) -> CredentialKind:
    """The credential kind a path names, Invalid for a name that is none of them."""
    try:
        return KIND.validate_python(name)
    except ValidationError as error:
        raise Invalid(
            f"{name!r} is no credential kind; the kinds are {', '.join(KINDS)}"
        ) from error


def routes(context: ServerContext) -> list[Route]:
    """The kinds held, one kind entered and one cleared, from this machine only."""

    @answering
    async def held(request: Request) -> Response:
        _peer(request)
        return JSONResponse({"held": sorted(context.credentials)})

    @answering
    async def entered(request: Request) -> Response:
        _peer(request)
        kind = _kind(request.path_params["kind"])
        body = await json_object(request)
        try:
            account = Account.model_validate(
                {
                    "username": body.get("username"),
                    "password": body.get("password"),
                    "token": body.get("token"),
                }
            )
        except ValidationError as error:
            raise Invalid(
                "a credential is a username and a password as text, and a token as text or none"
            ) from error
        context.credentials[kind] = account
        return Response(status_code=204)

    @answering
    async def cleared(request: Request) -> Response:
        _peer(request)
        context.credentials.pop(_kind(request.path_params["kind"]), None)
        return Response(status_code=204)

    return [
        Route("/api/credentials", held),
        Route("/api/credentials/{kind}", entered, methods=["PUT"]),
        Route("/api/credentials/{kind}", cleared, methods=["DELETE"]),
    ]
