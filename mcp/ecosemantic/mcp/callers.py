"""Who a request's caller is: the context the host answers for its scope, and the credential a
signed-in person's call must carry."""

from __future__ import annotations

from collections.abc import Mapping

from fastmcp.server.dependencies import get_http_request
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser, authorization_context

from ecosemantic.errors import Unauthorised
from ecosemantic.mcp.context import Callers, ServerContext


def request_scope() -> Mapping[str, object] | None:
    """The ASGI scope of the HTTP request being answered, or none under stdio and in process."""
    try:
        return get_http_request().scope
    except RuntimeError:
        return None


async def resolved(callers: Callers, scope: Mapping[str, object] | None) -> ServerContext:
    """The context the host binds to the request; a context that names no person is refused
    unless it is the callers it was asked of."""
    context = await callers.caller(scope)
    if context.person is None and context is not callers:
        raise RuntimeError("a caller's context names no person")
    return context


async def calling_agent(callers: Callers) -> ServerContext:
    """The context of this request's caller, refused when it names a person the request carries no
    credential for."""
    scope = request_scope()
    context = await resolved(callers, scope)
    if context.person is None:
        return context
    user = None if scope is None else scope.get("user")
    if not isinstance(user, AuthenticatedUser):
        raise Unauthorised(f"a call by {context.person.id!r} carries no credential")
    if authorization_context(user)["subject"] != context.person.id:
        raise Unauthorised(f"a call by {context.person.id!r} carries another person's credential")
    return context
