"""Build a BAFU zolca into one openLCA JSON-LD bundle, read back by the core's importer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ecosemantic.databases.bafu.profile import database_name
from ecosemantic.databases.revision import revise
from ecosemantic.databases.zolca.export.write import NotCarried, export
from ecosemantic.errors import Conflict
from ecosemantic.files import replace
from ecosemantic.package.background import Import, read_background
from ecosemantic.package.manifest import Correction


@dataclass(frozen=True)
class Built:
    """What a build wrote: the bundle, the records it holds by folder, the rows its package does
    not carry, and the import the core read the staged bundle as."""

    bundle: Path
    records: dict[str, int]
    not_carried: tuple[NotCarried, ...]
    imported: Import = field(repr=False)


def build(
    zolca: Path,
    *,
    version: str,
    out_dir: Path,
    revision: int,
    corrections: Sequence[Correction],
    now: datetime,
) -> Built:
    """Write a zolca as `<out_dir>/bafu-<version>.zip` and import it under `bafu-<version>`. The
    package is exported to a staging file beside the destination, revised into a second one, and
    moved into place only once the core reads it, so a bundle the core refuses leaves nothing under
    the final name; a destination that exists is `Conflict`."""
    destination = out_dir / f"{database_name(version)}.zip"
    staging = out_dir / f".bafu-{version}.staging.zip"
    revised = out_dir / f".bafu-{version}.revised.zip"
    if destination.exists():
        raise Conflict(f"{destination.name} exists; name another destination")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = export(zolca, staging)
    try:
        revise(
            staging,
            revised,
            name=database_name(version),
            version=version,
            revision=revision,
            corrections=corrections,
            now=now,
        )
        imported = read_background(revised, database_name(version), foreground=frozenset())
        replace(revised, destination)
    finally:
        staging.unlink(missing_ok=True)
        revised.unlink(missing_ok=True)
    return Built(
        bundle=destination,
        records=written.records,
        not_carried=written.not_carried,
        imported=imported,
    )
