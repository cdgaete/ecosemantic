"""A working database: every stored system as its package, zipped whole inside the bundle, its
openLCA half merged at the root beside the base processes the systems reach."""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from ecosemantic.compute.links import pins
from ecosemantic.model import units
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import BackgroundRef, split_native_id
from ecosemantic.package.base import BaseBundle
from ecosemantic.package.gates import gate, gathered, refuse_existing
from ecosemantic.package.jsonld import parameter_prefix
from ecosemantic.package.manifest import (
    SCHEMA_VERSION,
    BaseDatabase,
    Manifest,
    SystemEntry,
    read_manifest,
    write_manifest,
)
from ecosemantic.package.sidecar import SIDECAR_DIR
from ecosemantic.package.wholeness import require_whole
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import Restored

SYSTEMS_DIR = "ecosemantic/systems"
DESCRIPTOR = "olca-schema.json"


Redefinition = dict[str, object]
Link = dict[str, dict[str, object]]


def _linked_values(
    system: ProductSystem, by_id: dict[uuid.UUID, ProductSystem], seen: set[uuid.UUID]
) -> list[Redefinition]:
    out: list[Redefinition] = []
    for ref in pins(system):
        if ref.product_system_id in seen:
            continue
        seen.add(ref.product_system_id)
        linked = by_id[ref.product_system_id]
        chosen = linked.case(ref.case).values if ref.case is not None else {}
        prefix = parameter_prefix(linked)
        out += [
            {"name": f"{prefix}{p.name}", "value": chosen.get(p.name, p.value)}
            for p in linked.parameters
            if p.formula is None
        ]
        out += _linked_values(linked, by_id, seen)
    return out


def _with_links(system: dict, redefinitions: list[Redefinition]) -> None:
    if not redefinitions:
        return
    sets = system.get("parameterSets") or []
    if not sets:
        system["parameterSets"] = [
            {"name": "base", "isBaseline": True, "parameters": redefinitions}
        ]
        return
    for chosen in sets:
        chosen["parameters"] = [*chosen.get("parameters", []), *redefinitions]


def _base_links(process: dict, base: BaseBundle) -> list[Link]:
    out: list[Link] = []
    for exchange in process.get("exchanges", []):
        provider = exchange.get("defaultProvider", {}).get("@id")
        if exchange.get("isInput") and provider in base.processes:
            out.append(
                {
                    "provider": {"@type": "Process", "@id": provider},
                    "flow": {"@type": "Flow", "@id": exchange["flow"]["@id"]},
                    "process": {"@type": "Process", "@id": process["@id"]},
                    "exchange": {"internalId": exchange["internalId"]},
                }
            )
    return out


def _with_base(
    data: bytes, package: zipfile.ZipFile, base: BaseBundle, redefinitions: list[Redefinition]
) -> bytes:
    system = json.loads(data)
    _with_links(system, redefinitions)
    links: list[Link] = []
    for ref in system.get("processes", []):
        member = f"processes/{ref['@id']}.json"
        if member in package.namelist():
            links += _base_links(json.loads(package.read(member)), base)
    reached = base.closure({str(link["provider"]["@id"]) for link in links})
    held = {ref["@id"] for ref in system.get("processes", [])}
    system["processes"] = [
        *system.get("processes", []),
        *({"@type": "Process", "@id": i} for i in sorted(reached - held)),
    ]
    system["processLinks"] = [*system.get("processLinks", []), *links, *base.links(reached)]
    return json.dumps(system).encode()


def _merged(
    member: str,
    data: bytes,
    base: BaseBundle,
    package: zipfile.ZipFile,
    redefinitions: list[Redefinition],
) -> bytes:
    if member.startswith("product_systems/"):
        return _with_base(data, package, base, redefinitions)
    if not member.startswith("processes/"):
        return data
    process = json.loads(data)
    for exchange in process.get("exchanges", []):
        flow_id = exchange.get("flow", {}).get("@id")
        if flow_id in base.flows:
            unit = units.by_symbol(exchange["unit"]["name"]).name
            unit_ref, property_ref = base.flow_unit(flow_id, unit)
            exchange["unit"], exchange["flowProperty"] = unit_ref.to_dict(), property_ref.to_dict()
    return json.dumps(process).encode()


def _assemble(
    systems: list[ProductSystem],
    packages: dict[uuid.UUID, Path],
    base_bundle: Path,
    manifest: Manifest,
    destination: Path,
) -> None:
    starts = {
        split_native_id(e.input.id)[0]
        for s in systems
        for p in s.processes
        for e in p.exchanges
        if isinstance(e.input, BackgroundRef)
    }
    by_id = {s.id: s for s in systems}
    linked = {s.id: _linked_values(s, by_id, set()) for s in systems}
    staged = destination.with_name(destination.name + ".partial")
    staged.unlink(missing_ok=True)
    try:
        with (
            BaseBundle(base_bundle) as base,
            zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as target,
        ):
            target.writestr(DESCRIPTOR, '{"version": 2}')
            written = base.copy(target, base.closure(starts))
            for system_id, package in packages.items():
                target.write(package, f"{SYSTEMS_DIR}/{system_id}.zip")
                with zipfile.ZipFile(package) as zipped:
                    for member in zipped.namelist():
                        if member == DESCRIPTOR or member.startswith(f"{SIDECAR_DIR}/"):
                            continue
                        if member in written:
                            continue
                        target.writestr(
                            member,
                            base.read(member)
                            if base.holds(member)
                            else _merged(
                                member, zipped.read(member), base, zipped, linked[system_id]
                            ),
                        )
                        written.add(member)
        require_whole(staged)
        write_manifest(staged, manifest)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


async def build_working(
    storage: StoragePort,
    base_bundle: Path,
    base: BaseDatabase,
    name: str,
    version: str,
    destination: Path,
    now: datetime,
) -> Manifest:
    """Write every stored system, whole, beside the base processes it reaches."""
    refuse_existing(destination)
    systems = await gathered(storage)
    await gate(storage, systems, base.name, render=False)
    manifest = Manifest(
        mode="working",
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
                cases=[c.name for c in s.cases],
            )
            for s in systems
        ],
        datasets=[],
    )
    with tempfile.TemporaryDirectory() as work:
        packages = {}
        for system in systems:
            packages[system.id] = Path(work) / f"{system.id}.zip"
            await storage.export_package(system.id, packages[system.id])
        await asyncio.to_thread(_assemble, systems, packages, base_bundle, manifest, destination)
    return manifest


def foreground_processes(bundle: Path) -> frozenset[str]:
    """The ids of the processes the bundle's product systems own, which install nothing."""
    manifest = read_manifest(bundle)
    found: set[str] = set()
    with zipfile.ZipFile(bundle) as zipped:
        for entry in manifest.systems:
            with zipfile.ZipFile(
                io.BytesIO(zipped.read(f"{SYSTEMS_DIR}/{entry.product_system_id}.zip"))
            ) as package:
                found |= {
                    Path(member).stem
                    for member in package.namelist()
                    if member.startswith("processes/") and member.endswith(".json")
                }
    return frozenset(found)


def write_base_part(bundle: Path, destination: Path) -> None:
    """Write the base a working bundle carries as a bundle of its own: every process no
    system of it owns, the records those name and the impact methods."""
    manifest = read_manifest(bundle)
    with (
        BaseBundle(bundle, foreground_processes(bundle)) as base,
        zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        target.writestr(DESCRIPTOR, '{"version": 2}')
        base.copy(target, set(base.processes))
    require_whole(destination)
    write_manifest(
        destination,
        Manifest(
            mode="release",
            name=manifest.base.name,
            version=manifest.base.version,
            schema_version=SCHEMA_VERSION,
            built_at=manifest.built_at,
            base=manifest.base,
            systems=[],
            datasets=[],
        ),
    )


async def restore_systems(bundle: Path, storage: StoragePort) -> dict[uuid.UUID, Restored]:
    """Each system of a working bundle restored into the store: added, or left as it is."""
    manifest = read_manifest(bundle)
    out: dict[uuid.UUID, Restored] = {}
    with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(bundle) as zipped:
        for entry in manifest.systems:
            package = Path(work) / f"{entry.product_system_id}.zip"
            package.write_bytes(zipped.read(f"{SYSTEMS_DIR}/{entry.product_system_id}.zip"))
            out[entry.product_system_id] = await storage.restore_package(package)
    return out
