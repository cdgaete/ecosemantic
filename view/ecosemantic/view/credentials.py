"""The page's own credential routes: which kinds this server holds, one entered and one cleared.
They answer a peer on this machine only, since the page's token travels over plain HTTP."""

from __future__ import annotations

from typing import get_args

from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid, Unauthorised
from ecosemantic.mcp.accounts import account_advice, entry_for
from ecosemantic.mcp.context import ServerContext
from ecosemantic.ports.types import Account, CredentialKind
from ecosemantic.view.api import json_object, reach
from ecosemantic.view.handling import answering

KIND = TypeAdapter(CredentialKind)
KINDS: tuple[str, ...] = get_args(CredentialKind)


def _peer(request: Request, context: ServerContext) -> None:
    """Unauthorised unless the request reached the engine on its own computer, saying how the page
    reached the engine and what enters the account there."""
    reached = reach(request.scope)
    if reached != "here":
        advice = account_advice(context.accounts, reached)
        raise Unauthorised(advice.why, hint=advice.steps)


def _kind(name: str) -> CredentialKind:
    """The credential kind a path names, Invalid for a name that is none of them."""
    try:
        return KIND.validate_python(name)
    except ValidationError as error:
        raise Invalid(
            f"{name!r} is no credential kind; the kinds are {', '.join(KINDS)}"
        ) from error


def routes(context: ServerContext) -> list[Route]:
    """The kinds held, how a request reached the engine, one kind entered and one cleared, from
    this machine only."""

    @answering
    async def held(request: Request) -> Response:
        _peer(request, context)
        return JSONResponse({"held": sorted(context.credentials)})

    @answering
    async def entry(request: Request) -> Response:
        answer = entry_for(context.accounts, reach(request.scope))
        return JSONResponse(answer.model_dump(mode="json"))

    @answering
    async def entered(request: Request) -> Response:
        _peer(request, context)
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
        _peer(request, context)
        context.credentials.pop(_kind(request.path_params["kind"]), None)
        return Response(status_code=204)

    return [
        Route("/api/credentials", held),
        Route("/api/credentials/entry", entry),
        Route("/api/credentials/{kind}", entered, methods=["PUT"]),
        Route("/api/credentials/{kind}", cleared, methods=["DELETE"]),
    ]
