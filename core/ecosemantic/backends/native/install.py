"""Install a bundle's import under a data directory: the bundle kept, the background compiled
and saved, the catalog written, and the registry entry last."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.backends.native.catalog import catalog_rows, write_catalog
from ecosemantic.backends.native.store import (
    BACKGROUND_DIR,
    BUNDLES_DIR,
    CATALOG_FILE,
    DATABASES_DIR,
    ENTRY_FILE,
    FORMAT,
    Entry,
    slug,
)
from ecosemantic.errors import Conflict
from ecosemantic.model.refs import Database
from ecosemantic.package.background import Import, Unlinked, require_linked
from ecosemantic.package.compile import compile_background


@dataclass(frozen=True)
class Installed:
    """What one install wrote, and where."""

    database: Database
    directory: Path
    datasets: int
    flows: int
    methods: int


def _keep(directory: Path, bundle: Path) -> str:
    """Copy the bundle under its SHA-256 unless that file exists; its digest."""
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    folder = directory / BUNDLES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    kept = folder / f"{digest}.zip"
    if not kept.is_file():
        shutil.copyfile(bundle, kept)
    return digest


def _refuse_taken(target: Path, name: str, replace: bool) -> None:
    """Conflict for a directory another database holds, and for this one's without replace."""
    entry_path = target / ENTRY_FILE
    if not entry_path.is_file():
        return
    held = json.loads(entry_path.read_text())["database"]["name"]
    if held != name:
        raise Conflict(f"{target} holds {held!r}; {name!r} cannot be installed there")
    if not replace:
        raise Conflict(f"database {name!r} is installed in {target}")


def install(
    directory: Path,
    imported: Import,
    bundle: Path,
    *,
    version: str,
    system_model: str,
    replace: bool = False,
    dropped: Sequence[Unlinked] = (),
) -> Installed:
    """Install the import under the data directory, its entry naming the fingerprint of the
    background compiled from it; the records in `dropped` are listed in the catalog as exchanges
    the install cut off and reach no background. Invalid while an input is unlinked, NotSupported
    for an exchange or flow type the ports do not name, Conflict for a name that is installed
    without replace."""
    require_linked(imported)
    database = Database(
        name=imported.database,
        elementary_flows=imported.biosphere,
        scheme="olca",
        version=version,
        system_model=system_model,
    )
    rows = catalog_rows(imported, dropped)
    target = directory / DATABASES_DIR / slug(database.name)
    _refuse_taken(target, database.name, replace)
    digest = _keep(directory, bundle)
    partial = target.parent / f".{target.name}.partial-{uuid.uuid4().hex}"
    partial.mkdir(parents=True)
    try:
        background = compile_background(imported, database)
        database = database.model_copy(update={"fingerprint": background.fingerprint()})
        background.save(partial / BACKGROUND_DIR)
        write_catalog(partial / CATALOG_FILE, rows)
        entry = Entry(format=FORMAT, database=database, bundle=digest)
        (partial / ENTRY_FILE).write_text(entry.model_dump_json(indent=1) + "\n")
        if target.exists():
            old = target.parent / f".{target.name}.old-{uuid.uuid4().hex}"
            target.rename(old)
            partial.rename(target)
            shutil.rmtree(old)
        else:
            partial.rename(target)
    finally:
        if partial.exists():
            shutil.rmtree(partial)
    return Installed(
        database=database,
        directory=target,
        datasets=len(imported.datasets),
        flows=len(imported.flows),
        methods=len(imported.methods),
    )
