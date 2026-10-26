"""A product system as one model package, each system it links beside it at the pin: written from
the model, read back through a storage port."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path

from ecosemantic.compute.links import pinned, pins
from ecosemantic.errors import Conflict, Invalid
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.jsonld import Stated, read_jsonld
from ecosemantic.package.package import read_package, unzip_package, write_package, zip_package
from ecosemantic.package.sidecar import SIDECAR_DIR, read_sidecar
from ecosemantic.ports.resolver import Resolver
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import LogEntry

LINKED_DIR = "linked"
DESCRIPTOR = "olca-schema.json"


def _merge_linked(root: Path, linked_root: Path, product_system_id: uuid.UUID) -> None:
    """A linked system's package merged into the model package's: its openLCA entities beside the
    root's, an entity both hold kept once, and its sidecar under linked/<id>/."""
    for path in sorted(linked_root.rglob("*")):
        relative = path.relative_to(linked_root)
        if not path.is_file() or relative.parts[0] == SIDECAR_DIR or relative.name == DESCRIPTOR:
            continue
        target = root / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copytree(
        linked_root / SIDECAR_DIR, root / LINKED_DIR / str(product_system_id) / SIDECAR_DIR
    )


def stated_at(system: ProductSystem, log: list[LogEntry]) -> Stated:
    """The log entry a stored system's state is, which its export's base tag names; Conflict
    when the log moved past the state read."""
    last = log[-1]
    if last.result_hash != system.hash:
        raise Conflict(f"{system.name!r} moved while it was read for export; export it again")
    return Stated(seq=last.seq, hash=last.result_hash)


def export_model_package(
    system: ProductSystem,
    destination: Path,
    actor: Actor,
    resolver: Resolver,
    linked: Mapping[uuid.UUID, ProductSystem] | None = None,
    at: Stated | None = None,
) -> LogEntry:
    """Write the system as a fresh package, zipped at the destination, with every system it
    reaches written beside it at its pin; the entry names the system's state. `linked` holds
    every system the system reaches, as it stood at the pin, and the base tag names `at`, the
    stored entry the system's state is, or else the package's own first entry."""
    reached = dict(linked or {})
    with tempfile.TemporaryDirectory() as work:
        root = Path(work) / "root"
        entry = write_package(
            system.model_copy(update={"hash": None}),
            root,
            actor,
            "exported",
            resolver,
            linked=reached,
            tagged=at,
        )
        for product_system_id, document in reached.items():
            linked_root = Path(work) / str(product_system_id)
            write_package(
                document.model_copy(update={"hash": None}),
                linked_root,
                actor,
                "exported",
                resolver,
                linked=reached,
            )
            _merge_linked(root, linked_root, product_system_id)
        zip_package(root, destination)
    return entry


def _read_model_package(source: Path) -> tuple[ProductSystem, list[ProductSystem]]:
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        unzip_package(source, root)
        system, _ = read_package(root)
        folder = root / LINKED_DIR
        linked = []
        for path in sorted(folder.iterdir()) if folder.is_dir() else []:
            document = read_jsonld(root, read_sidecar(path))
            linked.append(document.model_copy(update={"hash": content_hash(document)}))
    return system.model_copy(update={"hash": None}), linked


def _in_link_order(linked: list[ProductSystem]) -> list[ProductSystem]:
    """The linked systems ordered so each comes after every system it links; Invalid for a set
    whose links close a cycle."""
    ordered: list[ProductSystem] = []
    pending = list(linked)
    while pending:
        waiting = {d.id for d in pending}
        ready = [d for d in pending if all(r.product_system_id not in waiting for r in pins(d))]
        if not ready:
            raise Invalid(f"the model package's linked systems link in a cycle: {sorted(waiting)}")
        ordered += ready
        pending = [d for d in pending if d not in ready]
    return ordered


async def _store_linked(
    system: ProductSystem, linked: list[ProductSystem], storage: StoragePort, actor: Actor
) -> None:
    """Each linked system the store lacks, stored as an import once its hash is its pin; one the
    store holds at the pin left as it is; Conflict for one the store holds at other states."""
    pinned_at = {r.product_system_id: pinned(r) for d in [system, *linked] for r in pins(d)}
    held = {summary.id for summary in await storage.list_product_systems()}
    for document in _in_link_order(linked):
        pin = pinned_at.get(document.id)
        if pin is None:
            raise Invalid(f"the model package carries {document.name!r}, which nothing in it links")
        if document.hash != pin:
            raise Invalid(
                f"{document.name!r} in the model package is at {document.hash}, "
                f"and its link pins {pin}"
            )
        if document.id in held:
            reached = {entry.result_hash for entry in await storage.log(document.id)}
            if pin not in reached:
                raise Conflict(
                    f"{document.name!r} ({document.id}) is stored, and its log never reached "
                    f"{pin}, the state the model package links"
                )
            continue
        await storage.put_product_system(
            document.model_copy(update={"hash": None}),
            actor,
            f"imported product system {document.name}",
            source="import",
        )


async def import_model_package(
    source: Path, storage: StoragePort, actor: Actor
) -> tuple[ProductSystem, LogEntry]:
    """Store the product system a model package carries as a new one, logged as an import,
    after each system it links that the store lacks."""
    if not source.is_file():
        raise Invalid(f"{str(source)!r} is not a file")
    system, linked = await asyncio.to_thread(_read_model_package, source)
    await _store_linked(system, linked, storage, actor)
    entry = await storage.put_product_system(
        system, actor, f"imported product system {system.name}", source="import"
    )
    return system, entry
