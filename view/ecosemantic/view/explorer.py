"""The explorer's routes: one background database's counts, its classification and method trees,
its compartments with the flows filed under them, the processes under a classification node, and
one indicator's factors. Every route reads the request context's inventory and search ports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import Answer
from ecosemantic.ports.classifications import (
    classification_tree,
    method_tree,
    ordered_schemes,
    scheme_kind,
    values_under,
)
from ecosemantic.ports.types import Compartment
from ecosemantic.view.handling import answering

T = TypeVar("T")
DEFAULT_LIMIT = 20
NO_NODE = "no node is given; the route lists the processes under a classification node"


def _answer(value: T) -> JSONResponse:
    """One value as the envelope every route of the view answers with."""
    return JSONResponse(Answer[T](value=value).model_dump(mode="json"))


def _query(params: Mapping[str, str]) -> str:
    """The text a listing is narrowed by; a request that names none narrows nothing."""
    return params.get("query", "")


def _limit(params: Mapping[str, str]) -> int:
    """The page size a request asks for, the default when it asks for none; Invalid for a size
    that is no whole number, and the port refuses one below one."""
    stated = params.get("limit")
    if stated is None:
        return DEFAULT_LIMIT
    try:
        return int(stated)
    except ValueError as error:
        raise Invalid(f"limit {stated!r} is not a whole number") from error


def _filed(compartments: Sequence[Compartment], database: str, name: str, sub: str | None) -> None:
    """Refuse a compartment the database files no flow under, and a sub-compartment the
    compartment does not hold, so neither answers an empty page."""
    filed = next((found for found in compartments if found.name == name), None)
    if filed is None:
        raise NotFound(f"no compartment {name!r} in {database!r}")
    if sub is not None and all(found.name != sub for found in filed.sub_compartments):
        raise NotFound(f"no sub-compartment {sub!r} under compartment {name!r} in {database!r}")


def routes(context: ServerContext) -> list[Route]:
    """The eight resources of one background database the explorer browses."""

    @answering
    async def summary(request: Request) -> Response:
        return _answer(await context.inventory.summarize(request.path_params["name"]))

    @answering
    async def classifications(request: Request) -> Response:
        name = request.path_params["name"]
        schemes = await context.inventory.list_classifications(name)
        kinds = {
            scheme.scheme: scheme_kind(
                scheme.scheme,
                await context.inventory.classification_values(name, scheme.scheme),
            )
            for scheme in schemes
        }
        return _answer(ordered_schemes(schemes, kinds))

    @answering
    async def tree(request: Request) -> Response:
        params = request.path_params
        values = await context.inventory.classification_values(params["name"], params["scheme"])
        return _answer(classification_tree(params["scheme"], values))

    @answering
    async def processes(request: Request) -> Response:
        params = request.path_params
        query = request.query_params
        node = query.get("node")
        if node is None:
            raise Invalid(NO_NODE)
        values = await context.inventory.classification_values(params["name"], params["scheme"])
        return _answer(
            await context.search.processes(
                params["name"],
                _query(query),
                limit=_limit(query),
                cursor=query.get("cursor"),
                classifications=values_under(params["scheme"], values, node),
            )
        )

    @answering
    async def compartments(request: Request) -> Response:
        return _answer(await context.inventory.list_compartments(request.path_params["name"]))

    @answering
    async def flows(request: Request) -> Response:
        params = request.path_params
        query = request.query_params
        name = params["name"]
        compartment = params["compartment"]
        sub = query.get("sub_compartment")
        _filed(await context.inventory.list_compartments(name), name, compartment, sub)
        return _answer(
            await context.search.elementary_flows(
                name,
                _query(query),
                compartment=compartment,
                sub_compartment=sub,
                limit=_limit(query),
                cursor=query.get("cursor"),
            )
        )

    @answering
    async def methods(request: Request) -> Response:
        listed = await context.inventory.list_methods(request.path_params["name"])
        return _answer(method_tree(listed))

    @answering
    async def factors(request: Request) -> Response:
        params = request.path_params
        query = request.query_params
        return _answer(
            await context.inventory.factors(
                params["name"],
                params["id"],
                query=_query(query),
                limit=_limit(query),
                cursor=query.get("cursor"),
            )
        )

    return [
        Route("/api/databases/{name}/summary", summary),
        Route("/api/databases/{name}/classifications", classifications),
        Route("/api/databases/{name}/classifications/{scheme}", tree),
        Route("/api/databases/{name}/classifications/{scheme}/processes", processes),
        Route("/api/databases/{name}/compartments", compartments),
        Route("/api/databases/{name}/compartments/{compartment}/flows", flows),
        Route("/api/databases/{name}/impact-methods", methods),
        Route("/api/databases/{name}/impact-methods/{id}/factors", factors),
    ]
