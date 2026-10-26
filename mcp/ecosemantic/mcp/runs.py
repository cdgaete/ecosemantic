"""The run tools: a Monte Carlo that outlives its request, started, watched and stopped."""

from __future__ import annotations

import asyncio

from fastmcp import FastMCP

from ecosemantic.compute.links import linked_documents
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import RunOpen
from ecosemantic.mcp.calculation import demand_of, methods_for
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import COMPUTE, READ, WRITE
from ecosemantic.mcp.envelopes import Answer, as_uuid, bound, boundary
from ecosemantic.mcp.treatments import backwards_in
from ecosemantic.mcp.watcher import reap, watch
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import DemandItem
from ecosemantic.ports.types import MonteCarloConfig, Run, RunDraft, RunPatch


def simulation_link(context: ServerContext, run: Run) -> str | None:
    """The simulation page that shows a run."""
    return context.page_link(run.product_system_id, f"/simulations/{run.id}")


async def start_monte_carlo(
    context: ServerContext,
    product_system_id: str,
    method_id: str | None = None,
    impact_method: str | None = None,
    demand: list[DemandItem] | None = None,
    monte_carlo: MonteCarloConfig | None = None,
) -> Answer[Run]:
    system_id = as_uuid(product_system_id)
    async with context.runs.slot():
        for existing in await context.runs.list_runs():
            settled = await reap(context.runs, context.launcher, existing)
            if settled.open:
                raise RunOpen(settled.id, settled.product_system_id, settled.status)
        stored = await context.storage.get_product_system(system_id)
        linked = await linked_documents(stored, context.storage.get_version)
        methods, _ = await methods_for(
            context.inventory, stored.database.name, method_id, impact_method
        )
        posted = await context.runs.post_run(
            RunDraft(
                product_system_id=system_id,
                at_hash=content_hash(stored),
                demand=demand_of(stored, demand),
                methods=methods,
                config=monte_carlo or MonteCarloConfig(),
                treatments_run_backwards=await backwards_in(
                    context.inventory, materialize(stored), linked
                ),
            )
        )
        pid = await asyncio.to_thread(context.launcher.start, posted.id)
        watched = await context.runs.update_run(posted.id, RunPatch(pid=pid))
        context.keep_watching(watch(context.events, context.runs, context.launcher, posted.id))
        return Answer[Run](value=watched, view_url=simulation_link(context, watched))


async def get_run(context: ServerContext, run_id: str) -> Answer[Run]:
    run = await reap(context.runs, context.launcher, await context.runs.get_run(as_uuid(run_id)))
    return Answer[Run](value=run, view_url=simulation_link(context, run))


async def list_runs(
    context: ServerContext, product_system_id: str | None = None
) -> Answer[list[Run]]:
    found = await context.runs.list_runs(
        as_uuid(product_system_id) if product_system_id is not None else None
    )
    return Answer[list[Run]](
        value=[await reap(context.runs, context.launcher, run) for run in found]
    )


async def cancel_run(context: ServerContext, run_id: str) -> Answer[Run]:
    run = await context.runs.cancel_run(as_uuid(run_id))
    return Answer[Run](value=run, view_url=simulation_link(context, run))


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the four run tools, in roster order."""
    server.tool(
        name="start_monte_carlo",
        annotations=WRITE,
        tags={COMPUTE},
        description=(
            "Start a Monte Carlo that outlives this call, pinned to the product system's "
            "current hash, and answer the run. get_run polls it, cancel_run stops it. One "
            "run at a time: a second start is refused while one is open. calculate_impact "
            "takes a monte_carlo block instead when the iterations fit in one call."
        ),
    )(boundary(bound(start_monte_carlo, context)))
    server.tool(
        name="get_run",
        annotations=READ,
        description=(
            "One run: its status, how many iterations it has taken, and its result once it "
            "is done. A run whose worker is gone answers as failed."
        ),
    )(boundary(bound(get_run, context)))
    server.tool(
        name="list_runs",
        annotations=READ,
        description=(
            "The runs of a product system, newest first, or every run without one. "
            "start_monte_carlo makes them."
        ),
    )(boundary(bound(list_runs, context)))
    server.tool(
        name="cancel_run",
        annotations=WRITE,
        description=(
            "Ask a run to stop. It finishes the iteration it is on and keeps the samples it "
            "has, so the answer is cancelled rather than lost. A finished run is refused."
        ),
    )(boundary(bound(cancel_run, context)))
