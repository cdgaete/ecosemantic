"""A portable product system on disk: openLCA half, sidecar, change log and version snapshots."""

from __future__ import annotations

import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.jsonld import BASE_TAG, Stated, read_jsonld, stated_base, write_jsonld
from ecosemantic.package.log import next_entry, read_log, write_log
from ecosemantic.package.sidecar import (
    SIDECAR_DIR,
    ActivityRecord,
    Identities,
    ProjectRecord,
    Sidecar,
    read_sidecar,
    write_sidecar,
)
from ecosemantic.ports.resolver import Resolver
from ecosemantic.ports.types import LogEntry, Source

VERSIONS_DIR = "versions"


def _versions(root: Path) -> Path:
    return root / SIDECAR_DIR / VERSIONS_DIR


def _snapshot(root: Path, product_system: ProductSystem) -> None:
    _versions(root).mkdir(parents=True, exist_ok=True)
    (_versions(root) / f"{product_system.hash}.json").write_text(
        product_system.model_dump_json(), encoding="utf-8"
    )


def read_version(root: Path, version_hash: str) -> ProductSystem:
    """The product system state a content hash names, as the package snapshotted it."""
    path = _versions(root) / f"{version_hash}.json"
    if not path.is_file():
        raise NotFound(f"no version {version_hash} in {root}")
    return ProductSystem.model_validate_json(path.read_text(encoding="utf-8"))


def read_package(root: Path) -> tuple[ProductSystem, list[LogEntry]]:
    """The product system a package holds, its hash set to the state read, and its log."""
    sidecar = read_sidecar(root)
    product_system = read_jsonld(root, sidecar)
    product_system.hash = content_hash(product_system)
    return product_system, read_log(root)


def _base(root: Path, product_system: ProductSystem) -> tuple[ProductSystem | None, list[LogEntry]]:
    """The state a write may build on; Conflict unless the write's claim matches the package."""
    if not (root / SIDECAR_DIR).is_dir():
        if product_system.hash is not None:
            raise Conflict(f"no package at {root}, yet the write claims base {product_system.hash}")
        return None, []
    before, log = read_package(root)
    if product_system.hash is None:
        raise Conflict(
            f"product system {product_system.id} is stored already, at {before.hash}; a write "
            "that names no base adds a new system only"
        )
    if product_system.hash != before.hash:
        raise Conflict(
            f"package {root} is at {before.hash}, the write is based on {product_system.hash}"
        )
    return before, log


def _sidecar(product_system: ProductSystem, entry: LogEntry, identities: Identities) -> Sidecar:
    """What openLCA cannot hold for one stored state, keyed to the log entry's result hash."""
    return Sidecar(
        product_system=ProjectRecord(
            id=product_system.id,
            name=product_system.name,
            description=product_system.description,
            notes=product_system.notes,
            database=product_system.database,
            hash=entry.result_hash,
            processes=[ActivityRecord(id=a.id, code=a.code) for a in product_system.processes],
        ),
        identities=identities,
        scenarios=product_system.scenarios,
        metadata={a.id: a.metadata for a in product_system.processes},
    )


def write_package(
    product_system: ProductSystem,
    root: Path,
    actor: Actor,
    message: str,
    resolver: Resolver,
    source: Source = "mcp",
    now: datetime | None = None,
    linked: Mapping[uuid.UUID, ProductSystem] | None = None,
    tagged: Stated | None = None,
) -> LogEntry:
    """Write the system as a package and append one log entry; its hash names the stored state.
    `linked` holds each system it links, as it stood at the pin. The base tag names `tagged`,
    or else the entry appended."""
    before, log = _base(root, product_system)
    entry = next_entry(log, actor, source, before, product_system, message, now)
    stated = tagged if tagged is not None else Stated(seq=entry.seq, hash=entry.result_hash)
    identities = write_jsonld(product_system, root, resolver, linked, state=stated)
    stored = product_system.model_copy(update={"hash": entry.result_hash})
    write_sidecar(root, _sidecar(product_system, entry, identities))
    write_log(root, [*log, entry])
    _snapshot(root, stored)
    return entry


def write_returned(
    exported_root: Path,
    root: Path,
    actor: Actor,
    resolver: Resolver,
    linked: Mapping[uuid.UUID, ProductSystem] | None = None,
    now: datetime | None = None,
    at_entry: int | None = None,
) -> LogEntry:
    """Store the package openLCA exported over the retained one; one entry sourced openlca. The
    export was taken at the log entry `at_entry` states, or else the one its base tag names;
    Invalid when neither names one, and Conflict for an entry the log does not hold at that
    hash and for any write since it."""
    before, log = read_package(root)
    last = log[-1].seq
    exported_at = at_entry
    if exported_at is None:
        stated = stated_base(exported_root, before.id)
        if stated is None:
            raise Invalid(
                f"the returned package names no entry it was exported at: its product system "
                f"{before.id} carries no {BASE_TAG} tag"
            )
        held = next((entry for entry in log if entry.seq == stated.seq), None)
        if held is None or held.result_hash != stated.hash:
            raise Conflict(f"{before.name!r} never reached entry #{stated.seq} at {stated.hash}")
        exported_at = stated.seq
    if not 1 <= exported_at <= last:
        raise Conflict(f"{before.name!r} has no entry #{exported_at}; its last is #{last}")
    since = [entry for entry in log if entry.seq > exported_at]
    if since:
        writes = "; ".join(f"#{entry.seq} {entry.message}" for entry in since)
        raise Conflict(
            f"{before.name!r} moved since the export at entry #{exported_at}: {writes}; "
            f"it is at entry #{last}"
        )
    after = read_jsonld(exported_root, read_sidecar(root))
    return write_package(
        after.model_copy(update={"hash": before.hash}),
        root,
        actor,
        "returned from openLCA",
        resolver,
        "openlca",
        now,
        linked=linked,
    )


def zip_package(root: Path, zip_path: Path) -> None:
    """The package directory as one zip file."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(root).as_posix())


def unzip_package(zip_path: Path, root: Path) -> None:
    """A zip file as a package directory."""
    with zipfile.ZipFile(zip_path) as zipped:
        zipped.extractall(root)
