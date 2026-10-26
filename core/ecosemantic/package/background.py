"""An openLCA JSON-LD package as datasets, elementary flows and methods, read with olca-schema
alone."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

import olca_schema as o
from olca_schema.zipio import ZipReader

from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model import units
from ecosemantic.package.olca import from_olca_uncertainty
from ecosemantic.package.wholeness import providers, resolve_provider
from ecosemantic.ports.types import FlowType

Key = tuple[str, str]
Dataset = dict[str, object]
ELEMENTARY_ROOT = "elementary flows"
ALLOCATED = (
    o.AllocationType.PHYSICAL_ALLOCATION,
    o.AllocationType.ECONOMIC_ALLOCATION,
    o.AllocationType.CAUSAL_ALLOCATION,
)


@dataclass(frozen=True)
class Unlinked:
    """A product or waste input no dataset in the package provides, and the dataset that would
    have carried its exchange."""

    process: str
    process_id: str
    flow: str
    flow_id: str
    provider_id: str | None
    reason: str
    dataset: str
    position: int
    is_input: bool
    amount: float
    unit: str


@dataclass(frozen=True)
class ImportedMethod:
    """One impact category: its key, unit and factors, and how many factors it set apart by
    naming a location."""

    key: tuple[str, str, str]
    unit: str
    factors: list[tuple[Key, float]]
    set_apart: int = 0


@dataclass(frozen=True)
class Import:
    """What a package becomes: datasets, elementary flows, methods, and what could not link."""

    database: str
    biosphere: str
    datasets: dict[Key, Dataset]
    flows: dict[Key, Dataset]
    methods: list[ImportedMethod]
    processes: int
    unlinked: list[Unlinked] = field(default_factory=list)


@dataclass(frozen=True)
class _Flow:
    entity: o.Flow
    reference_property: str
    stored: units.Unit


def _ref_id(ref: o.Ref | None, what: str) -> str:
    if ref is None or ref.id is None:
        raise Invalid(f"{what} carries no reference")
    return ref.id


def _ref_name(ref: o.Ref | None, what: str) -> str:
    if ref is None or ref.name is None:
        raise Invalid(f"{what} has no unit")
    return ref.name


def _categories(path: str | None) -> tuple[str, ...]:
    parts = [p.strip() for p in (path or "").split("/") if p.strip()]
    if parts and parts[0].lower() == ELEMENTARY_ROOT:
        parts = parts[1:]
    return tuple(parts)


def _flow_type(categories: tuple[str, ...]) -> FlowType:
    """The type an elementary flow's top category names: openLCA's `Resource` or ecoinvent's
    `natural resource` is a natural resource, a category named after a type is that type, and any
    other is an emission."""
    top = categories[0].lower() if categories else ""
    if top.startswith("resource"):
        return "natural resource"
    for flow_type in get_args(FlowType):
        if top == flow_type:
            return flow_type
    return "emission"


def _distribution(process: o.Process, e: o.Exchange, flow: _Flow, factor: float) -> Dataset:
    """The distribution of an exchange whose amount was multiplied by factor, as the model's
    `Uncertainty`, under the row's `uncertainty` key; none when the exchange has none."""
    uncertainty = from_olca_uncertainty(
        e.uncertainty,
        e.amount or 0.0,
        owner=f"{process.name!r}, exchange of {flow.entity.name!r}",
    )
    return {"uncertainty": uncertainty.scaled(factor) if uncertainty else None}


def exchange_refusal(e: o.Exchange, flow: o.Flow) -> str | None:
    """Why the importer cannot hold this exchange, or None. A waste flow taken in by a process
    that does not treat it as its own reference is not one the core can link to a treater."""
    if flow.flow_type == o.FlowType.WASTE_FLOW and e.is_input and not e.is_quantitative_reference:
        return "a waste input that is not its process's reference"
    return None


class _Reader:
    def __init__(self, reader: ZipReader, name: str, foreground: frozenset[str]) -> None:
        self.reader = reader
        self.database = name
        self.biosphere = f"{name}-biosphere"
        self.reference_symbols = {
            g.id: next(u.name for u in g.units or [] if u.is_ref_unit)
            for g in reader.read_each(o.UnitGroup)
        }
        self.property_groups = {
            p.id: _ref_id(p.unit_group, f"flow property {p.name!r}")
            for p in reader.read_each(o.FlowProperty)
        }
        self.locations = {loc.id: loc.code for loc in reader.read_each(o.Location)}
        self.sources = {s.id: s.url for s in reader.read_each(o.Source)}
        self.flows = {f.id: self._flow(f) for f in reader.read_each(o.Flow)}
        self.processes = [p for p in reader.read_each(o.Process) if p.id not in foreground]
        self._declared()
        self.producers, self.treaters = providers(
            self.processes, {i: f.entity.flow_type for i, f in self.flows.items()}
        )
        self.unlinked: list[Unlinked] = []

    def _location(self, process: o.Process) -> str | None:
        """The code of the process's location, or None when it names none. Invalid when the
        package does not hold the location the process names."""
        if process.location is None:
            return None
        at = process.location.id or ""
        if at not in self.locations:
            raise Invalid(
                f"{process.name!r} names location {at!r}, which the package does not hold"
            )
        return self.locations[at]

    def _url(self, process: o.Process) -> dict[str, str]:
        """The dataset's publication link, when its documentation names one."""
        publication = (
            process.process_documentation.publication if process.process_documentation else None
        )
        if publication is None:
            return {}
        if publication.id not in self.sources:
            raise Invalid(
                f"{process.name!r} names a publication the package lacks: {publication.id}"
            )
        url = self.sources[publication.id]
        return {"url": url} if url else {}

    def _flow(self, flow: o.Flow) -> _Flow:
        reference = next((fp for fp in flow.flow_properties or [] if fp.is_ref_flow_property), None)
        if reference is None:
            raise Invalid(f"flow {flow.name!r} has no reference flow property")
        property_id = _ref_id(reference.flow_property, f"flow {flow.name!r}")
        symbol = self.reference_symbols[self.property_groups[property_id]]
        return _Flow(flow, property_id, units.canonical(units.by_symbol(symbol).group))

    def _declared(self) -> None:
        """Store each product and treated waste in the unit its producers declare on it, so a
        dataset keeps the unit its author gave it; producers that disagree, or declare a unit of
        another quantity, leave the quantity's canonical unit."""
        declared: dict[str, set[str]] = {}
        for process in self.processes:
            for e in process.exchanges or []:
                if e.flow is None or e.flow.id not in self.flows or e.unit is None:
                    continue
                kind = self.flows[e.flow.id].entity.flow_type
                made = kind == o.FlowType.PRODUCT_FLOW and not e.is_input
                treated = (
                    kind == o.FlowType.WASTE_FLOW and e.is_input and e.is_quantitative_reference
                )
                if made or treated:
                    declared.setdefault(e.flow.id, set()).add(e.unit.name or "")
        for flow_id, symbols in declared.items():
            flow = self.flows[flow_id]
            if len(symbols) != 1:
                continue
            unit = units.by_symbol(symbols.pop())
            if unit.group == flow.stored.group:
                self.flows[flow_id] = _Flow(flow.entity, flow.reference_property, unit)

    def _amount(self, process: o.Process, e: o.Exchange, flow: _Flow) -> tuple[float, float]:
        """The exchange amount in the unit the flow is stored in, and the factor that got it
        there."""
        owner = f"an exchange of {process.name!r}"
        if _ref_id(e.flow_property, owner) != flow.reference_property:
            raise NotSupported(
                f"{process.name!r} measures {flow.entity.name!r} in flow property "
                f"{_ref_name(e.flow_property, owner)!r}, not its reference property"
            )
        unit = units.by_symbol(_ref_name(e.unit, owner))
        if unit.group != flow.stored.group:
            raise Invalid(
                f"{process.name!r} measures {flow.entity.name!r} in {unit.name!r}, "
                f"a unit of another quantity"
            )
        factor = unit.factor / flow.stored.factor
        return (e.amount or 0.0) * factor, factor

    def _provider(
        self,
        process: o.Process,
        e: o.Exchange,
        flow: _Flow,
        *,
        dataset: str,
        position: int,
        amount: float,
    ) -> str | None:
        """The provider of an input, and the record of the dataset's exchange when none provides
        it."""
        waste = flow.entity.flow_type == o.FlowType.WASTE_FLOW
        candidates = (self.treaters if waste else self.producers).get(flow.entity.id, [])
        named = e.default_provider.id if e.default_provider is not None else None
        provider, reason = resolve_provider(named, candidates)
        if provider is None:
            self.unlinked.append(
                Unlinked(
                    process=process.name or process.id,
                    process_id=process.id,
                    flow=flow.entity.name or flow.entity.id,
                    flow_id=flow.entity.id,
                    provider_id=named,
                    reason=reason,
                    dataset=dataset,
                    position=position,
                    is_input=bool(e.is_input),
                    amount=amount,
                    unit=flow.stored.name,
                )
            )
        return provider

    def _factors(
        self, process: o.Process, products: list[o.Exchange]
    ) -> dict[tuple[str, int | None], float]:
        """The share each reference's dataset takes of each exchange that is not a product's own
        output: 1.0 for a lone reference, the product's own factor under physical and economic
        allocation, and the value of the causal factor that names the pair under causal
        allocation."""
        own = {e.internal_id for e in products}
        others = [e for e in process.exchanges or [] if e.internal_id not in own]
        ids = [_ref_id(p.flow, process.name or "") for p in products]
        if len(products) == 1:
            return {(ids[0], e.internal_id): 1.0 for e in others}
        method = process.default_allocation_method
        if method not in ALLOCATED:
            raise Invalid(
                f"{process.name!r} has {len(products)} products and its default allocation "
                f"is {method.value if method else 'none'}, "
                "which is not physical, economic or causal"
            )
        listed = [f for f in process.allocation_factors or [] if f.allocation_type == method]
        if method == o.AllocationType.CAUSAL_ALLOCATION:
            named = {
                (
                    _ref_id(f.product, f"an allocation factor of {process.name!r}"),
                    f.exchange.internal_id if f.exchange is not None else None,
                ): float(f.value or 0.0)
                for f in listed
            }
            for product, product_id in zip(products, ids, strict=True):
                for e in others:
                    if (product_id, e.internal_id) in named:
                        continue
                    raise Invalid(
                        f"{process.name!r} has no causal factor for product "
                        f"{product.flow.name if product.flow else None!r} and exchange "
                        f"{e.flow.name if e.flow else None!r}"
                    )
            return named
        factors = {
            _ref_id(f.product, f"an allocation factor of {process.name!r}"): float(f.value or 0.0)
            for f in listed
        }
        missing = [p.flow.name for p in products if _ref_id(p.flow, "") not in factors]
        if missing:
            raise Invalid(f"{process.name!r} has no {method.value} factor for {missing}")
        shares: dict[tuple[str, int | None], float] = {}
        for product_id in ids:
            for e in others:
                shares[(product_id, e.internal_id)] = factors[product_id]
        return shares

    def datasets(self, process: o.Process) -> dict[Key, Dataset]:
        """One dataset per product of the process, or one for the waste it treats."""
        exchanges = process.exchanges or []
        flows = {e.internal_id: self.flows[_ref_id(e.flow, process.name or "")] for e in exchanges}
        products = [
            e
            for e in exchanges
            if not e.is_input and flows[e.internal_id].entity.flow_type == o.FlowType.PRODUCT_FLOW
        ]
        treated = [
            e
            for e in exchanges
            if e.is_input
            and e.is_quantitative_reference
            and flows[e.internal_id].entity.flow_type == o.FlowType.WASTE_FLOW
        ]
        if not products and not treated:
            raise Invalid(f"{process.name!r} produces nothing and treats nothing")
        out: dict[Key, Dataset] = {}
        factors = self._factors(process, products or treated)
        product_ids = {e.internal_id for e in products}
        treated_ids = {e.internal_id for e in treated}
        location = self._location(process)
        for reference in products or treated:
            flow = flows[reference.internal_id]
            amount, scale = self._amount(process, reference, flow)
            sign = -1.0 if reference.internal_id in treated_ids else 1.0
            production = sign * amount
            code = f"{process.id}_{flow.entity.id}"
            rows: list[Dataset] = [
                {
                    "input": (self.database, code),
                    "amount": production,
                    "type": "production",
                    "side": "input" if reference.internal_id in treated_ids else "output",
                    "position": 0,
                    "name": flow.entity.name,
                    "unit": flow.stored.name,
                }
                | _distribution(process, reference, flow, sign * scale)
            ]
            at = 1
            for e in exchanges:
                if e.internal_id == reference.internal_id or e.internal_id in product_ids:
                    continue
                factor = factors[(flow.entity.id, e.internal_id)]
                rows.extend(
                    self._rows(process, e, flows[e.internal_id], factor, dataset=code, position=at)
                )
                at += 1
            out[(self.database, code)] = {
                "name": process.name,
                "reference product": flow.entity.name,
                "unit": flow.stored.name,
                "location": location,
                "classifications": [("Category", process.category)] if process.category else [],
                "type": "process",
                "comment": process.description,
                "exchanges": rows,
            } | self._url(process)
        return out

    def _rows(
        self,
        process: o.Process,
        e: o.Exchange,
        flow: _Flow,
        factor: float,
        *,
        dataset: str,
        position: int,
    ) -> list[Dataset]:
        if reason := exchange_refusal(e, flow.entity):
            raise NotSupported(f"{process.name!r} takes {flow.entity.name!r} as {reason}")
        amount, scale = self._amount(process, e, flow)
        kind = flow.entity.flow_type
        if kind == o.FlowType.ELEMENTARY_FLOW:
            return [
                {
                    "input": (self.biosphere, flow.entity.id),
                    "amount": amount * factor,
                    "type": "biosphere",
                    "side": "input" if e.is_input else "output",
                    "position": position,
                    "name": flow.entity.name,
                    "unit": flow.stored.name,
                }
                | _distribution(process, e, flow, scale * factor)
            ]
        provider = self._provider(
            process, e, flow, dataset=dataset, position=position, amount=amount
        )
        if provider is None:
            return []
        sign = -1.0 if (e.is_avoided_product or kind == o.FlowType.WASTE_FLOW) else 1.0
        return [
            {
                "input": (self.database, f"{provider}_{flow.entity.id}"),
                "amount": amount * factor * sign,
                "type": "technosphere",
                "side": "input" if e.is_input else "output",
                "position": position,
                "name": flow.entity.name,
                "unit": flow.stored.name,
            }
            | _distribution(process, e, flow, scale * factor * sign)
        ]

    def biosphere_flows(self) -> dict[Key, Dataset]:
        """The elementary flows as biosphere datasets."""
        out: dict[Key, Dataset] = {}
        for flow in self.flows.values():
            if flow.entity.flow_type != o.FlowType.ELEMENTARY_FLOW:
                continue
            categories = _categories(flow.entity.category)
            out[(self.biosphere, flow.entity.id)] = {
                "name": flow.entity.name,
                "unit": flow.stored.name,
                "categories": categories,
                "type": _flow_type(categories),
                "CAS number": flow.entity.cas,
                "synonyms": list(flow.entity.synonyms or []),
            }
        return out

    def methods(self) -> list[ImportedMethod]:
        """Every impact category of every method, its factors in canonical units. A factor that
        names a location is set apart and counted, and the category applies the factor without a
        location to every process; a flow the category characterises only with factors that name
        a location has no factor to apply and is not supported."""
        out: list[ImportedMethod] = []
        for method in self.reader.read_each(o.ImpactMethod):
            for ref in method.impact_categories or []:
                category = self.reader.read(o.ImpactCategory, _ref_id(ref, method.name or ""))
                if category is None:
                    raise Invalid(f"method {method.name!r} names a category the package lacks")
                owner = f"a factor of {category.name!r}"
                factors: list[tuple[Key, float]] = []
                located: dict[Key, str] = {}
                set_apart = 0
                for f in category.impact_factors or []:
                    flow = self.flows[_ref_id(f.flow, owner)]
                    if _ref_id(f.flow_property, owner) != flow.reference_property:
                        raise NotSupported(
                            f"{category.name!r} gives {flow.entity.name!r} in flow property "
                            f"{_ref_name(f.flow_property, owner)!r}, not its reference property"
                        )
                    key = (self.biosphere, flow.entity.id)
                    if f.location is not None:
                        located.setdefault(key, flow.entity.name)
                        set_apart += 1
                        continue
                    unit = units.by_symbol(_ref_name(f.unit, owner))
                    factors.append((key, float(f.value or 0.0) / unit.factor))
                applied = {key for key, _ in factors}
                for key, flow_name in located.items():
                    if key not in applied:
                        raise NotSupported(
                            f"{method.name or ''!r} > {category.name or ''!r} characterises "
                            f"{flow_name!r} only with factors that name a location"
                        )
                out.append(
                    ImportedMethod(
                        key=(self.database, method.name or "", category.name or ""),
                        unit=category.ref_unit or "",
                        factors=factors,
                        set_apart=set_apart,
                    )
                )
        return out


def read_background(path: Path, name: str, *, foreground: frozenset[str]) -> Import:
    """Read an openLCA package into the datasets, flows and methods of a database called name;
    the processes named in foreground install nothing."""
    with ZipReader(str(path)) as reader:
        state = _Reader(reader, name, foreground)
        datasets: dict[Key, Dataset] = {}
        for process in state.processes:
            datasets.update(state.datasets(process))
        return Import(
            database=name,
            biosphere=state.biosphere,
            datasets=datasets,
            flows=state.biosphere_flows(),
            methods=state.methods(),
            processes=len(state.processes),
            unlinked=state.unlinked,
        )


def require_linked(imported: Import) -> None:
    """Invalid while any input of the import has no provider, naming each."""
    if imported.unlinked:
        named = "; ".join(
            f"{u.process!r} takes {u.flow!r} and {u.reason}" for u in imported.unlinked
        )
        raise Invalid(f"{len(imported.unlinked)} inputs are unlinked: {named}")
