"""The databases installed under one data directory: their registry entries, their catalogs and
their compiled backgrounds, served from one worker thread."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

import duckdb
from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, model_validator

from ecosemantic.backends.retry import read_bytes, replace
from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.solver import SolverName, require_solver
from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.model.refs import Database

T = TypeVar("T")
FORMAT = 5
BUNDLES_DIR = "bundles"
DATABASES_DIR = "databases"
BUILDS_DIR = "builds"
POINTER_FILE = "current"
ENTRY_FILE = "entry.json"
CATALOG_FILE = "catalog.duckdb"
BACKGROUND_DIR = "background"
MIGRATION_LOCK = ".migration.lock"
INSTALL_LOCK = "install.lock"
MIGRATED_PREFIX = "migrated-"


class Entry(BaseModel):
    """The registry entry of one installed database: the entry's format, the database with the
    fingerprint of its compiled background, and the SHA-256 of the bundle it was installed
    from."""

    model_config = ConfigDict(frozen=True)

    format: int
    database: Database
    bundle: str

    @model_validator(mode="after")
    def _fingerprinted(self) -> Entry:
        if self.database.fingerprint is None:
            raise ValueError("an entry names the fingerprint of its compiled background")
        return self


def slug(name: str) -> str:
    """The directory name of a database: lowercased, each run of characters other than a-z and
    0-9 one hyphen, no hyphen at either end."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def served_build(database_dir: Path) -> str | None:
    """The build id a database directory's pointer names, or None when it holds no pointer."""
    pointer = database_dir / POINTER_FILE
    if not pointer.is_file():
        return None
    return read_bytes(pointer).decode("utf-8").strip()


def build_dir(directory: Path, name: str, build_id: str) -> Path:
    """The directory of one build of a database under the data directory."""
    return directory / DATABASES_DIR / slug(name) / BUILDS_DIR / build_id


def point(database_dir: Path, build_id: str) -> None:
    """Point a database directory at a build, the pointer replaced whole within the bounded
    retry, so a store reading it sees one build or the other."""
    pointer = database_dir / POINTER_FILE
    staged = database_dir / f".{POINTER_FILE}.tmp"
    staged.write_text(build_id, encoding="utf-8")
    replace(staged, pointer)


def install_lock(database_dir: Path) -> FileLock:
    """The per-database lock an install holds while it writes its build, so a store reading the
    directory does not remove the build before the pointer names it."""
    return FileLock(database_dir / INSTALL_LOCK)


def remove_unnamed_builds(database_dir: Path, keep: str | None) -> None:
    """Remove every build directory a database's pointer does not name, or every build when no
    pointer names one; a directory Windows refuses to remove because a store still maps it stays
    for the next install or open."""
    builds = database_dir / BUILDS_DIR
    if not builds.is_dir():
        return
    for build in builds.iterdir():
        if (keep is not None and build.name == keep) or not build.is_dir():
            continue
        try:
            shutil.rmtree(build)
        except PermissionError as error:
            if os.name != "nt" or getattr(error, "winerror", None) not in (5, 32):
                raise


def remove_unnamed_builds_if_idle(database_dir: Path) -> None:
    """Remove every build the pointer does not name, the pointer read only after the install lock
    is held, and nothing when an install holds the lock."""
    lock = install_lock(database_dir)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return
    try:
        remove_unnamed_builds(database_dir, served_build(database_dir))
    finally:
        lock.release()


def _servable(path: Path) -> bool:
    """Whether a directory under databases/ names a database: a directory, not a dot-name."""
    return path.is_dir() and not path.name.startswith(".")


def _migrated_build(path: Path) -> Path | None:
    """The half-moved build of a database directory: its `builds/migrated-*` directory, or None."""
    builds = path / BUILDS_DIR
    if not builds.is_dir():
        return None
    for build in builds.iterdir():
        if build.is_dir() and build.name.startswith(MIGRATED_PREFIX):
            return build
    return None


def _needs_migration(path: Path) -> bool:
    """Whether a database directory might need migration: no pointer and a root entry or a
    `migrated-` build; a hint only, the entry is read under the migration lock."""
    if (path / POINTER_FILE).is_file():
        return False
    if (path / ENTRY_FILE).is_file():
        return True
    return _migrated_build(path) is not None


def _wrong_format(name: str, format_: object) -> Unavailable:
    """Unavailable naming a database installed in an entry format this store does not read."""
    return Unavailable(
        f"{name!r} is installed in entry format {format_}; this store reads format {FORMAT}",
        hint="install it again from its bundle with `ecosemantic setup openlca --replace`",
    )


def migrate(directory: Path) -> None:
    """Move every format-4 database under the data directory into its own `migrated-` build
    directory and point at it, resuming a half-finished move, under one data-directory-wide lock
    so two stores do not both move; a server that writes entry format 4 at the same time is the
    one state it cannot repair."""
    databases = directory / DATABASES_DIR
    if not databases.is_dir():
        return
    if not any(_needs_migration(path) for path in databases.iterdir() if _servable(path)):
        return
    with FileLock(directory / MIGRATION_LOCK):
        for path in sorted(databases.iterdir()):
            if _servable(path) and _needs_migration(path):
                _migrate_build(path)


def _migrate_build(path: Path) -> None:
    """Move a format-4 database's files into its `migrated-` build directory, idempotently, and
    point at it; each move happens only while the file is still at the root, the entry moves last
    and is rewritten staged, and the pointer write is the commit."""
    root_entry = path / ENTRY_FILE
    build = _migrated_build(path)
    held: dict
    if build is None:
        if not root_entry.is_file():
            return
        held = json.loads(root_entry.read_text(encoding="utf-8"))
        if held.get("format") != 4:
            return
        build = path / BUILDS_DIR / (MIGRATED_PREFIX + held["bundle"][:32])
        build.mkdir(parents=True, exist_ok=True)
        _move_files(path, build)
        shutil.move(str(root_entry), str(build / ENTRY_FILE))
    else:
        _move_files(path, build)
        if root_entry.is_file():
            held = json.loads(root_entry.read_text(encoding="utf-8"))
            shutil.move(str(root_entry), str(build / ENTRY_FILE))
        else:
            held = json.loads((build / ENTRY_FILE).read_text(encoding="utf-8"))
    held["format"] = FORMAT
    _write_entry(build / ENTRY_FILE, held)
    point(path, build.name)


def _move_files(path: Path, build: Path) -> None:
    """Move a format-4 database's background and catalog into its build, each only while still at
    the root, so a resumed move finds nothing already gone."""
    if (path / BACKGROUND_DIR).is_dir():
        shutil.move(str(path / BACKGROUND_DIR), str(build / BACKGROUND_DIR))
    if (path / CATALOG_FILE).is_file():
        shutil.move(str(path / CATALOG_FILE), str(build / CATALOG_FILE))


def _write_entry(entry_path: Path, held: dict) -> None:
    """Write an entry staged and replaced within the retry, so a crash cannot leave a truncated
    entry beside a build the pointer may already name."""
    staged = entry_path.with_name(f".{entry_path.name}.tmp")
    staged.write_text(json.dumps(held, indent=1) + "\n", encoding="utf-8")
    replace(staged, entry_path)


class NativeStore:
    """Every database installed under one data directory, its registry read when the store is
    built and again when the store lists the databases or is asked for a name it does not hold;
    every port call, catalog query and solve runs on the store's one worker thread."""

    def __init__(self, directory: Path, solver: str = "superlu") -> None:
        self.directory = directory
        self.solver: SolverName = require_solver(solver)
        self._entries: dict[str, Entry] = {}
        self._builds: dict[str, str] = {}
        self._catalogs: dict[str, duckdb.DuckDBPyConnection] = {}
        self._backgrounds: dict[str, Background] = {}
        self._calculations: dict[str, Calculation] = {}
        self._worker: int | None = None
        self._read()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="native")

    def _read(self) -> None:
        """Read the build every database's pointer names, close what a database whose build is
        gone or changed leaves loaded, and remove the builds nothing points at while no install
        writes them."""
        migrate(self.directory)
        entries: dict[str, Entry] = {}
        builds: dict[str, str] = {}
        databases = self.directory / DATABASES_DIR
        if not databases.is_dir():
            for name in self._entries:
                self._drop(name)
            self._entries = entries
            self._builds = builds
            return
        pending: list[Path] = []
        for path in sorted(databases.iterdir()):
            if not _servable(path):
                continue
            build_id = served_build(path)
            if build_id is None:
                self._refuse_unserved(path)
                pending.append(path)
                continue
            entry_path = path / BUILDS_DIR / build_id / ENTRY_FILE
            if not entry_path.is_file():
                continue
            held = json.loads(entry_path.read_text(encoding="utf-8"))
            if held.get("format") != FORMAT:
                raise _wrong_format(path.name, held.get("format"))
            entry = Entry.model_validate(held)
            entries[entry.database.name] = entry
            builds[entry.database.name] = build_id
            pending.append(path)
        for name in self._entries:
            current = entries.get(name)
            if current is None or builds.get(name) != self._builds.get(name):
                self._drop(name)
        self._entries = entries
        self._builds = builds
        for path in pending:
            remove_unnamed_builds_if_idle(path)

    def _refuse_unserved(self, path: Path) -> None:
        """Unavailable for a database directory that holds an entry this store cannot migrate:
        an entry beside its files in a format other than 4, with no pointer."""
        entry_path = path / ENTRY_FILE
        if not entry_path.is_file():
            return
        held = json.loads(entry_path.read_text(encoding="utf-8"))
        raise _wrong_format(path.name, held.get("format"))

    def _drop(self, name: str) -> None:
        """Close the catalog, background and calculation the store loaded for a database."""
        catalog = self._catalogs.pop(name, None)
        if catalog is not None:
            catalog.close()
        self._backgrounds.pop(name, None)
        self._calculations.pop(name, None)

    def _on_worker(self, fn: Callable[[], T]) -> T:
        """Run fn on the worker thread, or in the job already running there, and wait for it."""
        if self._worker == threading.get_ident():
            return fn()
        return self._executor.submit(lambda: self._entered(fn)).result()

    def _entered(self, fn: Callable[[], T]) -> T:
        self._worker = threading.get_ident()
        return fn()

    def databases(self) -> list[Database]:
        """Every database the store serves, in name order, the registry read again."""
        return self._on_worker(self._listed)

    def _listed(self) -> list[Database]:
        self._read()
        return [self._entries[name].database for name in sorted(self._entries)]

    def registered(self, name: str) -> Entry:
        """The registry entry of a database name, the registry read again when the store does not
        hold the name."""
        held = self._entries.get(name)
        if held is None:
            return self._on_worker(lambda: self._entry(name))
        return held

    def _entry(self, name: str) -> Entry:
        self._read()
        held = self._entries.get(name)
        if held is None:
            owner = self._owner(name)
            if owner is not None:
                raise NotFound(f"{name!r} holds the elementary flows of {owner!r}; name {owner!r}")
            raise NotFound(f"no database {name!r} under {self.directory}")
        return held

    def technosphere_of(self, name: str) -> str:
        """The served database a name addresses: itself, or the owner of the flows it names."""
        if name not in self._entries:
            return self._on_worker(lambda: self._technosphere(name))
        return name

    def _technosphere(self, name: str) -> str:
        self._read()
        if name in self._entries:
            return name
        owner = self._owner(name)
        if owner is None:
            raise NotFound(f"no database {name!r}; this store serves {sorted(self._entries)}")
        return owner

    def owner_of_elementary_flows(self, name: str) -> str:
        """The served database whose elementary flows the name holds."""
        owner = self._owner(name)
        if owner is None:
            return self._on_worker(lambda: self._flows_owner(name))
        return owner

    def _flows_owner(self, name: str) -> str:
        self._read()
        owner = self._owner(name)
        if owner is None:
            raise NotFound(f"no database under {self.directory} uses the elementary flows {name!r}")
        return owner

    def _owner(self, name: str) -> str | None:
        for entry in self._entries.values():
            if entry.database.elementary_flows == name:
                return entry.database.name
        return None

    def bundle_at(self, digest: str) -> Path:
        """Where the bundle of a digest is kept."""
        return self.directory / BUNDLES_DIR / f"{digest}.zip"

    def bundle_of(self, name: str) -> Path:
        """The bundle a database was installed from, as this directory keeps it."""
        return self.bundle_at(self.registered(name).bundle)

    def path_of(self, name: str) -> Path:
        """The directory of the build this database's pointer names."""
        self.registered(name)
        return build_dir(self.directory, name, self._builds[name])

    def _reload_if_pointer_moved(self, name: str) -> None:
        """Re-read the registry when the build the pointer names is not the one this store
        loaded, so a catalog or background opens the build the pointer names; NotFound when the
        database is gone."""
        if served_build(self.directory / DATABASES_DIR / slug(name)) == self._builds[name]:
            return
        self._read()
        if name not in self._entries:
            raise NotFound(f"no database {name!r} under {self.directory}")

    def catalog(self, name: str) -> duckdb.DuckDBPyConnection:
        """The database's catalog, opened read-only on first use; call on the worker thread."""
        if name not in self._catalogs:
            self._reload_if_pointer_moved(name)
            path = self.path_of(name) / CATALOG_FILE
            self._catalogs[name] = duckdb.connect(path, read_only=True)
        return self._catalogs[name]

    def background(self, name: str) -> Background:
        """The database's compiled background, its arrays memory-mapped on first use; call on the
        worker thread."""
        if name not in self._backgrounds:
            self._reload_if_pointer_moved(name)
            self._backgrounds[name] = Background.load(self.path_of(name) / BACKGROUND_DIR)
        return self._backgrounds[name]

    def calculation(self, name: str) -> Calculation:
        """The database's calculation under the store's solver, over its background, built on
        first use; call on the worker thread."""
        if name not in self._calculations:
            self._calculations[name] = Calculation(self.background(name), self.solver)
        return self._calculations[name]

    def native_ids(self, name: str) -> set[str]:
        """The native id of every dataset the database holds."""
        rows = self.call(
            name, lambda: self.catalog(name).execute("SELECT native_id FROM processes").fetchall()
        )
        return {row[0] for row in rows}

    def call(self, name: str, fn: Callable[[], T]) -> T:
        """Run fn on the worker thread for a served database, and wait for it."""
        self.registered(name)
        return self._on_worker(fn)

    async def run(self, name: str, fn: Callable[[], T]) -> T:
        """Run fn on the worker thread for a served database."""
        self.registered(name)
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._entered, fn)

    def close(self) -> None:
        """Close every catalog, background and calculation and stop the worker thread."""

        def shut() -> None:
            for name in list(self._entries):
                self._drop(name)

        self._on_worker(shut)
        self._executor.shutdown(wait=True)
