"""The parameter tools: the parameter space of a product system and its scenarios."""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel

from ecosemantic.compute import edits
from ecosemantic.compute.edits import (
    add_scenario,
    remove_scenario,
    set_parameter_space,
)
from ecosemantic.compute.parameters import CaseMatrix, case_matrix, evaluate
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.effects import DELETE, READ, WRITE
from ecosemantic.mcp.envelopes import Answer, Written, as_uuid, bound, boundary, serialised
from ecosemantic.mcp.linking import refuse_dropped_cases
from ecosemantic.mcp.requests import answer_write
from ecosemantic.model.entities import Case, Override, Parameter, ProductSystem, Scenario


class ParameterSpace(BaseModel):
    """A product system's parameters and the cases over them, as stored and as a table, and
    the value every parameter evaluates to, a derived one's beside its formula."""

    parameters: list[Parameter]
    values: dict[str, float]
    cases: list[Case]
    matrix: CaseMatrix


def space_of(system: ProductSystem) -> ParameterSpace:
    """The parameter space of a document, with the cases rendered as a table."""
    values, _ = evaluate(system.parameters, {})
    return ParameterSpace(
        parameters=system.parameters,
        values=values,
        cases=system.cases,
        matrix=case_matrix(system.cases),
    )


async def get_parameters(
    context: ServerContext, product_system_id: str, content_hash: str | None = None
) -> Answer[ParameterSpace]:
    system_id = as_uuid(product_system_id)
    stored = (
        await context.storage.get_product_system(system_id)
        if content_hash is None
        else await context.storage.get_version(system_id, content_hash)
    )
    return Answer[ParameterSpace](value=space_of(stored))


async def set_parameters(
    context: ServerContext,
    product_system_id: str,
    parameters: list[Parameter] | None = None,
    cases: list[Case] | None = None,
    delete_parameters: list[str] | None = None,
    delete_cases: list[str] | None = None,
) -> Written[ParameterSpace]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed = set_parameter_space(
        stored,
        parameters=parameters or (),
        cases=cases or (),
        delete_parameters=delete_parameters or (),
        delete_cases=delete_cases or (),
    )
    await refuse_dropped_cases(context.storage, stored, changed)
    entry = await context.storage.put_product_system(changed, context.acting(), "set parameters")
    space = space_of(changed)
    return await answer_write(context, space, entry, stored, changed)


async def create_scenario(
    context: ServerContext,
    product_system_id: str,
    name: str,
    overrides: list[Override],
    description: str = "",
) -> Written[Scenario]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed, scenario = add_scenario(
        stored, name=name, description=description, overrides=overrides
    )
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"created scenario {name}"
    )
    return await answer_write(context, scenario, entry, stored, changed)


async def delete_scenario(
    context: ServerContext, product_system_id: str, name: str
) -> Written[str]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed = remove_scenario(stored, name)
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"deleted scenario {name}"
    )
    return await answer_write(context, name, entry, stored, changed)


async def rebase_scenario(
    context: ServerContext, product_system_id: str, name: str
) -> Written[Scenario]:
    stored = await context.storage.get_product_system(as_uuid(product_system_id))
    changed, scenario = edits.rebase_scenario(stored, name)
    entry = await context.storage.put_product_system(
        changed, context.acting(), f"rebased scenario {name}"
    )
    return await answer_write(context, scenario, entry, stored, changed)


def register(server: FastMCP, context: ServerContext) -> None:
    """Register get_parameters and set_parameters, then the scenario tools, in roster order."""
    server.tool(
        name="get_parameters",
        annotations=READ,
        description=(
            "The parameter space of a product system: literal and formula parameters, the "
            "cases over them, and the cases as a table. Give a content_hash to read the "
            "space as it was at that version. set_parameters writes it, and calculate_impact "
            "takes a case as a variant."
        ),
    )(boundary(bound(get_parameters, context)))
    server.tool(
        name="set_parameters",
        annotations=WRITE,
        description=(
            "Write the parameter space in one call: parameters replaced whole by name, one "
            "of value or formula each; cases replaced whole by name, each a set of values "
            "over literal parameters; and names to delete. A parameter a formula or a case "
            "uses cannot be deleted, nor can a case another system's link names. Exchange "
            "formulas are re-evaluated after the write."
        ),
    )(boundary(serialised(context.lock)(bound(set_parameters, context))))
    server.tool(
        name="create_scenario",
        annotations=WRITE,
        description=(
            "A named what-if over the product system: exchange overrides (exchange_id with "
            "one of amount, multiplier or input) and parameter overrides (name, value). It is "
            "applied once to prove it and pinned to the base hash, the content hash without "
            "the cases and the database build: a case written or deleted moves no scenario, "
            "and base_hash is never the system's hash. Any later edit leaves the scenario "
            "behind until rebase_scenario moves it. An input swap applies to a product "
            "exchange and names a background dataset or a foreground process, never a linked "
            "system. A scenario is immutable; delete and create to change it. calculate_impact "
            'takes it as a variant. Example: {"product_system_id": "…", "name": "half power", '
            '"overrides": [{"kind": "exchange", "exchange_id": "…", "multiplier": 0.5}]}.'
        ),
    )(boundary(serialised(context.lock)(bound(create_scenario, context))))
    server.tool(
        name="delete_scenario",
        annotations=DELETE,
        description="Remove a scenario. The product system's data is untouched.",
    )(boundary(serialised(context.lock)(bound(delete_scenario, context))))
    server.tool(
        name="rebase_scenario",
        annotations=WRITE,
        description=(
            "Re-pin a scenario to the product system's base hash after the base changed, "
            "proving its overrides still apply. calculate_impact refuses a stale scenario."
        ),
    )(boundary(serialised(context.lock)(bound(rebase_scenario, context))))
