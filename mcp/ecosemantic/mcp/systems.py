"""The product system tools: list, read, create, patch, delete, validate, export, import, log."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import FastMCP

from ecosemantic.compute import edits
from ecosemantic.compute.edits import (
    background_references,
    new_product_system,
    patch_product_system,
)
from ecosemantic.compute.links import held_pins, pinned_documents, pinning
from ecosemantic.compute.overrides import apply_variant
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.mcp.calculation import refuse_stale
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import DELETE, READ, WRITE
from ecosemantic.mcp.envelopes import (
    Answer,
    Listing,
    Written,
    WrittenPath,
    as_uuid,
    bound,
    boundary,
    listing,
    serialised,
)
from ecosemantic.mcp.linking import others
from ecosemantic.mcp.requests import answer_write, open_requests
from ecosemantic.mcp.treatments import treatments_in
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.validation import ValidationReport, validate
from ecosemantic.package.model_package import export_model_package, import_model_package, stated_at
from ecosemantic.ports.types import (
    LogEntry,
    Page,
    ProductSystemSummary,
    Summarised,
    offset_cursor,
)

LOG_PAGE = 10


class SystemCard(ProductSystemSummary):
    """A summary with the link to its page, when the server serves one."""

    view_url: str | None = None

    @classmethod
    def of(
        cls, system: Summarised, stored_hash: str | None = None, view_url: str | None = None
    ) -> SystemCard:
        """The listing's view of a document at the stored state a hash names, with its link."""
        return cls(**ProductSystemSummary.of(system, stored_hash).model_dump(), view_url=view_url)


class SystemRead(Answer[ProductSystem]):
    """A product system whole, with the count of open requests on it."""

    open_requests: int = 0


async def list_product_systems(context: ServerContext) -> Answer[list[SystemCard]]:
    summaries = await context.storage.list_product_systems()
    return Answer[list[SystemCard]](
        value=[SystemCard(**s.model_dump(), view_url=context.deep_link(s.id)) for s in summaries]
    )


async def get_product_system(
    context: ServerContext, product_system_id: str, variant: str | None = None
) -> SystemRead:
    system = await context.storage.get_product_system(as_uuid(product_system_id))
    if variant is not None:
        await refuse_stale(context, system, [variant])
    return SystemRead(
        value=system if variant is None else apply_variant(system, variant),
        open_requests=await open_requests(context.storage, system.id),
        view_url=context.deep_link(system.id),
    )


async def create_product_system(
    context: ServerContext, name: str, database: str, description: str = "", notes: str = ""
) -> Written[SystemCard]:
    found = await context.inventory.get_database(database)
    system = new_product_system(name, found, description, notes)
    entry = await context.storage.put_product_system(
        system, context.acting(), f"created product system {name}"
    )
    card = SystemCard.of(system, entry.result_hash, context.deep_link(system.id))
    return await answer_write(context, card, entry, None, system)


async def update_product_system(
    context: ServerContext,
    product_system_id: str,
    name: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    reference_process: str | None = None,
) -> Written[SystemCard]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed = patch_product_system(
        stored,
        name=name,
        description=description,
        notes=notes,
        reference_process=reference_process,
    )
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"updated product system {changed.name}"
    )
    card = SystemCard.of(changed, entry.result_hash, context.deep_link(changed.id))
    return await answer_write(context, card, entry, stored, changed)


async def rebase_database(
    context: ServerContext, product_system_id: str, database: str | None = None
) -> Written[SystemCard]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    installed = await context.inventory.get_database(database or stored.database.name)
    moved = edits.rebase_database(stored, installed)
    placed = background_references(moved)
    lacking = set(await context.inventory.missing([ref for _, _, ref in placed]))
    if lacking:
        named = [f"{where} · {label} · {ref.id}" for where, label, ref in placed if ref in lacking]
        raise NotFound(
            f"{installed.name!r} lacks {len(named)} references {stored.name} names: "
            + "; ".join(named)
        )
    leaving = stored.database.fingerprint
    left = "no build" if leaving is None else f"build {leaving[:12]}"
    entry = await context.storage.put_product_system(
        moved,
        context.acting(),
        f"moved product system {moved.name} from {stored.database.name!r} at {left} to "
        f"{installed.name!r} at build {str(installed.fingerprint)[:12]}",
    )
    card = SystemCard.of(moved, entry.result_hash, context.deep_link(moved.id))
    return await answer_write(context, card, entry, stored, moved)


async def delete_product_system(
    context: ServerContext, product_system_id: str
) -> Answer[SystemCard]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    linking = pinning(stored.id, await others(context.storage, stored.id))
    if linking:
        raise Invalid(f"{stored.name} is linked by {linking}; delete their links first")
    await context.runs.delete_runs(stored.id)
    await context.storage.delete_product_system(stored.id, context.acting())
    return Answer[SystemCard](value=SystemCard.of(stored))


async def validate_product_system(
    context: ServerContext, product_system_id: str, target: str | None = None
) -> Answer[ValidationReport]:
    system = await context.storage.get_product_system(as_uuid(product_system_id))
    installed = await context.inventory.get_database(system.database.name)
    pins = await held_pins(system, context.storage)
    documents = [system, *(p.document for p in pins if p.document is not None)]
    treatments = await treatments_in(context.inventory, documents)
    return Answer[ValidationReport](value=validate(system, target, pins, installed, treatments))


async def export_product_system(
    context: ServerContext, product_system_id: str, path: str
) -> Answer[WrittenPath]:
    system = await context.storage.get_product_system(as_uuid(product_system_id))
    destination = Path(path)
    if not destination.parent.is_dir():
        raise Invalid(f"{str(destination.parent)!r} does not exist")
    linked = await pinned_documents(system, context.storage.get_version)
    at = stated_at(system, await context.storage.log(system.id))
    entry = await asyncio.to_thread(
        export_model_package,
        system,
        destination,
        context.acting(),
        context.resolver,
        linked=linked,
        at=at,
    )
    return Answer[WrittenPath](value=WrittenPath(path=str(destination), hash=entry.result_hash))


async def import_product_system(context: ServerContext, path: str) -> Written[SystemCard]:
    system, entry = await import_model_package(Path(path), context.storage, context.acting())
    card = SystemCard.of(system, entry.result_hash, context.deep_link(system.id))
    return await answer_write(context, card, entry, None, system)


async def get_product_system_log(
    context: ServerContext, product_system_id: str, limit: int = LOG_PAGE, cursor: str | None = None
) -> Listing[LogEntry]:
    if limit < 1:
        raise Invalid("limit is at least 1")
    entries = await context.storage.log(as_uuid(product_system_id))
    start = offset_cursor(cursor)
    page = Page[LogEntry].at_offset(
        entries[start : start + limit], start + limit < len(entries), start, limit
    )
    return listing(page)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the product system tools, in roster order."""
    server.tool(
        name="list_product_systems",
        annotations=READ,
        description=(
            "Every stored product system, with its database and its content hash: the hash "
            "over its processes, exchanges, parameters, cases, reference process and database "
            "build, which leaves out its name, description, scenarios and layout."
        ),
    )(boundary(bound(list_product_systems, context)))
    server.tool(
        name="get_product_system",
        annotations=READ,
        description=(
            "One product system whole: its processes, their exchanges, its parameters, "
            "cases and scenarios. There is no separate tool for the parts. Name a case or a "
            "scenario as variant to read the document with it applied and every formula "
            "resolved; a scenario behind the base is refused as calculate_impact refuses it. "
            "A scenario's base_hash is the base pin, the content hash without the cases and "
            "the database build, so it is never the system's hash."
        ),
    )(boundary(bound(get_product_system, context)))
    server.tool(
        name="create_product_system",
        annotations=WRITE,
        description=(
            "An empty product system on one background database this server serves. "
            "Model it with create_process and create_exchange."
        ),
    )(boundary(bound(create_product_system, context)))
    server.tool(
        name="update_product_system",
        annotations=WRITE,
        description=(
            "Patch a product system's name, description, notes or reference process, the base "
            "process whose product, one unit of it, is the functional unit. Its database is fixed."
        ),
    )(boundary(serialised(context.lock)(bound(update_product_system, context))))
    server.tool(
        name="rebase_database",
        annotations=WRITE,
        description=(
            "Move a product system onto an installed database: without database, onto the "
            "build of its own database this server holds; with database, onto that one, every "
            "background and elementary-flow reference of its exchanges and scenario overrides "
            "renamed to it, each id resolved there first, and nothing written while any does "
            "not resolve. One log entry names the database and build it leaves and the ones it "
            "takes. A calculation refuses a system on another build, or on none; this write "
            "accepts that its numbers may change. It moves the content hash, so the answer's "
            "consequences name the scenarios that need rebase_scenario and the systems whose "
            'links need rebase_links. Example: {"product_system_id": "…", "database": '
            '"ecoinvent-3.12-cutoff"}.'
        ),
    )(boundary(serialised(context.lock)(bound(rebase_database, context))))
    server.tool(
        name="delete_product_system",
        annotations=DELETE,
        description=(
            "Remove a product system, its log and its runs. Nothing survives; "
            "export_product_system first to keep a copy. Refused while another system links "
            "it or one of its runs is open."
        ),
    )(boundary(serialised(context.lock)(bound(delete_product_system, context))))
    server.tool(
        name="validate_product_system",
        annotations=READ,
        description=(
            "Run every structural case against a product system, against its reference "
            "process unless a target is named, and report each one with what to fix, the "
            "database build it names against the installed one among them. The cases advise: "
            "a calculation does not wait for them to pass, and refuses only a build other "
            "than the installed one."
        ),
    )(boundary(bound(validate_product_system, context)))
    server.tool(
        name="export_product_system",
        annotations=READ,
        description=(
            "Write a product system as a model package at the given path: one zip "
            "holding the openLCA JSON-LD layout, which openLCA opens directly, and the "
            "ecosemantic/ folder with what openLCA has no field for: the scenarios, the pins, "
            "the identities, the state as a version snapshot, and ecosemantic/log.jsonl, whose "
            "one entry records the export; the stored change log stays in the store. "
            "Background datasets travel as references, never as records. Example: "
            '{"product_system_id": "…", "path": "/home/person/widget.zip"}.'
        ),
    )(boundary(bound(export_product_system, context)))
    server.tool(
        name="import_product_system",
        annotations=WRITE,
        description=(
            "Read a model package at the given path and store the product system "
            "it carries as a new one. An id already stored is refused."
        ),
    )(boundary(bound(import_product_system, context)))
    server.tool(
        name="get_product_system_log",
        annotations=READ,
        description=(
            "The append-only change log of a product system, oldest entry first, a page of "
            "limit entries at a time; pass next_cursor to continue."
        ),
    )(boundary(bound(get_product_system_log, context)))
