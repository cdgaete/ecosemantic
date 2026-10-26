"""The table tools: a product system as a folder of text, written and read back."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from pathlib import Path

from fastmcp import FastMCP

from ecosemantic.errors import Invalid
from ecosemantic.mcp.calculation import demand_of
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import READ, WRITE
from ecosemantic.mcp.envelopes import Answer, Written, WrittenPath, as_uuid, bound, boundary
from ecosemantic.mcp.linking import refuse_dropped_cases
from ecosemantic.mcp.parameters import ParameterSpace, space_of
from ecosemantic.mcp.requests import answer_write
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, DemandItem, ProductSystem
from ecosemantic.ports.types import LogEntry
from ecosemantic.tables.folder import read_model, write_folder
from ecosemantic.tables.reader import apply_inputs
from ecosemantic.tables.results import ResultKey, method_label


async def apply_tables(
    context: ServerContext,
    product_system_id: uuid.UUID,
    folder: Path,
    actor: Actor,
    message: str,
) -> tuple[ProductSystem, ProductSystem, LogEntry]:
    """Store the parameter space a table folder carries over the product system it was rendered
    from, holding that system's lock from the read to the write; the system as read, as
    written, and the entry."""
    async with context.lock(product_system_id):
        stored = await context.storage.get_product_system(product_system_id)
        changed = await asyncio.to_thread(apply_inputs, stored, folder)
        await refuse_dropped_cases(context.storage, stored, changed)
        entry = await context.storage.put_product_system(changed, actor, message, source="tables")
    return stored, changed, entry


def result_key(
    system: ProductSystem,
    method_id: str | None,
    impact_method: str | None,
    demand: list[DemandItem] | None,
    variants: Sequence[str],
) -> ResultKey:
    """The key a run folder records for a calculation over a product system: the state the
    document was read at, which is its own content when nothing read it, the method it was
    asked for, the demand it resolved and the variants it compared."""
    return ResultKey(
        product_system_id=system.id,
        hash=system.hash if system.hash is not None else content_hash(system),
        method=method_label(method_id, impact_method),
        demand=demand_of(system, demand),
        variants=list(variants),
    )


async def export_tables(
    context: ServerContext, product_system_id: str, path: str
) -> Answer[WrittenPath]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    root = Path(path)
    if not root.is_dir():
        raise Invalid(f"{path!r} is not a directory")
    folder = await asyncio.to_thread(write_folder, root, stored)
    return Answer[WrittenPath](value=WrittenPath(path=str(folder), hash=content_hash(stored)))


async def import_tables(context: ServerContext, path: str) -> Written[ParameterSpace]:
    folder = Path(path)
    if not folder.is_dir():
        raise Invalid(f"{path!r} is not a directory")
    model = await asyncio.to_thread(read_model, folder)
    stored, changed, entry = await apply_tables(
        context, model.id, folder, context.acting(), "imported tables"
    )
    return await answer_write(context, space_of(changed), entry, stored, changed)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register export_tables and import_tables, in roster order."""
    server.tool(
        name="export_tables",
        annotations=READ,
        description=(
            "Write a product system as a folder of text under the given directory: model.yaml, "
            "and inputs/ holding the parameter space as CSV with a schema. import_tables reads "
            "an edited folder back."
        ),
    )(boundary(bound(export_tables, context)))
    server.tool(
        name="import_tables",
        annotations=WRITE,
        description=(
            "Read the inputs/ of a table folder back as the whole parameter space of the "
            "product system its model.yaml names. Refused when the document moved, when "
            "model.yaml was edited, and cell by cell when a value cannot be read."
        ),
    )(boundary(bound(import_tables, context)))
