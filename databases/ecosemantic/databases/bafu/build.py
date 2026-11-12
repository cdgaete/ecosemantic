"""Build a BAFU zolca into one openLCA JSON-LD bundle, read back by the core's importer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ecosemantic.databases.bafu.profile import database_name
from ecosemantic.databases.zolca.export.write import NotCarried, export
from ecosemantic.errors import Conflict
from ecosemantic.files import replace
from ecosemantic.package.background import Import, read_background


@dataclass(frozen=True)
class Built:
    """What a build wrote: the bundle, the records it holds by folder, the rows its package does
    not carry, and the import the core read the staged bundle as."""

    bundle: Path
    records: dict[str, int]
    not_carried: tuple[NotCarried, ...]
    imported: Import = field(repr=False)


def build(zolca: Path, *, version: str, out_dir: Path) -> Built:
    """Write a zolca as `<out_dir>/bafu-<version>.zip` and import it under `bafu-<version>`. The
    package is exported to a staging file beside the destination and moved into place only once the
    core reads it, so a bundle the core refuses leaves nothing under the final name; a destination
    that exists is `Conflict`."""
    destination = out_dir / f"{database_name(version)}.zip"
    staging = out_dir / f".bafu-{version}.staging.zip"
    if destination.exists():
        raise Conflict(f"{destination.name} exists; name another destination")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = export(zolca, staging)
    try:
        imported = read_background(written.bundle, database_name(version), foreground=frozenset())
        replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return Built(
        bundle=destination,
        records=written.records,
        not_carried=written.not_carried,
        imported=imported,
    )
