"""A product system as an openLCA JSON-LD directory, and back."""

from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import olca_schema as o
from olca_schema import units as olca_units
from pydantic import ValidationError

from ecosemantic.compute.edits import invalid
from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model import units
from ecosemantic.model.entities import (
    Case,
    Exchange,
    Parameter,
    Process,
    ProductSystem,
)
from ecosemantic.model.refs import (
    BackgroundRef,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
    keygen,
    olca_elementary_flow_id,
    olca_process_id,
    olca_product_flow_id,
    slug,
)
from ecosemantic.package.olca import from_olca_uncertainty, to_olca_uncertainty
from ecosemantic.package.sidecar import (
    ExchangeIdentity,
    Identities,
    ProcessIdentity,
    Sidecar,
    supplier_key,
)
from ecosemantic.ports.resolver import Resolver

DESCRIPTOR = "olca-schema.json"
BASE_TAG = "ecosemantic:base="


@dataclass(frozen=True)
class Stated:
    """The log entry a package's openLCA half was written at, and that entry's result hash."""

    seq: int
    hash: str

    def tag(self) -> str:
        """The product system's tag that names the entry: its hash, then its number."""
        return f"{BASE_TAG}{self.hash}:{self.seq}"


_FOLDERS: dict[type, str] = {
    o.UnitGroup: "unit_groups",
    o.FlowProperty: "flow_properties",
    o.Location: "locations",
    o.Flow: "flows",
    o.Process: "processes",
    o.Parameter: "parameters",
    o.ProductSystem: "product_systems",
}


def parameter_prefix(product_system: ProductSystem) -> str:
    """The prefix keeping this system's global parameters apart in one openLCA database."""
    return slug(product_system.name, "_") + "__"


def rewrite_formula(formula: str, names: set[str], prefix: str) -> str:
    """Prefix every occurrence of a parameter name at a word boundary."""
    if not names:
        return formula
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.sub(rf"\b({alternatives})\b", lambda m: prefix + m.group(1), formula)


def strip_prefix(text: str, prefix: str) -> str:
    """Remove the prefix wherever it starts a word."""
    return re.sub(r"\b" + re.escape(prefix), "", text)


def _filed_alike(symbol: str, group: str) -> bool:
    filed = olca_units.group_ref(symbol)
    return filed is not None and filed.name == group


def _unit_refs(unit: str) -> tuple[o.Ref, o.Ref, o.Ref]:
    """A unit's openLCA unit, unit group and flow property. openLCA's reference ids stand where
    its reference data files the unit, and the group, under the core's group of that name; ids
    derived from the names stand everywhere else, so a quantity the core keeps apart, such as
    standard volume, stays apart."""
    known = units.by_name(unit)
    symbol = known.symbols[0]
    anchor = units.canonical(known.group).symbols[0]
    if _filed_alike(anchor, known.group):
        group_ref, property_ref = olca_units.group_ref(anchor), olca_units.property_ref(anchor)
    else:
        quantity = known.group.removeprefix("Units of ").capitalize()
        group_ref = _ref(o.RefType.UnitGroup, keygen("unit group", known.group), known.group)
        property_ref = _ref(o.RefType.FlowProperty, keygen("flow property", known.group), quantity)
    unit_ref = olca_units.unit_ref(symbol) if _filed_alike(symbol, known.group) else None
    if unit_ref is None:
        unit_ref = _ref(o.RefType.Unit, keygen("unit", symbol), symbol)
    return unit_ref, group_ref, property_ref


def _write_entity(root: Path, entity: o.RootEntity) -> None:
    folder = root / _FOLDERS[type(entity)]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{entity.id}.json").write_text(entity.to_json(), encoding="utf-8", newline="\n")


def _ref(entity_type: o.RefType, entity_id: str, name: str, **extra: object) -> o.Ref:
    return o.Ref(ref_type=entity_type, id=entity_id, name=name, **extra)


def _factor(property_ref: o.Ref) -> o.FlowPropertyFactor:
    return o.FlowPropertyFactor(
        flow_property=property_ref, conversion_factor=1.0, is_ref_flow_property=True
    )


class UnitTable:
    """The unit groups and flow properties a set of model units needs; each group lists every
    unit used of its quantity against the canonical one."""

    def __init__(self) -> None:
        self.groups: dict[str, o.UnitGroup] = {}
        self.properties: dict[str, o.FlowProperty] = {}

    def refs(self, name: str) -> tuple[o.Ref, o.Ref]:
        """The openLCA unit and flow property references of a model unit."""
        unit = units.by_name(name)
        canonical = units.canonical(unit.group)
        reference, group_ref, property_ref = _unit_refs(canonical.name)
        unit_ref = reference if unit == canonical else _unit_refs(name)[0]
        group = self.groups.setdefault(
            group_ref.id,
            o.UnitGroup(
                id=group_ref.id,
                name=group_ref.name,
                default_flow_property=property_ref,
                units=[
                    o.Unit(
                        id=reference.id,
                        name=reference.name,
                        conversion_factor=1.0,
                        is_ref_unit=True,
                    )
                ],
            ),
        )
        if all(u.id != unit_ref.id for u in group.units or []):
            group.units = [
                *(group.units or []),
                o.Unit(id=unit_ref.id, name=unit_ref.name, conversion_factor=unit.factor),
            ]
        self.properties.setdefault(
            property_ref.id,
            o.FlowProperty(
                id=property_ref.id,
                name=property_ref.name,
                flow_property_type=o.FlowPropertyType.PHYSICAL_QUANTITY,
                unit_group=group_ref,
            ),
        )
        return unit_ref, property_ref

    def entities(self) -> list[o.RootEntity]:
        """The unit groups, then the flow properties."""
        return [*self.groups.values(), *self.properties.values()]


def location_entity(code: str) -> tuple[o.Ref, o.Location]:
    """The reference to a location code and the location it names, under openLCA's name-based id."""
    return (
        _ref(o.RefType.Location, keygen(code), code),
        o.Location(id=keygen(code), name=code, code=code),
    )


class _Writer:
    def __init__(
        self,
        product_system: ProductSystem,
        resolver: Resolver,
        linked: Mapping[uuid.UUID, ProductSystem],
        state: Stated | None,
    ) -> None:
        self.product_system = product_system
        self.resolver = resolver
        self.linked = linked
        self.state = state
        self.scheme = product_system.database.scheme
        self.prefix = parameter_prefix(product_system)
        self.identities = Identities(parameter_prefix=self.prefix)
        self.units = UnitTable()
        self.locations: dict[str, o.Location] = {}
        self.elementary_flows: dict[str, o.Flow] = {}
        self.links: list[o.ProcessLink] = []

    def unit(self, name: str) -> tuple[o.Ref, o.Ref]:
        return self.units.refs(name)

    def location(self, code: str) -> o.Ref:
        ref, entity = location_entity(code)
        if code not in self.locations:
            self.locations[code] = entity
            self.identities.locations[keygen(code)] = code
        return ref

    def _flow(self, process: Process, owner: str) -> o.Ref:
        flow_id = str(uuid.uuid5(process.id, "product"))
        if flow_id not in self.elementary_flows:
            _, property_ref = self.unit(process.unit)
            self.elementary_flows[flow_id] = o.Flow(
                id=flow_id,
                name=process.reference_product,
                flow_type=o.FlowType.PRODUCT_FLOW,
                category=f"ecosemantic/{slug(owner, '_')}",
                location=self.location(process.location),
                flow_properties=[_factor(property_ref)],
            )
        return _ref(
            o.RefType.Flow, flow_id, process.reference_product, flow_type=o.FlowType.PRODUCT_FLOW
        )

    def product_flow(self, process: Process) -> o.Ref:
        ref = self._flow(process, self.product_system.name)
        self.identities.product_flows[str(uuid.uuid5(process.id, "product"))] = process.id
        return ref

    def linked_provider(self, ref: SystemRef, owner: str) -> tuple[o.Ref, o.Ref]:
        """The flow of the linked system's reference product and the system as openLCA's
        provider, from the system as it stood at the pin."""
        linked = self.linked.get(ref.product_system_id)
        if linked is None or linked.hash != ref.at_hash:
            raise NotFound(
                f"{owner} links product system {ref.product_system_id} at {ref.at_hash}, "
                "which the write was not given"
            )
        if linked.reference_process is None:
            raise Invalid(f"{owner} links {linked.name}, which has no reference process")
        target = linked.process(linked.reference_process)
        return (
            self._flow(target, linked.name),
            _ref(o.RefType.ProductSystem, str(linked.id), linked.name),
        )

    def background(self, ref: BackgroundRef) -> tuple[o.Ref, o.Ref]:
        info = self.resolver.background(ref)
        flow_id = olca_product_flow_id(self.scheme, ref.id)
        process_id = olca_process_id(self.scheme, ref.id)
        if flow_id not in self.elementary_flows:
            _, property_ref = self.unit(info.unit)
            self.elementary_flows[flow_id] = o.Flow(
                id=flow_id,
                name=info.reference_product,
                flow_type=o.FlowType.PRODUCT_FLOW,
                category=f"{ref.database}/products",
                flow_properties=[_factor(property_ref)],
            )
        self.identities.suppliers[supplier_key(process_id, flow_id)] = ref
        return (
            _ref(
                o.RefType.Flow, flow_id, info.reference_product, flow_type=o.FlowType.PRODUCT_FLOW
            ),
            _ref(
                o.RefType.Process,
                process_id,
                info.name,
                location=info.location,
                process_type=o.ProcessType.UNIT_PROCESS,
            ),
        )

    def elementary(self, ref: ElementaryFlowRef) -> tuple[o.Ref, bool]:
        info = self.resolver.flow(ref)
        flow_id = olca_elementary_flow_id(self.scheme, ref.id)
        if flow_id not in self.elementary_flows:
            _, property_ref = self.unit(info.unit)
            category = "Elementary flows/" + info.compartment
            if info.sub_compartment:
                category += f"/{info.sub_compartment}"
            self.elementary_flows[flow_id] = o.Flow(
                id=flow_id,
                name=info.name,
                flow_type=o.FlowType.ELEMENTARY_FLOW,
                category=category,
                flow_properties=[_factor(property_ref)],
            )
            self.identities.elementary_flows[flow_id] = ref
        flow_ref = _ref(o.RefType.Flow, flow_id, info.name, flow_type=o.FlowType.ELEMENTARY_FLOW)
        return flow_ref, info.side == "input"

    def exchange(
        self, process: Process, number: int, exchange: Exchange, names: set[str]
    ) -> o.Exchange:
        unit_ref, property_ref = self.unit(exchange.unit)
        out = o.Exchange(
            internal_id=number,
            amount=exchange.amount,
            unit=unit_ref,
            flow_property=property_ref,
            description=exchange.comment,
            uncertainty=to_olca_uncertainty(exchange.uncertainty),
            amount_formula=(
                rewrite_formula(exchange.formula, names, self.prefix) if exchange.formula else None
            ),
        )
        if exchange.type == "production":
            out.flow = self.product_flow(process)
            out.is_input = False
            out.is_quantitative_reference = True
        elif isinstance(exchange.input, ElementaryFlowRef):
            out.flow, out.is_input = self.elementary(exchange.input)
        elif isinstance(exchange.input, BackgroundRef):
            out.flow, out.default_provider = self.background(exchange.input)
            out.is_input = True
        elif isinstance(exchange.input, ForegroundRef):
            target = self.product_system.process(exchange.input.code)
            out.flow = self.product_flow(target)
            out.default_provider = _ref(o.RefType.Process, str(target.id), target.name)
            out.is_input = True
            self.links.append(
                o.ProcessLink(
                    provider=out.default_provider,
                    flow=out.flow,
                    process=_ref(o.RefType.Process, str(process.id), process.name),
                    exchange=o.ExchangeRef(internal_id=number),
                )
            )
        elif isinstance(exchange.input, SystemRef):
            out.flow, provider = self.linked_provider(exchange.input, process.code)
            out.is_input = True
            self.links.append(
                o.ProcessLink(
                    provider=provider,
                    flow=out.flow,
                    process=_ref(o.RefType.Process, str(process.id), process.name),
                    exchange=o.ExchangeRef(internal_id=number),
                )
            )
            self.identities.links[f"{process.id}:{number}"] = exchange.input
        else:
            raise Invalid(
                f"exchange {exchange.name!r} references {exchange.input!r}, "
                "which the package cannot carry"
            )
        self.identities.exchanges[f"{process.id}:{number}"] = ExchangeIdentity(
            id=exchange.id, label=exchange.name
        )
        return out

    def reference(self) -> tuple[Process, int] | None:
        """The reference process and its production exchange's internal id, or None without
        one."""
        code = self.product_system.reference_process
        if code is None:
            return None
        process = self.product_system.process(code)
        for n, exchange in enumerate(process.exchanges, start=1):
            if exchange.type == "production":
                return process, n
        return None

    def write(self, root: Path) -> Identities:
        names = {p.name for p in self.product_system.parameters}
        self.identities.parameter_units = {p.name: p.unit for p in self.product_system.parameters}
        processes: list[o.Process] = []
        for process in self.product_system.processes:
            exchanges = [
                self.exchange(process, n, e, names)
                for n, e in enumerate(process.exchanges, start=1)
            ]
            processes.append(
                o.Process(
                    id=str(process.id),
                    name=process.name,
                    description=process.comment,
                    process_type=o.ProcessType.UNIT_PROCESS,
                    category=f"ecosemantic/{slug(self.product_system.name, '_')}",
                    location=self.location(process.location),
                    exchanges=exchanges,
                    last_internal_id=len(exchanges),
                )
            )
            self.identities.processes[str(process.id)] = ProcessIdentity(
                id=process.id, code=process.code
            )
        parameters = [
            o.Parameter(
                id=str(uuid.uuid5(self.product_system.id, p.name)),
                name=self.prefix + p.name,
                parameter_scope=o.ParameterScope.GLOBAL_SCOPE,
                is_input_parameter=p.formula is None,
                value=p.value,
                formula=rewrite_formula(p.formula, names, self.prefix) if p.formula else None,
                description=p.description,
            )
            for p in self.product_system.parameters
        ]
        system = o.ProductSystem(
            id=str(self.product_system.id),
            name=self.product_system.name,
            description=self.product_system.description,
            processes=[
                _ref(o.RefType.Process, str(a.id), a.name) for a in self.product_system.processes
            ],
            process_links=self.links,
            tags=[self.state.tag()] if self.state is not None else None,
            parameter_sets=[
                o.ParameterRedefSet(
                    name=c.name,
                    description=c.description,
                    is_baseline=False,
                    parameters=[
                        o.ParameterRedef(name=self.prefix + k, value=v) for k, v in c.values.items()
                    ],
                )
                for c in self.product_system.cases
            ],
        )
        reference = self.reference()
        if reference is not None:
            root_activity, production = reference
            unit_ref, property_ref = self.unit(root_activity.unit)
            system.ref_process = _ref(o.RefType.Process, str(root_activity.id), root_activity.name)
            system.ref_exchange = o.ExchangeRef(internal_id=production)
            system.target_amount = 1.0
            system.target_flow_property = property_ref
            system.target_unit = unit_ref
        entities = [
            *self.units.entities(),
            *self.locations.values(),
            *self.elementary_flows.values(),
            *processes,
            *parameters,
            system,
        ]
        for folder in _FOLDERS.values():
            shutil.rmtree(root / folder, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        (root / DESCRIPTOR).write_text('{"version": 2}', encoding="utf-8", newline="\n")
        for entity in entities:
            _write_entity(root, entity)
        return self.identities


def write_jsonld(
    product_system: ProductSystem,
    root: Path,
    resolver: Resolver,
    linked: Mapping[uuid.UUID, ProductSystem] | None = None,
    state: Stated | None = None,
) -> Identities:
    """Write the openLCA half of a package into root, with each system it links as it stood at
    the pin, and the log entry it is written at named in the product system's base tag, which
    openLCA keeps through its import and export. Every entity is built before what an older write
    left is cleared, so a write the package refuses leaves that one whole."""
    return _Writer(product_system, resolver, linked or {}, state).write(root)


def stated_base(root: Path, product_system_id: uuid.UUID) -> Stated | None:
    """The log entry the openLCA half's product system names in its base tag; None when it
    carries none, Invalid for a base tag that names no entry."""
    for system in _read_entities(root, o.ProductSystem):
        if system.id == str(product_system_id):
            for tag in system.tags or []:
                if tag.startswith(BASE_TAG):
                    named, _, seq = tag[len(BASE_TAG) :].rpartition(":")
                    if not named or not seq.isdigit():
                        raise Invalid(f"the base tag {tag!r} names no entry")
                    return Stated(seq=int(seq), hash=named)
    return None


def _read_entities(root: Path, entity_type: type) -> list[o.RootEntity]:
    folder = root / _FOLDERS[entity_type]
    if not folder.is_dir():
        return []
    return [
        entity_type.from_json(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.json"))
    ]


def _unit_name(ref: o.Ref | None) -> str:
    if ref is None or ref.name is None:
        raise Invalid("an exchange without a unit")
    return units.by_symbol(ref.name).name


def _unique_code(name: str, taken: set[str]) -> str:
    base = slug(name, "_") or "process"
    code, n = base, 2
    while code in taken:
        code, n = f"{base}_{n}", n + 1
    taken.add(code)
    return code


Ref = BackgroundRef | ElementaryFlowRef | ForegroundRef | SystemRef | None


class _Reader:
    def __init__(self, root: Path, sidecar: Sidecar) -> None:
        self.root = root
        self.sidecar = sidecar
        self.ident = sidecar.identities
        self.elementary_flows = {f.id: f for f in _read_entities(root, o.Flow)}
        self.codes: dict[str, str] = {pid: p.code for pid, p in self.ident.processes.items()}
        self.code_of: dict[uuid.UUID, str] = {p.id: p.code for p in self.ident.processes.values()}
        self.new_ids: dict[str, uuid.UUID] = {}
        self.taken = {p.code for p in self.ident.processes.values()}

    def identity_of(self, process: o.Process) -> tuple[uuid.UUID, str]:
        known = self.ident.processes.get(process.id)
        if known:
            return known.id, known.code
        code = self.codes.get(process.id) or _unique_code(process.name, self.taken)
        self.codes[process.id] = code
        self.new_ids.setdefault(process.id, uuid.uuid4())
        return self.new_ids[process.id], code

    def flow_type_of(self, exchange: o.Exchange) -> o.FlowType | None:
        """The type of the exchange's flow, as its own file states it or else its reference."""
        flow_id = exchange.flow.id if exchange.flow else None
        flow = self.elementary_flows.get(flow_id) if flow_id else None
        return flow.flow_type if flow else (exchange.flow.flow_type if exchange.flow else None)

    def input_of(self, process: o.Process, exchange: o.Exchange) -> tuple[str, Ref]:
        if exchange.is_quantitative_reference:
            return "production", None
        link = self.ident.links.get(f"{process.id}:{exchange.internal_id}")
        if link is not None:
            return "product", link
        flow_id = exchange.flow.id if exchange.flow else None
        flow_type = self.flow_type_of(exchange)
        if flow_type == o.FlowType.ELEMENTARY_FLOW:
            known = self.ident.elementary_flows.get(flow_id)
            if known:
                return "elementary", known
            elementary_flows = self.sidecar.product_system.database.elementary_flows
            return "elementary", ElementaryFlowRef(database=elementary_flows, id=flow_id)
        provider_id = exchange.default_provider.id if exchange.default_provider else None
        supplier = (
            self.ident.suppliers.get(supplier_key(provider_id, flow_id))
            if provider_id and flow_id
            else None
        )
        if supplier:
            return "product", supplier
        owner = self.ident.product_flows.get(flow_id) if flow_id else None
        if owner is not None:
            return "product", ForegroundRef(code=self.code_of[owner])
        if exchange.default_provider and exchange.default_provider.id in self.codes:
            return "product", ForegroundRef(code=self.codes[exchange.default_provider.id])
        raise Invalid(
            f"exchange {exchange.internal_id} of {process.name!r} references a flow "
            "the package cannot place"
        )

    def sign_of(self, process: o.Process, exchange: o.Exchange, kind: str) -> float:
        """-1 for a waste output and for an avoided product, which the core holds as a product
        exchange of the negated amount, as the background reader does; 1 otherwise. Invalid for
        any other product output: a co-product, and the core holds no allocation."""
        if kind != "product":
            return 1.0
        if exchange.is_avoided_product:
            return -1.0
        if exchange.is_input:
            return 1.0
        if self.flow_type_of(exchange) == o.FlowType.WASTE_FLOW:
            return -1.0
        flow = exchange.flow.name if exchange.flow else None
        raise Invalid(
            f"exchange {exchange.internal_id} of {process.name!r} is a co-product, an output of "
            f"{flow!r} neither the reference nor avoided; the core holds no allocation"
        )

    def exchange_of(self, process: o.Process, exchange: o.Exchange) -> Exchange:
        if exchange.amount is None:
            raise Invalid(f"exchange {exchange.internal_id} of {process.name!r} has no amount")
        kind, ref = self.input_of(process, exchange)
        sign = self.sign_of(process, exchange, kind)
        known = self.ident.exchanges.get(f"{process.id}:{exchange.internal_id}")
        flow_name = exchange.flow.name if exchange.flow and exchange.flow.name else ""
        formula = exchange.amount_formula
        uncertainty = from_olca_uncertainty(
            exchange.uncertainty,
            exchange.amount,
            owner=f"{process.name!r}, exchange of {flow_name!r}",
        )
        return Exchange(
            id=known.id if known else uuid.uuid4(),
            type=kind,
            name=known.label if known else flow_name,
            amount=exchange.amount * sign,
            unit=_unit_name(exchange.unit),
            input=ref,
            formula=strip_prefix(formula, self.ident.parameter_prefix) if formula else None,
            comment=exchange.description,
            uncertainty=uncertainty.scaled(sign) if uncertainty is not None else None,
        )

    def read(self) -> ProductSystem:
        own = str(self.sidecar.product_system.id)
        olca_systems = _read_entities(self.root, o.ProductSystem)
        olca_system = next((s for s in olca_systems if s.id == own), None)
        listed = {r.id for r in olca_system.processes or []} if olca_system is not None else set()
        theirs = {r.id for s in olca_systems if s.id != own for r in s.processes or []} - listed
        olca_processes = [p for p in _read_entities(self.root, o.Process) if p.id not in theirs]
        for olca in olca_processes:
            self.identity_of(olca)
        processes: list[Process] = []
        for olca in olca_processes:
            process_id, code = self.identity_of(olca)
            reference = next((e for e in olca.exchanges or [] if e.is_quantitative_reference), None)
            if reference is None or reference.flow is None:
                raise Invalid(f"process {olca.name!r} has no quantitative reference")
            processes.append(
                Process(
                    id=process_id,
                    code=code,
                    name=olca.name,
                    unit=_unit_name(reference.unit),
                    location=olca.location.name if olca.location else "",
                    reference_product=reference.flow.name or "",
                    comment=olca.description,
                    metadata=self.sidecar.metadata.get(process_id, {}),
                    exchanges=[self.exchange_of(olca, e) for e in olca.exchanges or []],
                )
            )
        prefix = self.ident.parameter_prefix
        parameters = [
            Parameter(
                name=p.name[len(prefix) :],
                value=p.value if p.is_input_parameter else None,
                formula=(
                    strip_prefix(p.formula, prefix)
                    if (p.formula and not p.is_input_parameter)
                    else None
                ),
                unit=self.ident.parameter_units.get(p.name[len(prefix) :], ""),
                description=p.description or "",
            )
            for p in _read_entities(self.root, o.Parameter)
            if p.parameter_scope == o.ParameterScope.GLOBAL_SCOPE
            and p.name
            and p.name.startswith(prefix)
        ]
        cases = [
            Case(
                name=s.name or "",
                description=s.description or "",
                values={
                    r.name[len(prefix) :]: r.value
                    for r in s.parameters or []
                    if r.name and r.value is not None
                },
            )
            for s in (olca_system.parameter_sets or [] if olca_system is not None else [])
        ]
        record = self.sidecar.product_system
        try:
            return ProductSystem(
                id=record.id,
                name=record.name,
                description=record.description,
                notes=record.notes,
                database=record.database,
                processes=processes,
                parameters=parameters,
                cases=cases,
                scenarios=self.sidecar.scenarios,
                reference_process=(
                    self.codes[olca_system.ref_process.id]
                    if olca_system is not None and olca_system.ref_process is not None
                    else None
                ),
            )
        except ValidationError as error:
            raise invalid(error) from error


def read_jsonld(root: Path, sidecar: Sidecar) -> ProductSystem:
    """Rebuild the product system from the openLCA half of a package and its retained sidecar."""
    return _Reader(root, sidecar).read()
