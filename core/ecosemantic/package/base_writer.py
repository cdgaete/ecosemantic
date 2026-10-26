"""Base rows written as a whole openLCA JSON-LD bundle under openLCA ids."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import olca_schema as o
from olca_schema.zipio import ZipWriter

from ecosemantic.errors import Conflict, Invalid, NotSupported
from ecosemantic.model.entities import Uncertainty
from ecosemantic.model.refs import (
    Scheme,
    keygen,
    olca_elementary_flow_id,
    olca_process_id,
    olca_product_flow_id,
)
from ecosemantic.package.jsonld import UnitTable, location_entity
from ecosemantic.package.manifest import SCHEMA_VERSION, BaseDatabase, Manifest, write_manifest
from ecosemantic.package.olca import to_olca_uncertainty
from ecosemantic.package.wholeness import require_whole
from ecosemantic.ports.types import FlowType

ExchangeKind = Literal["production", "technosphere", "biosphere"]


@dataclass(frozen=True)
class BaseExchange:
    """One exchange of a base dataset: its kind, its target and its amount."""

    kind: ExchangeKind
    input: str
    amount: float
    uncertainty: Uncertainty | None


@dataclass(frozen=True)
class BaseDataset:
    """A process of a base database, its exchanges and the ids that name it."""

    code: str
    native: str
    name: str
    reference_product: str
    unit: str
    location: str
    comment: str | None
    url: str | None
    exchanges: tuple[BaseExchange, ...]


@dataclass(frozen=True)
class BaseFlow:
    """An elementary flow of a base database."""

    code: str
    name: str
    unit: str
    categories: tuple[str, ...]
    type: FlowType
    cas: str | None


@dataclass(frozen=True)
class BaseMethod:
    """An impact method: its key, its unit and a factor per elementary flow code."""

    key: tuple[str, ...]
    unit: str
    factors: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class BaseRows:
    """Everything a base bundle holds, before openLCA ids are derived."""

    datasets: tuple[BaseDataset, ...]
    flows: tuple[BaseFlow, ...]
    methods: tuple[BaseMethod, ...]


@dataclass(frozen=True)
class Written:
    """What one bundle write produced."""

    bundle: Path
    processes: int
    flows: int
    methods: int


class _Builder:
    def __init__(self, scheme: Scheme, name: str, rows: BaseRows) -> None:
        self.scheme = scheme
        self.name = name
        self.rows = rows
        self.by_code = {dataset.code: dataset for dataset in rows.datasets}
        self.flow_units = {flow.code: flow.unit for flow in rows.flows}
        self.units = UnitTable()
        self.locations: dict[str, o.Location] = {}
        self.sources: dict[str, o.Source] = {}
        self.flows: dict[str, o.Flow] = {}
        self.resources: set[str] = set()
        self.unknown_units: set[str] = set()

    def _refs(self, unit: str) -> tuple[o.Ref, o.Ref] | None:
        try:
            return self.units.refs(unit)
        except NotSupported:
            self.unknown_units.add(unit)
            return None

    def _product(self, dataset: BaseDataset) -> o.Ref | None:
        flow_id = olca_product_flow_id(self.scheme, dataset.native)
        refs = self._refs(dataset.unit)
        if refs is None:
            return None
        self.flows.setdefault(
            flow_id,
            o.Flow(
                id=flow_id,
                name=dataset.reference_product,
                flow_type=o.FlowType.PRODUCT_FLOW,
                flow_properties=[
                    o.FlowPropertyFactor(
                        flow_property=refs[1], conversion_factor=1.0, is_ref_flow_property=True
                    )
                ],
            ),
        )
        return o.Ref(ref_type=o.RefType.Flow, id=flow_id, name=dataset.reference_product)

    def elementary(self) -> None:
        for flow in self.rows.flows:
            refs = self._refs(flow.unit)
            if refs is None:
                continue
            categories = list(flow.categories)
            flow_id = olca_elementary_flow_id(self.scheme, flow.code)
            if flow.type == "natural resource":
                self.resources.add(flow_id)
                below = categories[1:] if categories[:1] == ["natural resource"] else categories
                categories = ["Resource", *below]
            self.flows[flow_id] = o.Flow(
                id=flow_id,
                name=flow.name,
                flow_type=o.FlowType.ELEMENTARY_FLOW,
                category="/".join(["Elementary flows", *categories]),
                cas=flow.cas,
                flow_properties=[
                    o.FlowPropertyFactor(
                        flow_property=refs[1], conversion_factor=1.0, is_ref_flow_property=True
                    )
                ],
            )

    def _exchange(self, n: int, exchange: BaseExchange, dataset: BaseDataset) -> o.Exchange:
        amount = exchange.amount
        uncertainty = to_olca_uncertainty(exchange.uncertainty)
        if exchange.kind == "production":
            refs = self._refs(dataset.unit)
            return o.Exchange(
                internal_id=n,
                flow=self._product(dataset),
                amount=amount,
                is_input=False,
                is_quantitative_reference=True,
                unit=refs[0] if refs else None,
                flow_property=refs[1] if refs else None,
                uncertainty=uncertainty,
            )
        if exchange.kind == "technosphere":
            provider = self.by_code.get(exchange.input)
            if provider is None:
                raise Invalid(
                    f"{dataset.name!r} takes an input no dataset provides: {exchange.input}"
                )
            refs = self._refs(provider.unit)
            return o.Exchange(
                internal_id=n,
                flow=self._product(provider),
                amount=amount,
                is_input=True,
                default_provider=o.Ref(
                    ref_type=o.RefType.Process,
                    id=olca_process_id(self.scheme, provider.native),
                ),
                unit=refs[0] if refs else None,
                flow_property=refs[1] if refs else None,
                uncertainty=uncertainty,
            )
        if exchange.kind == "biosphere":
            if exchange.input not in self.flow_units:
                raise Invalid(f"{dataset.name!r} takes a flow the rows lack: {exchange.input}")
            flow_id = olca_elementary_flow_id(self.scheme, exchange.input)
            refs = self._refs(self.flow_units[exchange.input])
            return o.Exchange(
                internal_id=n,
                flow=o.Ref(ref_type=o.RefType.Flow, id=flow_id),
                amount=amount,
                is_input=flow_id in self.resources,
                unit=refs[0] if refs else None,
                flow_property=refs[1] if refs else None,
                uncertainty=uncertainty,
            )
        raise NotSupported(f"{dataset.name!r} carries an exchange of type {exchange.kind!r}")

    def processes(self) -> list[o.Process]:
        out = []
        for dataset in self.rows.datasets:
            location, entity = location_entity(dataset.location)
            self.locations.setdefault(entity.id, entity)
            exchanges = [
                self._exchange(n, exchange, dataset)
                for n, exchange in enumerate(dataset.exchanges, start=1)
            ]
            documentation = None
            if dataset.url is not None:
                source = o.Source(
                    id=keygen("source", dataset.url), name=dataset.url, url=dataset.url
                )
                self.sources[source.id] = source
                documentation = o.ProcessDocumentation(
                    publication=o.Ref(ref_type=o.RefType.Source, id=source.id, name=source.name)
                )
            out.append(
                o.Process(
                    id=olca_process_id(self.scheme, dataset.native),
                    name=dataset.name,
                    description=dataset.comment,
                    process_type=o.ProcessType.UNIT_PROCESS,
                    location=location,
                    exchanges=exchanges,
                    process_documentation=documentation,
                    last_internal_id=len(exchanges),
                )
            )
        return out

    def _factor(self, code: str, value: float) -> o.ImpactFactor:
        unit, flow_property = self.units.refs(self.flow_units[code])
        return o.ImpactFactor(
            flow=o.Ref(ref_type=o.RefType.Flow, id=olca_elementary_flow_id(self.scheme, code)),
            flow_property=flow_property,
            unit=unit,
            value=value,
        )

    def methods(self) -> tuple[list[o.ImpactMethod], list[o.ImpactCategory]]:
        grouped: dict[str, list[o.Ref]] = {}
        categories = []
        for method in self.rows.methods:
            category = o.ImpactCategory(
                id=keygen(*method.key),
                name=" > ".join(method.key[2:]),
                ref_unit=method.unit,
                impact_factors=[self._factor(code, value) for code, value in method.factors],
            )
            categories.append(category)
            grouped.setdefault(method.key[1], []).append(
                o.Ref(ref_type=o.RefType.ImpactCategory, id=category.id, name=category.name)
            )
        methods = [
            o.ImpactMethod(id=keygen(self.name, method), name=method, impact_categories=refs)
            for method, refs in grouped.items()
        ]
        return methods, categories


def write_base_bundle(
    rows: BaseRows, *, scheme: Scheme, name: str, version: str, destination: Path, now: datetime
) -> Written:
    """Write the rows as a whole base bundle under openLCA ids; the bundle is complete only
    once its manifest is written."""
    if destination.exists():
        raise Conflict(f"{destination.name} exists; name another destination")
    builder = _Builder(scheme, name, rows)
    builder.elementary()
    processes = builder.processes()
    if builder.unknown_units:
        raise NotSupported(f"units the core does not know: {sorted(builder.unknown_units)}")
    methods, categories = builder.methods()
    staged = destination.with_name(destination.name + ".partial")
    staged.unlink(missing_ok=True)
    with ZipWriter(str(staged)) as writer:
        for entity in [
            *builder.units.entities(),
            *builder.locations.values(),
            *builder.sources.values(),
            *builder.flows.values(),
            *processes,
            *categories,
            *methods,
        ]:
            writer.write(entity)
    require_whole(staged)
    write_manifest(
        staged,
        Manifest(
            mode="release",
            name=name,
            version=version,
            schema_version=SCHEMA_VERSION,
            built_at=now,
            base=BaseDatabase(name=name, version=version),
            systems=[],
            datasets=[],
        ),
    )
    os.replace(staged, destination)
    return Written(
        bundle=destination,
        processes=len(processes),
        flows=len(builder.flows),
        methods=len(categories),
    )
