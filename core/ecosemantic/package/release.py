"""A release: every stored system rendered under each of its cases, written as JSON-LD beside
the base processes it reaches, with its manifest and changelog."""

from __future__ import annotations

import asyncio
import os
import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import olca_schema as o

from ecosemantic.compute.render import (
    Rendered,
    case_label,
    cases_of,
    dataset_id,
    product_flow_id,
    render,
)
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Exchange, Process, ProductSystem
from ecosemantic.model.refs import (
    BackgroundRef,
    ElementaryFlowRef,
    ForegroundRef,
    SystemRef,
    split_native_id,
)
from ecosemantic.package.base import BaseBundle
from ecosemantic.package.gates import gate, gathered, refuse_existing
from ecosemantic.package.jsonld import UnitTable, location_entity
from ecosemantic.package.manifest import (
    CHANGELOG,
    SCHEMA_VERSION,
    BaseDatabase,
    DatasetEntry,
    Manifest,
    SystemEntry,
    changelog,
    read_manifest,
    write_manifest,
)
from ecosemantic.package.olca import to_olca_uncertainty
from ecosemantic.package.wholeness import require_whole
from ecosemantic.ports.storage import StoragePort


def _ref(kind: o.RefType, entity_id: str, name: str | None = None) -> o.Ref:
    return o.Ref(ref_type=kind, id=entity_id, name=name)


class _Writer:
    def __init__(
        self, base: BaseBundle, systems: Mapping[uuid.UUID, ProductSystem], version: str
    ) -> None:
        self.base = base
        self.systems = systems
        self.version = version
        self.units = UnitTable()
        self.locations: dict[str, o.Location] = {}
        self.flows: dict[str, o.Flow] = {}

    def _product(self, system: ProductSystem, process: Process) -> o.Ref:
        flow_id = product_flow_id(system.id, process.code)
        _, prop = self.units.refs(process.unit)
        self.flows.setdefault(
            flow_id,
            o.Flow(
                id=flow_id,
                name=process.reference_product,
                flow_type=o.FlowType.PRODUCT_FLOW,
                category=f"ecosemantic/{system.name}",
                flow_properties=[
                    o.FlowPropertyFactor(
                        flow_property=prop, conversion_factor=1.0, is_ref_flow_property=True
                    )
                ],
            ),
        )
        return _ref(o.RefType.Flow, flow_id, process.reference_product)

    def _exchange(
        self, system: ProductSystem, rendered: Rendered, process: Process, n: int, e: Exchange
    ) -> o.Exchange:
        out = o.Exchange(
            internal_id=n,
            amount=e.amount,
            uncertainty=to_olca_uncertainty(e.uncertainty),
            description=e.comment,
        )
        if e.type == "production":
            out.flow = self._product(system, process)
            out.unit, out.flow_property = self.units.refs(e.unit)
            out.is_input, out.is_quantitative_reference = False, True
            return out
        out.is_input = True
        if isinstance(e.input, ForegroundRef):
            target = system.process(e.input.code)
            out.flow = self._product(system, target)
            out.unit, out.flow_property = self.units.refs(e.unit)
            out.default_provider = _ref(
                o.RefType.Process, dataset_id(system.id, target.code, rendered.case)
            )
        elif isinstance(e.input, SystemRef):
            linked = self.systems[e.input.product_system_id]
            target = linked.process(linked.reference_process)
            out.flow = self._product(linked, target)
            out.unit, out.flow_property = self.units.refs(e.unit)
            out.default_provider = _ref(
                o.RefType.Process, dataset_id(linked.id, target.code, case_label(e.input.case))
            )
        elif isinstance(e.input, BackgroundRef):
            provider, flow_id = split_native_id(e.input.id)
            out.flow = _ref(o.RefType.Flow, flow_id)
            out.unit, out.flow_property = self.base.flow_unit(flow_id, e.unit)
            out.default_provider = _ref(o.RefType.Process, provider)
        elif isinstance(e.input, ElementaryFlowRef):
            out.flow = _ref(o.RefType.Flow, e.input.id)
            out.unit, out.flow_property = self.base.flow_unit(e.input.id, e.unit)
            out.is_input = self.base.is_resource(e.input.id)
        else:
            raise Invalid(f"{process.code} exchange {e.name!r} has an input a release cannot carry")
        return out

    def processes(self, rendered: Rendered) -> list[o.Process]:
        system = self.systems[rendered.product_system_id]
        out = []
        for process in rendered.processes:
            location, entity = location_entity(process.location)
            self.locations.setdefault(entity.id, entity)
            exchanges = [
                self._exchange(system, rendered, process, n, e)
                for n, e in enumerate(process.exchanges, start=1)
            ]
            out.append(
                o.Process(
                    id=dataset_id(system.id, process.code, rendered.case),
                    name=f"{process.name} | {rendered.case}",
                    description=(
                        f"product system {system.id} ({system.name}), process {process.code}, "
                        f"case {rendered.case}, pin {rendered.pin}, release {self.version}"
                    ),
                    process_type=o.ProcessType.UNIT_PROCESS,
                    location=location,
                    exchanges=exchanges,
                    last_internal_id=len(exchanges),
                )
            )
        return out

    def support(self) -> list[o.RootEntity]:
        return [*self.units.entities(), *self.locations.values(), *self.flows.values()]


def _folder(entity: o.RootEntity) -> str:
    return {
        o.UnitGroup: "unit_groups",
        o.FlowProperty: "flow_properties",
        o.Location: "locations",
        o.Flow: "flows",
        o.Process: "processes",
    }[type(entity)]


def _write(
    target: zipfile.ZipFile, base: BaseBundle, entities: list[o.RootEntity], written: set[str]
) -> None:
    for entity in entities:
        member = f"{_folder(entity)}/{entity.id}.json"
        if member in written:
            continue
        target.writestr(member, base.read(member) if base.holds(member) else entity.to_json())
        written.add(member)


def _assemble(
    systems: list[ProductSystem],
    base_bundle: Path,
    base: BaseDatabase,
    name: str,
    version: str,
    destination: Path,
    previous: Path | None,
    now: datetime,
) -> Manifest:
    by_id = {s.id: s for s in systems}
    renderings = [render(s, case) for s in systems for case in cases_of(s)]
    starts = {
        split_native_id(e.input.id)[0]
        for s in systems
        for p in s.processes
        for e in p.exchanges
        if isinstance(e.input, BackgroundRef)
    }
    staged = destination.with_name(destination.name + ".partial")
    staged.unlink(missing_ok=True)
    manifest = Manifest(
        mode="release",
        name=name,
        version=version,
        schema_version=SCHEMA_VERSION,
        built_at=now,
        base=base,
        systems=[
            SystemEntry(
                product_system_id=s.id,
                name=s.name,
                content_hash=s.hash or "",
                cases=[case_label(c) for c in cases_of(s)],
            )
            for s in systems
        ],
        datasets=[
            DatasetEntry(
                id=dataset_id(r.product_system_id, p.code, r.case),
                product_system_id=r.product_system_id,
                process_code=p.code,
                case=r.case,
                pin=r.pin,
            )
            for r in renderings
            for p in r.processes
        ],
    )
    try:
        with (
            BaseBundle(base_bundle) as bundle,
            zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as target,
        ):
            target.writestr("olca-schema.json", '{"version": 2}')
            written = bundle.copy(target, bundle.closure(starts))
            writer = _Writer(bundle, by_id, version)
            processes = [p for r in renderings for p in writer.processes(r)]
            _write(target, bundle, [*writer.support(), *processes], written)
            prior = read_manifest(previous) if previous is not None else None
            target.writestr(CHANGELOG, changelog(prior, manifest).model_dump_json(indent=1))
        require_whole(staged)
        write_manifest(staged, manifest)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    return manifest


async def build_release(
    storage: StoragePort,
    base_bundle: Path,
    base: BaseDatabase,
    name: str,
    version: str,
    destination: Path,
    previous: Path | None,
    now: datetime,
) -> Manifest:
    """Render every stored system under each of its cases and write the release; nothing is
    written unless every system passes the gates and the bundle is whole."""
    refuse_existing(destination)
    systems = await gathered(storage)
    await gate(storage, systems, base.name, render=True)
    return await asyncio.to_thread(
        _assemble, systems, base_bundle, base, name, version, destination, previous, now
    )
