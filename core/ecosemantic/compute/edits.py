"""Edits to a product system as pure functions: each takes a document and returns a new one."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import JsonValue, ValidationError

from ecosemantic.compute.links import pins
from ecosemantic.compute.overrides import apply_scenario
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Conflict, Invalid
from ecosemantic.model.canonical import base_pin
from ecosemantic.model.entities import (
    Case,
    Exchange,
    ExchangeOverride,
    ExchangeType,
    Override,
    Parameter,
    Process,
    ProductSystem,
    Scenario,
    Uncertainty,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    Database,
    ElementaryFlowRef,
    ExchangeInput,
    ForegroundRef,
    SystemRef,
)

ProcessClearable = Literal["comment"]
ExchangeClearable = Literal["formula", "comment", "uncertainty"]


def invalid(error: ValidationError) -> Invalid:
    """The model's validation failure as the typed error a tool renders."""
    detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
    return Invalid(detail)


def new_product_system(
    name: str, database: Database, description: str, notes: str
) -> ProductSystem:
    """An empty document on one database, with a fresh id and no hash."""
    return ProductSystem(
        id=uuid.uuid4(), name=name, description=description, notes=notes, database=database
    )


def patch_product_system(
    system: ProductSystem,
    name: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    reference_process: str | None = None,
) -> ProductSystem:
    """The document with the given fields replaced; at least one must be given, and a reference
    process must name a process of the document."""
    fields = {
        "name": name,
        "description": description,
        "notes": notes,
        "reference_process": reference_process,
    }
    given = {key: value for key, value in fields.items() if value is not None}
    if not given:
        raise Invalid("name at least one of name, description, notes or reference_process")
    try:
        return ProductSystem.model_validate({**system.model_dump(), **given})
    except ValidationError as error:
        raise invalid(error) from error


Placed = tuple[str, str, BackgroundRef | ElementaryFlowRef]


def background_references(system: ProductSystem) -> list[Placed]:
    """Every background and elementary-flow reference of the document, each with where it
    stands: the process code and the exchange name, or the scenario and the exchange id its
    override names."""
    found: list[Placed] = []
    for process in system.processes:
        for exchange in process.exchanges:
            if isinstance(exchange.input, BackgroundRef | ElementaryFlowRef):
                found.append((process.code, exchange.name, exchange.input))
    for scenario in system.scenarios:
        for override in scenario.overrides:
            if isinstance(override, ExchangeOverride) and isinstance(override.input, BackgroundRef):
                found.append(
                    (f"scenario {scenario.name}", str(override.exchange_id), override.input)
                )
    return found


def _onto(ref: ExchangeInput | None, installed: Database) -> ExchangeInput | None:
    if isinstance(ref, BackgroundRef):
        return BackgroundRef(database=installed.name, id=ref.id)
    if isinstance(ref, ElementaryFlowRef):
        return ElementaryFlowRef(database=installed.elementary_flows, id=ref.id)
    return ref


def rebase_database(system: ProductSystem, installed: Database) -> ProductSystem:
    """The document on an installed database: its record becomes the installed one, and every
    background and elementary-flow reference of its exchanges and its scenario overrides names
    that database and its elementary flows. Invalid for the record the document holds already."""
    if system.database == installed:
        raise Invalid(
            f"{system.name} is on build {str(installed.fingerprint)[:12]} of "
            f"{installed.name!r} already"
        )
    moved = system.model_copy(deep=True, update={"database": installed})
    for process in moved.processes:
        for exchange in process.exchanges:
            exchange.input = _onto(exchange.input, installed)
    for scenario in moved.scenarios:
        for override in scenario.overrides:
            if isinstance(override, ExchangeOverride) and override.input is not None:
                override.input = _onto(override.input, installed)
    return moved


def _references(ref: ExchangeInput | None, code: str) -> bool:
    return isinstance(ref, ForegroundRef) and ref.code == code


def consumers_of(system: ProductSystem, code: str) -> list[str]:
    """Codes of the processes whose exchanges reference this code."""
    return sorted(
        a.code for a in system.processes if any(_references(e.input, code) for e in a.exchanges)
    )


def _swapping_scenarios(system: ProductSystem, code: str) -> list[str]:
    return sorted(
        s.name
        for s in system.scenarios
        if any(isinstance(o, ExchangeOverride) and _references(o.input, code) for o in s.overrides)
    )


def _overriding_scenarios(system: ProductSystem, exchange_ids: set[uuid.UUID]) -> list[str]:
    return sorted(
        s.name
        for s in system.scenarios
        if any(
            isinstance(o, ExchangeOverride) and o.exchange_id in exchange_ids for o in s.overrides
        )
    )


def add_process(
    system: ProductSystem,
    *,
    code: str,
    name: str,
    unit: str,
    reference_product: str,
    location: str = "GLO",
    comment: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
    production_amount: float = 1.0,
) -> tuple[ProductSystem, Process]:
    """The document with a new process and its production exchange; the code must be free."""
    if any(a.code == code for a in system.processes):
        raise Conflict(f"process {code!r} already exists in {system.name!r}")
    try:
        process = Process(
            id=uuid.uuid4(),
            code=code,
            name=name,
            unit=unit,
            location=location,
            reference_product=reference_product,
            comment=comment,
            metadata=metadata,
            exchanges=[
                Exchange(
                    id=uuid.uuid4(),
                    type="production",
                    name=reference_product,
                    amount=production_amount,
                    unit=unit,
                )
            ],
        )
    except ValidationError as error:
        raise invalid(error) from error
    out = system.model_copy(deep=True)
    out.processes.append(process)
    return out, process


def patch_process(
    system: ProductSystem,
    code: str,
    *,
    name: str | None = None,
    location: str | None = None,
    reference_product: str | None = None,
    comment: str | None = None,
    metadata: dict[str, JsonValue] | None = None,
    unit: str | None = None,
    clear: Sequence[ProcessClearable] = (),
) -> tuple[ProductSystem, Process]:
    """The document with a process's fields replaced; the unit only while nothing consumes it."""
    fields = {
        "name": name,
        "location": location,
        "reference_product": reference_product,
        "comment": comment,
    }
    given = {key: value for key, value in fields.items() if value is not None}
    if not given and metadata is None and unit is None and not clear:
        raise Invalid("name at least one field to change")
    out = system.model_copy(deep=True)
    process = out.process(code)
    for key, value in given.items():
        setattr(process, key, value)
    if metadata is not None:
        process.metadata = {**process.metadata, **metadata}
    if "comment" in clear:
        process.comment = None
    if unit is not None:
        consumers = consumers_of(out, code)
        if consumers:
            raise Invalid(f"{code!r} is consumed by {consumers}; its unit cannot change")
        process.unit = unit
        for exchange in process.exchanges:
            if exchange.type == "production":
                exchange.unit = unit
    return out, process


def remove_process(system: ProductSystem, code: str) -> ProductSystem:
    """The document without the process; refused while a process or a scenario depends on it."""
    out = system.model_copy(deep=True)
    process = out.process(code)
    if out.reference_process == code:
        raise Invalid(f"{code!r} is the reference process of {out.name}; set another first")
    consumers = consumers_of(out, code)
    if consumers:
        raise Invalid(f"{code!r} is consumed by {consumers}; delete those exchanges first")
    scenarios = sorted(
        set(_swapping_scenarios(out, code))
        | set(_overriding_scenarios(out, {e.id for e in process.exchanges}))
    )
    if scenarios:
        raise Invalid(f"scenarios {scenarios} reference {code!r}; delete them first")
    out.processes = [a for a in out.processes if a.code != code]
    return out


def same_unit(given: str | None, expected: str, owner: str) -> str:
    """The provider's unit, which a given unit must equal."""
    if given is not None and given != expected:
        raise Invalid(f"{owner!r} is in {expected!r}, not {given!r}")
    return expected


def _link(
    system: ProductSystem,
    ref: SystemRef,
    linked: ProductSystem | None,
    unit: str | None,
    name: str | None,
) -> tuple[str, str]:
    """The unit and name of a link to another system's functional unit, checked against that
    system as it stood at the pin."""
    if ref.product_system_id == system.id:
        raise Invalid(f"{system.name} cannot link itself")
    if linked is None or linked.id != ref.product_system_id or linked.hash != ref.at_hash:
        raise Invalid("a link needs the linked system as it stood at the pin")
    if linked.database.name != system.database.name:
        raise Invalid(f"{linked.name} is on {linked.database.name!r}, not {system.database.name!r}")
    if linked.reference_process is None:
        raise Invalid(
            f"{linked.name} has no reference process to link; set one with update_product_system"
        )
    if ref.case is not None:
        linked.case(ref.case)
    target = linked.process(linked.reference_process)
    return (
        same_unit(unit, target.unit, linked.name),
        name if name is not None else target.reference_product,
    )


def _materialised(system: ProductSystem, exchange_id: uuid.UUID) -> tuple[ProductSystem, Exchange]:
    out = materialize(system)
    _, exchange = out.exchange(exchange_id)
    return out, exchange


def add_exchange(
    system: ProductSystem,
    code: str,
    *,
    type: ExchangeType,
    input: ExchangeInput | None = None,
    amount: float | None = None,
    formula: str | None = None,
    unit: str | None = None,
    name: str | None = None,
    comment: str | None = None,
    uncertainty: Uncertainty | None = None,
    linked: ProductSystem | None = None,
) -> tuple[ProductSystem, Exchange]:
    """The document with a new exchange on the process, its amount materialised. A link takes
    `linked`, the linked system as it stood at the pin."""
    if (amount is None) == (formula is None):
        raise Invalid("give exactly one of amount and formula")
    out = system.model_copy(deep=True)
    process = out.process(code)
    if type == "production":
        if input is not None:
            raise Invalid("a production exchange takes no input")
        if any(e.type == "production" for e in process.exchanges):
            raise Invalid(f"{code!r} already has a production exchange")
        unit = same_unit(unit, process.unit, code)
        name = name if name is not None else process.reference_product
    elif type == "product":
        if isinstance(input, ForegroundRef):
            target = out.process(input.code)
            unit = same_unit(unit, target.unit, target.code)
            name = name if name is not None else target.reference_product
        elif isinstance(input, SystemRef):
            unit, name = _link(out, input, linked, unit, name)
        elif isinstance(input, BackgroundRef):
            if input.database != out.database.name:
                raise Invalid(
                    f"{input.database!r} is not this product system's {out.database.name!r}"
                )
            if unit is None or name is None:
                raise Invalid("a background input needs its unit and name resolved")
        else:
            raise Invalid("a product exchange needs a process reference")
    else:
        if not isinstance(input, ElementaryFlowRef):
            raise Invalid("an elementary exchange needs an elementary flow reference")
        if input.database != out.database.elementary_flows:
            raise Invalid(
                f"{input.database!r} is not this product system's {out.database.elementary_flows!r}"
            )
        if unit is None or name is None:
            raise Invalid("an elementary flow input needs its unit and name resolved")
    try:
        exchange = Exchange(
            id=uuid.uuid4(),
            type=type,
            name=name,
            amount=amount if amount is not None else 1.0,
            unit=unit,
            input=input,
            formula=formula,
            comment=comment,
            uncertainty=uncertainty,
        )
    except ValidationError as error:
        raise invalid(error) from error
    process.exchanges.append(exchange)
    return _materialised(out, exchange.id)


def patch_exchange(
    system: ProductSystem,
    exchange_id: uuid.UUID,
    *,
    amount: float | None = None,
    formula: str | None = None,
    name: str | None = None,
    unit: str | None = None,
    comment: str | None = None,
    uncertainty: Uncertainty | None = None,
    clear: Sequence[ExchangeClearable] = (),
) -> tuple[ProductSystem, Exchange]:
    """The document with an exchange's fields replaced; type and input are fixed."""
    given = [amount, formula, name, unit, comment, uncertainty]
    if all(value is None for value in given) and not clear:
        raise Invalid("name at least one field to change")
    out = system.model_copy(deep=True)
    process, exchange = out.exchange(exchange_id)
    if "formula" in clear:
        exchange.formula = None
    if "comment" in clear:
        exchange.comment = None
    if "uncertainty" in clear:
        exchange.uncertainty = None
    if formula is not None:
        exchange.formula = formula
    if amount is not None:
        if exchange.formula is not None:
            raise Invalid("the amount is derived from a formula; clear the formula to set it")
        exchange.amount = amount
    if unit is not None:
        if exchange.type == "production":
            raise Invalid("a production unit is the process unit; update the process")
        if isinstance(exchange.input, ForegroundRef):
            target = out.process(exchange.input.code)
            unit = same_unit(unit, target.unit, target.code)
        exchange.unit = unit
    if name is not None:
        exchange.name = name
    if comment is not None:
        exchange.comment = comment
    if uncertainty is not None:
        exchange.uncertainty = uncertainty
    return _materialised(out, exchange_id)


def remove_exchange(system: ProductSystem, exchange_id: uuid.UUID) -> ProductSystem:
    """The document without the exchange; refused for a production exchange, which states what
    its process makes, and while a scenario overrides it."""
    out = system.model_copy(deep=True)
    process, exchange = out.exchange(exchange_id)
    if exchange.type == "production":
        raise Invalid(
            f"{process.code!r} keeps its production exchange; update its amount or delete "
            "the process"
        )
    scenarios = _overriding_scenarios(out, {exchange_id})
    if scenarios:
        raise Invalid(
            f"scenarios {scenarios} override exchange {out.exchange_named(exchange_id)}; "
            "delete them first"
        )
    process.exchanges = [e for e in process.exchanges if e.id != exchange_id]
    return out


def rebase_links(
    system: ProductSystem, current: Mapping[uuid.UUID, str], linked: uuid.UUID | None = None
) -> tuple[ProductSystem, list[SystemRef]]:
    """The document with each link, or each link to one system, pinned to that system's current
    hash, and the links it moved; Invalid when it links no such system or none is behind."""
    if linked is not None and all(ref.product_system_id != linked for ref in pins(system)):
        raise Invalid(f"{system.name} has no link to product system {linked}")
    out = system.model_copy(deep=True)
    moved: list[SystemRef] = []
    for process in out.processes:
        for exchange in process.exchanges:
            ref = exchange.input
            if not isinstance(ref, SystemRef):
                continue
            if linked is not None and ref.product_system_id != linked:
                continue
            now = current[ref.product_system_id]
            if ref.at_hash == now:
                continue
            exchange.input = ref.model_copy(update={"at_hash": now})
            if exchange.input not in moved:
                moved.append(exchange.input)
    if not moved:
        raise Invalid("every link named is already at its system's current hash")
    return out, moved


def _parameter_users(system: ProductSystem, name: str) -> list[str]:
    symbol = re.compile(rf"\b{re.escape(name)}\b")
    users = [
        f"exchange {e.id} on {a.code}"
        for a in system.processes
        for e in a.exchanges
        if e.formula is not None and symbol.search(e.formula)
    ]
    users += [
        f"parameter {p.name}"
        for p in system.parameters
        if p.formula is not None and symbol.search(p.formula)
    ]
    users += [f"case {c.name}" for c in system.cases if name in c.values]
    return users


def set_parameter_space(
    system: ProductSystem,
    parameters: Sequence[Parameter] = (),
    cases: Sequence[Case] = (),
    delete_parameters: Sequence[str] = (),
    delete_cases: Sequence[str] = (),
) -> ProductSystem:
    """The document with parameters and cases replaced by name and the named ones removed.

    A deleted name is refused when something that survives the write still uses it, so one
    call can drop a parameter together with the formula and the case cells that used it.
    """
    if not (parameters or cases or delete_parameters or delete_cases):
        raise Invalid("name parameters or cases to set or delete")
    out = system.model_copy(deep=True)
    for name in delete_cases:
        out.case(name)
    for name in delete_parameters:
        out.parameter(name)
    by_case = {c.name: c for c in out.cases if c.name not in delete_cases}
    by_name = {p.name: p for p in out.parameters if p.name not in delete_parameters}
    for parameter in parameters:
        by_name[parameter.name] = parameter
    out.parameters = list(by_name.values())
    literal = {p.name for p in out.parameters if p.formula is None}
    for case in cases:
        bad = sorted(set(case.values) - literal)
        if bad:
            raise Invalid(f"case {case.name!r} sets {bad}, which are not literal parameters")
        by_case[case.name] = case
    out.cases = list(by_case.values())
    shared = out.shared_variant_names()
    if shared:
        raise Conflict(
            f"{shared} name scenarios of {system.name!r}; a case takes a name no scenario has"
        )
    for name in delete_parameters:
        users = _parameter_users(out, name)
        if users:
            raise Invalid(f"parameter {name!r} is used by {users}; change those first")
    return materialize(out)


def add_scenario(
    system: ProductSystem, *, name: str, description: str, overrides: Sequence[Override]
) -> tuple[ProductSystem, Scenario]:
    """The document with a new scenario, applied once to prove it, pinned to the base pin."""
    if any(s.name == name for s in system.scenarios):
        raise Conflict(f"scenario {name!r} already exists in {system.name!r}")
    try:
        scenario = Scenario(
            name=name,
            description=description,
            overrides=list(overrides),
            base_hash=base_pin(system),
        )
    except ValidationError as error:
        raise invalid(error) from error
    out = system.model_copy(deep=True)
    out.scenarios.append(scenario)
    if out.shared_variant_names():
        raise Conflict(
            f"case {name!r} exists in {system.name!r}; a scenario takes a name no case has"
        )
    apply_scenario(system, scenario)
    return out, scenario


def remove_scenario(system: ProductSystem, name: str) -> ProductSystem:
    """The document without the scenario."""
    system.scenario(name)
    out = system.model_copy(deep=True)
    out.scenarios = [s for s in out.scenarios if s.name != name]
    return out


def rebase_scenario(system: ProductSystem, name: str) -> tuple[ProductSystem, Scenario]:
    """The document with the scenario applied once more and pinned to the base pin."""
    out = system.model_copy(deep=True)
    scenario = out.scenario(name)
    apply_scenario(out, scenario)
    scenario.base_hash = base_pin(out)
    return out, scenario
