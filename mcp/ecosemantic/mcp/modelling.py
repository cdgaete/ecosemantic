"""The modelling tools: the processes of a product system and the exchanges between them."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import JsonValue

from ecosemantic.compute import edits
from ecosemantic.compute.edits import (
    ExchangeClearable,
    ProcessClearable,
    add_exchange,
    add_process,
    patch_exchange,
    patch_process,
    remove_exchange,
    remove_process,
    same_unit,
)
from ecosemantic.compute.links import closure, pinned, pins
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import DELETE, WRITE
from ecosemantic.mcp.envelopes import Written, as_uuid, bound, boundary, serialised
from ecosemantic.mcp.requests import answer_write
from ecosemantic.model.entities import (
    Exchange,
    ExchangeType,
    Process,
    ProductSystem,
    Uncertainty,
    state_of,
)
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ExchangeInput, SystemRef


async def create_process(
    context: ServerContext,
    product_system_id: str,
    code: str,
    name: str,
    unit: str,
    reference_product: str,
    location: str = "GLO",
    comment: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
    production_amount: float = 1.0,
) -> Written[Process]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed, process = add_process(
        stored,
        code=code,
        name=name,
        unit=unit,
        reference_product=reference_product,
        location=location,
        comment=comment,
        metadata=metadata,
        production_amount=production_amount,
    )
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"created process {code}"
    )
    return await answer_write(context, process, entry, stored, changed)


async def update_process(
    context: ServerContext,
    product_system_id: str,
    code: str,
    name: str | None = None,
    unit: str | None = None,
    location: str | None = None,
    reference_product: str | None = None,
    comment: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
    clear: list[ProcessClearable] | None = None,
) -> Written[Process]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed, process = patch_process(
        stored,
        code,
        name=name,
        location=location,
        reference_product=reference_product,
        comment=comment,
        metadata=metadata,
        unit=unit,
        clear=clear or (),
    )
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"updated process {code}"
    )
    return await answer_write(context, process, entry, stored, changed)


async def delete_process(context: ServerContext, product_system_id: str, code: str) -> Written[str]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed = remove_process(stored, code)
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"deleted process {code}"
    )
    return await answer_write(context, code, entry, stored, changed)


async def _resolved(
    context: ServerContext, input: ExchangeInput | None, unit: str | None, name: str | None
) -> tuple[str | None, str | None]:
    """The unit and name of a background or elementary input, checked against its provider."""
    if isinstance(input, BackgroundRef):
        provider = await context.inventory.get_process(input)
        unit = same_unit(unit, provider.unit, provider.name)
        return unit, name if name is not None else provider.reference_product
    if isinstance(input, ElementaryFlowRef):
        flow = await context.inventory.get_elementary_flow(input)
        unit = same_unit(unit, flow.unit, flow.name)
        return unit, name if name is not None else flow.name
    return unit, name


async def _pinned_link(context: ServerContext, ref: SystemRef) -> tuple[SystemRef, ProductSystem]:
    """The link pinned to the hash it names, or to the linked system's current hash, with
    the linked system as it stood there."""
    current = await context.storage.get_product_system(ref.product_system_id)
    pin = ref if ref.at_hash is not None else ref.model_copy(update={"at_hash": current.hash})
    return pin, await context.storage.get_version(pin.product_system_id, pinned(pin))


async def create_exchange(
    context: ServerContext,
    product_system_id: str,
    code: str,
    type: ExchangeType,
    amount: float | None = None,
    formula: str | None = None,
    unit: str | None = None,
    name: str | None = None,
    input: ExchangeInput | None = None,
    comment: str | None = None,
    uncertainty: Uncertainty | None = None,
) -> Written[Exchange]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    linked = None
    if isinstance(input, SystemRef):
        input, linked = await _pinned_link(context, input)
    unit, name = await _resolved(context, input, unit, name)
    changed, exchange = add_exchange(
        stored,
        code,
        type=type,
        input=input,
        amount=amount,
        formula=formula,
        unit=unit,
        name=name,
        comment=comment,
        uncertainty=uncertainty,
        linked=linked,
    )
    await closure(changed, context.storage.get_version)
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"created exchange {exchange.name} on {code}"
    )
    return await answer_write(context, exchange, entry, stored, changed)


async def update_exchange(
    context: ServerContext,
    product_system_id: str,
    exchange_id: str,
    amount: float | None = None,
    formula: str | None = None,
    name: str | None = None,
    unit: str | None = None,
    comment: str | None = None,
    uncertainty: Uncertainty | None = None,
    clear: list[ExchangeClearable] | None = None,
) -> Written[Exchange]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    _, current = stored.exchange(as_uuid(exchange_id))
    if unit is not None:
        unit, _ = await _resolved(context, current.input, unit, None)
    changed, exchange = patch_exchange(
        stored,
        current.id,
        amount=amount,
        formula=formula,
        name=name,
        unit=unit,
        comment=comment,
        uncertainty=uncertainty,
        clear=clear or (),
    )
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"updated exchange {changed.exchange_named(exchange.id)}"
    )
    return await answer_write(context, exchange, entry, stored, changed)


async def delete_exchange(
    context: ServerContext, product_system_id: str, exchange_id: str
) -> Written[str]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    named = stored.exchange_named(as_uuid(exchange_id))
    changed = remove_exchange(stored, as_uuid(exchange_id))
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"deleted exchange {named}"
    )
    return await answer_write(context, exchange_id, entry, stored, changed)


async def rebase_links(
    context: ServerContext, product_system_id: str, linked: str | None = None
) -> Written[list[SystemRef]]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    current = {
        ref.product_system_id: state_of(
            await context.storage.get_product_system(ref.product_system_id)
        )
        for ref in pins(stored)
    }
    changed, moved = edits.rebase_links(
        stored, current, as_uuid(linked) if linked is not None else None
    )
    await closure(changed, context.storage.get_version)
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"rebased the links of {changed.name}"
    )
    return await answer_write(context, moved, entry, stored, changed)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register the process tools, then the exchange tools, in roster order."""
    server.tool(
        name="create_process",
        annotations=WRITE,
        description=(
            "A foreground process in a product system, with its production exchange: "
            "production_amount of the reference product in the process unit. An "
            "alternative supplier is an ordinary process whose amount a parameter sets."
        ),
    )(boundary(serialised(context.lock)(bound(create_process, context))))
    server.tool(
        name="update_process",
        annotations=WRITE,
        description=(
            "Patch a process's name, location, reference product, comment or metadata; "
            "metadata keys given replace, others stay. The unit changes only while nothing "
            "consumes the process. The code is fixed."
        ),
    )(boundary(serialised(context.lock)(bound(update_process, context))))
    server.tool(
        name="delete_process",
        annotations=DELETE,
        description=(
            "Remove a process and its exchanges. Refused while another process consumes it "
            "or a scenario references it; delete those first."
        ),
    )(boundary(serialised(context.lock)(bound(delete_process, context))))
    server.tool(
        name="create_exchange",
        annotations=WRITE,
        description=(
            "An exchange on the process with this code: production (no input), product (a "
            "background process by the ref a search hit carries, or a foreground process by "
            "code) or elementary (a flow by the ref a search hit carries). Give "
            "amount or formula; a formula names parameters set_parameters has already "
            "written. Unit and name default to the provider's and must match its unit. A "
            'product input may instead link another product system, {"kind": "system", '
            '"product_system_id": ...}: one unit of its reference process, pinned to its '
            "current state unless at_hash names another, under its base values unless case "
            "names one of its cases. A link that closes a cycle, or that reaches one system "
            "under two cases, is refused. input and uncertainty are JSON objects, never strings "
            'holding JSON: {"kind": "foreground", "code": "mine"}, {"kind": "background", '
            '"database": ..., "id": ...}, {"type": "lognormal", "params": {"loc": ..., '
            '"scale": ...}}.'
        ),
    )(boundary(serialised(context.lock)(bound(create_exchange, context))))
    server.tool(
        name="update_exchange",
        annotations=WRITE,
        description=(
            "Patch an exchange's amount, formula, name, unit, comment or uncertainty. An "
            "amount on an exchange with a formula needs 'formula' in clear. Type and input "
            "are fixed; delete and create to change them."
        ),
    )(boundary(serialised(context.lock)(bound(update_exchange, context))))
    server.tool(
        name="delete_exchange",
        annotations=DELETE,
        description="Remove an exchange. Refused while a scenario overrides it; delete that first.",
    )(boundary(serialised(context.lock)(bound(delete_exchange, context))))
    server.tool(
        name="rebase_links",
        annotations=WRITE,
        description=(
            "Move the links of a product system to the current state of the systems they link, "
            "or only its links to one of them. A link names the state it was made against, and "
            "a linked system's later edits reach this system through this write alone."
        ),
    )(boundary(serialised(context.lock)(bound(rebase_links, context))))
