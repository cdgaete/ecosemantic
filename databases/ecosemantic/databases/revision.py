"""EcoSemantic's revision of a publisher's release: the corrections the release records applied to
its records, and every elementary flow written in the canonical shape.

A correction renames or re-files a value of one release; a correction the publisher's own file no
longer matches fails the build, so a list stays true when a publisher fixes its data. The bundle a
build writes is the release with its corrections, its revision and the corrections in its
manifest.
"""

from __future__ import annotations

import csv
import json
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import cast, get_args

import olca_schema as o
from olca_schema.zipio import ZipReader, _folder_of_class

from ecosemantic.errors import Invalid
from ecosemantic.files import replace
from ecosemantic.package.canonical import canonical_flow_record
from ecosemantic.package.manifest import (
    MANIFEST,
    SCHEMA_VERSION,
    BaseDatabase,
    Correction,
    Entity,
    Manifest,
    write_manifest,
)

CORRECTION_COLUMNS = ("entity", "id", "field", "published", "corrected", "why")
_ENTITIES: dict[str, type[o.RootEntity]] = {
    name: cast(type[o.RootEntity], getattr(o, name)) for name in get_args(Entity)
}
Record = dict[str, object]


def _folder(entity: str) -> str:
    """The folder of a zip a release's record of an entity is held under."""
    return _folder_of_class(_ENTITIES[entity])


def _flow_members(staged: Path) -> set[str]:
    """The members of a package that hold an elementary flow or a product flow, as the package's
    reader names them."""
    folder = _folder("Flow")
    with ZipReader(str(staged)) as reader:
        return {f"{folder}/{flow_id}.json" for flow_id in reader.ids_of(o.Flow)}


def _correction(path: Path, record: dict[str, str]) -> Correction:
    """One correction a list holds, its entity checked against the entities a correction names."""
    entity = record["entity"]
    if entity not in _ENTITIES:
        raise Invalid(
            f"{path} holds a correction of {entity!r}; a correction names one of "
            f"{', '.join(_ENTITIES)}"
        )
    return Correction(
        entity=cast(Entity, entity),
        id=record["id"],
        field=record["field"],
        published=record["published"],
        corrected=record["corrected"],
        why=record["why"],
    )


def read_corrections(path: Path) -> tuple[Correction, ...]:
    """The corrections a list holds, in the order the list gives them."""
    with path.open(newline="", encoding="utf-8") as read:
        reader = csv.DictReader(read)
        if tuple(reader.fieldnames or ()) != CORRECTION_COLUMNS:
            raise Invalid(
                f"{path} holds the columns {reader.fieldnames}; a correction list holds "
                f"{', '.join(CORRECTION_COLUMNS)}"
            )
        return tuple(_correction(path, record) for record in reader)


def listed_corrections(directory: Path, name: str | None) -> tuple[Correction, ...]:
    """The corrections a profile's named list holds, and none when it names no list."""
    return () if name is None else read_corrections(directory / name)


def _correct(members: dict[str, bytes], correction: Correction) -> None:
    """Apply a correction to a member of the release, its published value checked first; a record
    the release lacks or a field holding another value is `Invalid`."""
    member = f"{_folder(correction.entity)}/{correction.id}.json"
    content = members.get(member)
    record = None if content is None else cast(Record, json.loads(content))
    found: object = None if record is None else record.get(correction.field)
    if found != correction.published:
        raise Invalid(
            f"correction of {correction.entity} {correction.id} {correction.field}: "
            f"expected {correction.published!r}, found {found!r}"
        )
    cast(Record, record)[correction.field] = correction.corrected
    members[member] = json.dumps(record).encode()


def revise(
    staged: Path,
    destination: Path,
    *,
    name: str,
    version: str,
    revision: int,
    corrections: Sequence[Correction],
    now: datetime,
) -> None:
    """Write `staged` as EcoSemantic's revision of a publisher's release at `destination`: every
    member copied but an existing manifest, each correction applied to its record, every elementary
    flow written in the canonical shape, and a manifest naming the release, its revision and its
    corrections written last. Invalid when a correction does not match the record it names; the
    file being written is removed either way."""
    flows = _flow_members(staged)
    revising = destination.with_name(f".{destination.name}.revising")
    revising.unlink(missing_ok=True)
    try:
        with (
            zipfile.ZipFile(staged) as source,
            zipfile.ZipFile(revising, "w", compression=zipfile.ZIP_DEFLATED) as target,
        ):
            members = {
                info.filename: source.read(info.filename)
                for info in source.infolist()
                if info.filename != MANIFEST
            }
            for correction in corrections:
                _correct(members, correction)
            for info in source.infolist():
                if info.filename == MANIFEST:
                    continue
                content = members[info.filename]
                if info.filename in flows:
                    record = cast(Record, json.loads(content))
                    content = json.dumps(canonical_flow_record(record)).encode()
                target.writestr(info, content)
        write_manifest(
            revising,
            Manifest(
                mode="release",
                name=name,
                version=version,
                schema_version=SCHEMA_VERSION,
                built_at=now,
                base=BaseDatabase(name=name, version=version),
                systems=[],
                datasets=[],
                revision=revision,
                corrections=list(corrections),
            ),
        )
        replace(revising, destination)
    finally:
        revising.unlink(missing_ok=True)
