"""The calculation tools: an impact, its contributions, and its inventory."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastmcp import FastMCP
from pydantic import Field

from ecosemantic.compute.links import held_pins, linked_credit_loops, linked_documents, pinned
from ecosemantic.compute.montecarlo import paired_delta, paired_samples
from ecosemantic.compute.overrides import apply_variant
from ecosemantic.compute.parameters import materialize
from ecosemantic.compute.results import (
    ContributionResult,
    ImpactResult,
    InventoryResult,
    PinBehind,
    VariantScores,
)
from ecosemantic.errors import Invalid, NotFound, StaleScenario
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import COMPUTE, READ
from ecosemantic.mcp.envelopes import (
    Answer,
    Listing,
    applied_filters,
    as_uuid,
    bound,
    boundary,
    empty_search_hint,
    listing,
    stranger,
    suggestion_hint,
)
from ecosemantic.mcp.linking import moved_by
from ecosemantic.mcp.panels import panel
from ecosemantic.mcp.treatments import named_backwards, treatments_of
from ecosemantic.model.canonical import base_pin, stale
from ecosemantic.model.entities import DemandItem, Method, ProductSystem, nearest_names
from ecosemantic.model.refs import BackgroundRef, Database, ForegroundRef
from ecosemantic.model.validation import credit_loops, reference_of
from ecosemantic.ports.calculation import CUTOFF, MAX_LEVEL, MAX_NODES, TOP_N, CalculationPort
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.types import (
    MAX_DRAWS,
    N_HELP,
    N_MAX,
    N_MAX_HELP,
    N_MIN,
    N_MIN_HELP,
    Decomposition,
    InventoryRow,
    LinkedLoop,
    MonteCarloConfig,
    Page,
    System,
    page_start,
)

MAX_ITERATIONS = 200


class ImpactMonteCarlo(MonteCarloConfig):
    """What `calculate_impact` samples: `MonteCarloConfig`, with every count capped at the draws
    one call takes. `start_monte_carlo` takes the config whole."""

    n_min: int = Field(default=N_MIN, ge=1, le=MAX_ITERATIONS, description=N_MIN_HELP)
    n_max: int = Field(default=N_MAX, ge=1, le=MAX_ITERATIONS, description=N_MAX_HELP)
    n: int | None = Field(default=None, ge=1, le=MAX_ITERATIONS, description=N_HELP)


class InventoryListing(Listing[InventoryRow]):
    """One page of inventory rows over the database build `database` names, with the processes
    of each loop holding a credit, whose delivery no check decides, each exchange sending a
    positive amount to a treatment, which runs it backwards, and the amounts set aside as
    float64 residue: those at or below `floor`, which `dropped` counts."""

    database: Database
    credit_loops: list[list[str]]
    floor: float
    dropped: int
    linked_credit_loops: list[LinkedLoop] = Field(default_factory=list)
    treatments_run_backwards: list[str] = Field(default_factory=list)


def inventory_page(
    rows: list[InventoryRow], compartment: str | None, query: str | None, limit: int, offset: int
) -> Page[InventoryRow]:
    """The rows that pass the filters, in compartment then name order, from the offset."""
    terms = [t.lower() for t in (query or "").split()]
    kept = sorted(
        (
            r
            for r in rows
            if (compartment is None or r.compartment == compartment)
            and all(t in r.name.lower() for t in terms)
        ),
        key=lambda r: (r.compartment, r.name, r.flow.id),
    )
    return Page.at_offset(kept[offset : offset + limit], len(kept) > offset + limit, offset, limit)


def demand_of(system: ProductSystem, demand: list[DemandItem] | None) -> list[DemandItem]:
    """The demand as the port takes it; without one, a unit of the reference process."""
    if not demand:
        return [DemandItem(ref=ForegroundRef(code=reference_of(system, "demand")), amount=1.0)]
    return demand


async def methods_for(
    inventory: InventoryPort, database: str, method_id: str | None, impact_method: str | None
) -> tuple[list[Method], str | None]:
    """The methods to characterise with, and a hint when a specification was used for an id."""
    if method_id is None:
        if impact_method is None:
            raise Invalid("name exactly one of method_id or impact_method")
        found = await inventory.list_methods(database, impact_method)
        if not found:
            families = sorted({m.impact_method for m in await inventory.list_methods(database)})
            nearest = ", ".join(repr(name) for name in nearest_names(families, impact_method))
            raise NotFound(
                f"no impact method {impact_method!r} in {database!r}; "
                + (
                    f"the nearest are {nearest}"
                    if nearest
                    else "list_vocabulary with kind 'impact_methods' lists them"
                )
            )
        return found, None
    if impact_method is not None:
        raise Invalid("name exactly one of method_id or impact_method")
    method = await inventory.resolve_method(database, method_id)
    hint = None if method_id == method.id else suggestion_hint(method_id, method.id)
    return [method], hint


async def one_method(
    inventory: InventoryPort, database: str, method_id: str | None, impact_method: str | None
) -> tuple[Method, str | None]:
    """Exactly one method, for the tools that decompose a single total."""
    methods, hint = await methods_for(inventory, database, method_id, impact_method)
    if len(methods) != 1:
        raise Invalid(f"a decomposition takes one method; {impact_method!r} names {len(methods)}")
    return methods[0], hint


async def impact_of(
    calculation: CalculationPort,
    base: ProductSystem,
    methods: list[Method],
    demand: list[DemandItem] | None = None,
    variants: Sequence[str] = (),
    monte_carlo: MonteCarloConfig | None = None,
    linked: dict[uuid.UUID, ProductSystem] | None = None,
    treatments: frozenset[BackgroundRef] | None = None,
) -> ImpactResult:
    """The scores of a materialised product system and of each named variant against them, with
    the uncertainty of both when a Monte Carlo block is given. `linked` holds every system the
    base reaches through its links, each at its pin and materialised; given the background's
    `treatments`, the base and each variant name every exchange sending a positive amount to
    one."""
    linked = linked or {}
    inside = linked_credit_loops(linked.values())
    items = demand_of(base, demand)
    system = System.of(base, linked)
    scores = await calculation.scores(system, items, methods)
    uncertainty = (
        await calculation.monte_carlo(system, items, methods, monte_carlo)
        if monte_carlo is not None
        else None
    )
    result = ImpactResult(
        product_system=base.name,
        database=base.database,
        scores=scores,
        credit_loops=credit_loops(base),
        linked_credit_loops=inside,
        uncertainty=uncertainty,
        treatments_run_backwards=named_backwards(base, linked, treatments),
    )
    for name in variants:
        varied = apply_variant(base, name)
        varied_system = System.of(varied, linked)
        varied_items = demand_of(varied, demand)
        varied_scores = await calculation.scores(varied_system, varied_items, methods)
        varied_mc = None
        paired = None
        if monte_carlo is not None and uncertainty is not None:
            varied_mc = await calculation.monte_carlo(
                varied_system, varied_items, methods, monte_carlo
            )
            paired = [
                paired_delta(*paired_samples(uncertainty, varied_mc, c))
                for c in range(len(uncertainty.categories))
            ]
        deltas = [v.value - b.value for b, v in zip(scores, varied_scores, strict=True)]
        result.variants.append(
            VariantScores(
                name=name,
                scores=varied_scores,
                deltas=deltas,
                credit_loops=credit_loops(varied),
                linked_credit_loops=inside,
                treatments_run_backwards=named_backwards(varied, linked, treatments),
                uncertainty=varied_mc,
                paired_deltas=paired,
            )
        )
    return result


def result_link(
    context: ServerContext,
    system: ProductSystem,
    page: str,
    method_id: str | None = None,
    impact_method: str | None = None,
    variants: Sequence[str] = (),
    demand: list[DemandItem] | None = None,
) -> str | None:
    """The result page that reproduces a calculation, in the query parameters the page's
    results editor reads: the method, the variants, and the amount of the reference process
    when the demand is that process alone."""
    params = [("method_id", method_id), ("impact_method", impact_method)]
    params.append(("variants", ",".join(variants) or None))
    if (
        demand is not None
        and len(demand) == 1
        and isinstance(demand[0].ref, ForegroundRef)
        and demand[0].ref.code == system.reference_process
    ):
        params.append(("amount", str(demand[0].amount)))
    given = [(k, v) for k, v in params if v is not None]
    return context.page_link(system.id, f"/results/{page}", given)


async def refuse_stale(
    context: ServerContext, stored: ProductSystem, variants: Sequence[str]
) -> None:
    """StaleScenario for the first named scenario pinned to a base the system has left, naming
    the entry of its log that moved the base."""
    for scenario in stored.scenarios:
        if scenario.name in variants and stale(stored, scenario):
            entry = await moved_by(context.storage, stored.id, scenario.base_hash)
            raise StaleScenario(
                scenario.name,
                scenario.base_hash,
                base_pin(stored),
                None if entry is None else f"entry {entry.seq} ({entry.message})",
            )


async def variant_of(context: ServerContext, stored: ProductSystem, name: str) -> ProductSystem:
    """The system with the named scenario or case applied, refusing a stale scenario by the log
    entry that moved its base."""
    await refuse_stale(context, stored, [name])
    return apply_variant(stored, name)


async def calculate_impact(
    context: ServerContext,
    product_system_id: str,
    method_id: str | None = None,
    impact_method: str | None = None,
    demand: list[DemandItem] | None = None,
    variants: list[str] | None = None,
    monte_carlo: ImpactMonteCarlo | None = None,
) -> Answer[ImpactResult]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    await refuse_stale(context, stored, variants or ())
    linked = await linked_documents(stored, context.storage.get_version)
    base = materialize(stored)
    methods, hint = await methods_for(
        context.inventory, stored.database.name, method_id, impact_method
    )
    result = await impact_of(
        context.calculation,
        base,
        methods,
        demand=demand,
        variants=variants or (),
        monte_carlo=monte_carlo,
        linked=linked,
        treatments=await treatments_of(context.inventory, base, linked),
    )
    result.links_behind = [
        PinBehind(product_system_id=p.ref.product_system_id, name=p.name, at_hash=pinned(p.ref))
        for p in await held_pins(stored, context.storage)
        if p.name is not None and p.current != p.at
    ]
    link = result_link(context, stored, "impact", method_id, impact_method, variants or (), demand)
    return Answer[ImpactResult](value=result, hint=hint, view_url=link)


async def contributions_of(
    calculation: CalculationPort,
    treatments: frozenset[BackgroundRef] | None,
    base: ProductSystem,
    linked: dict[uuid.UUID, ProductSystem],
    method: Method,
    items: list[DemandItem],
    by: Decomposition = "process",
    top_n: int = TOP_N,
    max_level: int = MAX_LEVEL,
    max_nodes: int = MAX_NODES,
    cutoff: float = CUTOFF,
) -> ContributionResult:
    """One score of a materialised product system, decomposed along `by`, with the loops holding
    a credit and the exchanges running a treatment backwards. A flat list keeps the `top_n`
    largest items whose fraction reaches `cutoff` and says what it leaves out."""
    system = System.of(base, linked)
    named = credit_loops(base)
    inside = linked_credit_loops(linked.values())
    backwards = named_backwards(base, linked, treatments)
    if by == "process":
        found = await calculation.hotspots(system, items, method, top_n, cutoff)
        value = ContributionResult(
            database=base.database,
            by=by,
            total=found.total,
            processes=found.items,
            cut=found.cut,
            credit_loops=named,
            linked_credit_loops=inside,
            treatments_run_backwards=backwards,
        )
    elif by == "flow":
        flows = await calculation.flow_hotspots(system, items, method, top_n, cutoff)
        value = ContributionResult(
            database=base.database,
            by=by,
            total=flows.total,
            flows=flows.items,
            cut=flows.cut,
            credit_loops=named,
            linked_credit_loops=inside,
            treatments_run_backwards=backwards,
        )
    else:
        tree = await calculation.contribution_tree(
            system, items, method, max_level, max_nodes, cutoff
        )
        value = ContributionResult(
            database=base.database,
            by=by,
            total=tree.total,
            root=tree.root,
            truncated=tree.truncated,
            credit_loops=named,
            linked_credit_loops=inside,
            treatments_run_backwards=backwards,
        )
    return value


async def contribution_analysis(
    context: ServerContext,
    product_system_id: str,
    by: Decomposition = "process",
    method_id: str | None = None,
    impact_method: str | None = None,
    demand: list[DemandItem] | None = None,
    top_n: int = TOP_N,
    max_level: int = MAX_LEVEL,
    max_nodes: int = MAX_NODES,
    cutoff: float = CUTOFF,
) -> Answer[ContributionResult]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    linked = await linked_documents(stored, context.storage.get_version)
    base = materialize(stored)
    method, hint = await one_method(
        context.inventory, stored.database.name, method_id, impact_method
    )
    items = demand_of(base, demand)
    value = await contributions_of(
        context.calculation,
        await treatments_of(context.inventory, base, linked),
        base,
        linked,
        method,
        items,
        by,
        top_n,
        max_level,
        max_nodes,
        cutoff,
    )
    link = result_link(context, stored, "tree", method_id, impact_method, demand=demand)
    return Answer[ContributionResult](value=value, hint=hint, view_url=link)


async def inventory_of(
    calculation: CalculationPort,
    treatments: frozenset[BackgroundRef] | None,
    base: ProductSystem,
    linked: dict[uuid.UUID, ProductSystem],
    items: list[DemandItem],
) -> tuple[InventoryResult, list[InventoryRow]]:
    """Every elementary flow of a materialised product system, with the loops holding a credit,
    the exchanges running a treatment backwards, and the residue the floor set aside."""
    found = await calculation.inventory(System.of(base, linked), items)
    result = InventoryResult(
        database=base.database,
        credit_loops=credit_loops(base),
        floor=found.floor,
        dropped=found.dropped,
        linked_credit_loops=linked_credit_loops(linked.values()),
        treatments_run_backwards=named_backwards(base, linked, treatments),
    )
    return result, found.rows


async def calculate_inventory(
    context: ServerContext,
    product_system_id: str,
    demand: list[DemandItem] | None = None,
    compartment: str | None = None,
    query: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> InventoryListing:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    linked = await linked_documents(stored, context.storage.get_version)
    base = materialize(stored)
    items = demand_of(base, demand)
    treatments = await treatments_of(context.inventory, base, linked)
    result, rows = await inventory_of(context.calculation, treatments, base, linked, items)
    page = inventory_page(rows, compartment, query, limit, page_start(cursor, limit))
    out = listing(page)
    if not page.items:
        held = {c.name for c in await context.inventory.list_compartments(base.database.name)}
        filters = {"compartment": compartment}
        words = bool(applied_filters(filters)) and bool(
            inventory_page(rows, None, query, 1, 0).items
        )
        out = listing(
            page,
            stranger("compartment", compartment, base.database.name, "compartments")
            if compartment is not None and compartment not in held
            else empty_search_hint(filters, words),
        )
    return InventoryListing(
        database=result.database,
        items=out.items,
        has_more=out.has_more,
        next_cursor=out.next_cursor,
        hint=out.hint,
        view_url=result_link(context, stored, "inventory", demand=demand),
        credit_loops=result.credit_loops,
        linked_credit_loops=result.linked_credit_loops,
        treatments_run_backwards=result.treatments_run_backwards,
        floor=result.floor,
        dropped=result.dropped,
    )


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the three calculation tools, in roster order."""
    server.tool(
        name="calculate_impact",
        annotations=READ,
        tags={COMPUTE},
        description=(
            "The characterised impact of a stored product system. Name one method_id from "
            "search_methods, or one impact_method to score all of its categories. Add "
            "variants to compare scenarios or cases against the base under one seed: each "
            "variant answers its point scores and its deltas, its score less the base's, "
            "method by method. A monte_carlo block adds uncertainty and takes at most "
            f"{MAX_ITERATIONS} draws; start_monte_carlo runs up to {MAX_DRAWS} outside the "
            "call. Under that block a "
            "pair is the base's and the variant's draws at one position, over the first "
            "draws of each up to the shorter run, since each run's own stop rule ends it, "
            "and paired_deltas holds each difference's median, interval and percentage."
        ),
        app=panel("impact"),
    )(boundary(bound(calculate_impact, context)))
    server.tool(
        name="contribution_analysis",
        annotations=READ,
        tags={COMPUTE},
        description=(
            "Decompose one impact. by='process' partitions the total over the processes "
            "that emit it, each appearing once. "
            "by='path' nests it under the demanded process along the supply chain that "
            "caused it, with elementary flows itemised at each node. by='flow' partitions "
            "it over the substances emitted or drawn, ranked by characterised score. Same "
            f"total every way. by='path' stops at max_level (default {MAX_LEVEL}) and "
            f"max_nodes (default {MAX_NODES}) and folds a branch below cutoff (default "
            f"{CUTOFF}) of the total into a remainder; by='process' and by='flow' answer the "
            f"top_n (default {TOP_N}) largest parts that reach cutoff, and cut says what the "
            "list leaves out: below, the parts under the cut-off, with their share of the total, "
            "and unlisted, the parts that reach it past top_n, with their unlisted_share. Example: "
            '{"product_system_id": '
            '"…", "by": "path", "method_id": "m_…", "max_level": 4}.'
        ),
        app=panel("contribution"),
    )(boundary(bound(contribution_analysis, context)))
    server.tool(
        name="calculate_inventory",
        annotations=READ,
        tags={COMPUTE},
        description=(
            "The life cycle inventory: every elementary flow the demand draws or emits, "
            "with the foreground process that dominates each row. Rows are ordered by "
            "compartment then name and paged; filter by compartment or by words in the "
            "flow name. contribution_analysis by='flow' ranks them by characterised score."
        ),
        app=panel("inventory"),
    )(boundary(bound(calculate_inventory, context)))
