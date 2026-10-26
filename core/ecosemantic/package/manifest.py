"""The manifest a database bundle carries, and the changelog between two releases."""

from __future__ import annotations

import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from ecosemantic.errors import Invalid

Mode = Literal["working", "release"]
SCHEMA_VERSION = 1
MANIFEST = "ecosemantic-database.json"
CHANGELOG = "changelog.json"


class BaseDatabase(BaseModel):
    """The database a bundle's systems were modelled on, and the build of it they were stamped
    with: none for a base bundle, whose build is computed when it is installed."""

    name: str
    version: str
    fingerprint: str | None = None


class SystemEntry(BaseModel):
    """A product system a bundle carries or renders, at the state it was built from."""

    product_system_id: uuid.UUID
    name: str
    content_hash: str
    cases: list[str]


class DatasetEntry(BaseModel):
    """A rendered dataset: its id, the process and case it renders, and the pin of that case."""

    id: str
    product_system_id: uuid.UUID
    process_code: str
    case: str
    pin: str


class Manifest(BaseModel):
    """What a bundle is: its mode, name, version, base, systems and rendered datasets."""

    mode: Mode
    name: str
    version: str
    schema_version: int
    built_at: datetime
    base: BaseDatabase
    systems: list[SystemEntry]
    datasets: list[DatasetEntry]


class Changelog(BaseModel):
    """How a release's datasets differ from the previous release's, by id and pin."""

    previous: str | None
    base_changed: bool
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]


def write_manifest(bundle: Path, manifest: Manifest) -> None:
    """Append the manifest to a bundle as its last member."""
    with zipfile.ZipFile(bundle, "a", compression=zipfile.ZIP_DEFLATED) as zipped:
        if MANIFEST in zipped.namelist():
            raise Invalid(f"{bundle.name} already carries a manifest")
        zipped.writestr(MANIFEST, manifest.model_dump_json(indent=1))


def read_manifest(bundle: Path) -> Manifest:
    """The manifest of a bundle, or Invalid naming what is missing or unreadable."""
    with zipfile.ZipFile(bundle) as zipped:
        if MANIFEST not in zipped.namelist():
            raise Invalid(f"{bundle.name} carries no {MANIFEST}; it is not a complete bundle")
        raw = zipped.read(MANIFEST)
    try:
        manifest = Manifest.model_validate_json(raw)
    except ValidationError as error:
        first = error.errors(include_url=False)[0]
        field = ".".join(str(part) for part in first["loc"])
        raise Invalid(f"{bundle.name} manifest: {field}: {first['msg']}") from error
    if manifest.schema_version != SCHEMA_VERSION:
        raise Invalid(
            f"{bundle.name} manifest names schema_version {manifest.schema_version}; "
            f"this version reads {SCHEMA_VERSION}"
        )
    return manifest


def changelog(previous: Manifest | None, current: Manifest) -> Changelog:
    """Each dataset of the current release against the previous one, by id and pin."""
    before = {d.id: d.pin for d in previous.datasets} if previous is not None else {}
    now = {d.id: d.pin for d in current.datasets}
    return Changelog(
        previous=previous.version if previous is not None else None,
        base_changed=previous is not None and previous.base != current.base,
        added=sorted(i for i in now if i not in before),
        removed=sorted(i for i in before if i not in now),
        changed=sorted(i for i in now if i in before and before[i] != now[i]),
        unchanged=sorted(i for i in now if i in before and before[i] == now[i]),
    )
