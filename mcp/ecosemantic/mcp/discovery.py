"""The discovery tools: what a background database holds and what it is called."""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ
from ecosemantic.mcp.envelopes import (
    Answer,
    Listing,
    applied_filters,
    bound,
    boundary,
    empty_methods_hint,
    empty_search_hint,
    listing,
)
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.types import (
    BackgroundProcess,
    ElementaryFlow,
    ElementaryFlowHit,
    FlowType,
    ProcessHit,
)

Kind = Literal["units", "locations", "compartments", "impact_methods", "impact_categories"]


class Term(BaseModel):
    """One entry of a database's vocabulary."""

    value: str
    detail: str | None = None


async def list_databases(context: ServerContext) -> Answer[list[Database]]:
    return Answer[list[Database]](value=await context.inventory.list_databases())


async def search_processes(
    context: ServerContext,
    database: str,
    query: str,
    location: str | None = None,
    unit: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> Listing[ProcessHit]:
    page = await context.search.processes(database, query, location, unit, limit, cursor)
    if page.items:
        return listing(page)
    filters = {"location": location, "unit": unit}
    words = bool(applied_filters(filters)) and bool(
        (await context.search.processes(database, query, None, None, 1, None)).items
    )
    return listing(page, empty_search_hint(filters, words))


async def search_elementary_flows(
    context: ServerContext,
    database: str,
    query: str,
    compartment: str | None = None,
    sub_compartment: str | None = None,
    flow_type: FlowType | None = None,
    unit: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> Listing[ElementaryFlowHit]:
    database = (await context.inventory.get_database(database)).name
    page = await context.search.elementary_flows(
        database, query, compartment, sub_compartment, flow_type, unit, limit, cursor
    )
    if page.items:
        return listing(page)
    filters = {
        "compartment": compartment,
        "sub_compartment": sub_compartment,
        "flow_type": flow_type,
        "unit": unit,
    }
    words = bool(applied_filters(filters)) and bool(
        (
            await context.search.elementary_flows(database, query, None, None, None, None, 1, None)
        ).items
    )
    return listing(page, empty_search_hint(filters, words))


async def search_methods(
    context: ServerContext, database: str, query: str, limit: int = 20, cursor: str | None = None
) -> Listing[Method]:
    page = await context.search.methods(database, query, limit, cursor)
    if not page.items:
        return listing(page, empty_methods_hint(query))
    return listing(page)


async def get_background_process(
    context: ServerContext, database: str, process_id: str, exchanges: bool = False
) -> Answer[BackgroundProcess]:
    ref = BackgroundRef(database=database, id=process_id)
    return Answer[BackgroundProcess](
        value=await context.inventory.get_process(ref, exchanges=exchanges)
    )


async def get_elementary_flow(
    context: ServerContext, database: str, flow_id: str
) -> Answer[ElementaryFlow]:
    found = await context.inventory.get_database(database)
    ref = ElementaryFlowRef(database=found.elementary_flows, id=flow_id)
    return Answer[ElementaryFlow](value=await context.inventory.get_elementary_flow(ref))


async def list_vocabulary(context: ServerContext, database: str, kind: Kind) -> Answer[list[Term]]:
    if kind == "units":
        terms = [Term(value=u) for u in await context.inventory.list_units(database)]
    elif kind == "locations":
        terms = [Term(value=lo) for lo in await context.inventory.list_locations(database)]
    elif kind == "compartments":
        terms = []
        for compartment in await context.inventory.list_compartments(database):
            terms.append(Term(value=compartment.name, detail=f"{compartment.flow_count} flows"))
            terms += [
                Term(value=f"{compartment.name}/{sub}") for sub in compartment.sub_compartments
            ]
    elif kind == "impact_methods":
        counts: dict[str, int] = {}
        for method in await context.inventory.list_methods(database):
            counts[method.impact_method] = counts.get(method.impact_method, 0) + 1
        terms = [
            Term(value=name, detail=f"{n} method" if n == 1 else f"{n} methods")
            for name, n in sorted(counts.items())
        ]
    else:
        seen: list[str] = []
        for method in await context.inventory.list_methods(database):
            pair = f"{method.impact_method} > {method.impact_category}"
            if pair not in seen:
                seen.append(pair)
        terms = [Term(value=pair) for pair in seen]
    return Answer[list[Term]](value=terms)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the seven discovery tools, in roster order."""
    server.tool(
        name="list_databases",
        annotations=READ,
        description=(
            "The background databases this server serves: name, scheme, version, system model, "
            "and the elementary_flows database that flow refs carry."
        ),
    )(boundary(bound(list_databases, context)))
    server.tool(
        name="search_processes",
        annotations=READ,
        description=(
            "Search a background database for unit processes by name and reference product. "
            "Returns a page; pass next_cursor to continue. location matches an exact code, such "
            "as CH, RER or GLO, never a region that holds it: list_vocabulary with kind "
            "'locations' lists the codes, and get_background_process answers a dataset's "
            'comment, where its geography is qualified. Example: {"database": '
            '"ecoinvent-3.12-cutoff", "query": "electricity high voltage", '
            '"location": "CL"}.'
        ),
    )(boundary(bound(search_processes, context)))
    server.tool(
        name="search_elementary_flows",
        annotations=READ,
        description=(
            "Search elementary flows by name, compartment or CAS. database is the background "
            "database or its elementary_flows database; the hits are the same."
        ),
    )(boundary(bound(search_elementary_flows, context)))
    server.tool(
        name="search_methods",
        annotations=READ,
        description=(
            "Search a database's impact assessment methods by words in their names. Each hit "
            "carries an id; calculate_impact takes the id, never the specification string. "
            "list_vocabulary names every impact method family and every category. Pass "
            "next_cursor to continue."
        ),
    )(boundary(bound(search_methods, context)))
    server.tool(
        name="get_background_process",
        annotations=READ,
        description=(
            "One background process by its native id. With exchanges, every exchange of the "
            "dataset: its flow and its supplier apart, its side and whether it is the dataset's "
            "reference output, and, for an input the install cut off, the reason it carries and "
            "no input."
        ),
    )(boundary(bound(get_background_process, context)))
    server.tool(
        name="get_elementary_flow",
        annotations=READ,
        description=(
            "One elementary flow by its id, with compartment, unit, CAS and synonyms. database "
            "is the background database or its elementary_flows database."
        ),
    )(boundary(bound(get_elementary_flow, context)))
    server.tool(
        name="list_vocabulary",
        annotations=READ,
        description=(
            "A database's controlled vocabulary: units, locations, compartments, "
            "impact_methods or impact_categories. Use it to find the exact spelling a filter "
            "or calculate_impact takes."
        ),
    )(boundary(bound(list_vocabulary, context)))
