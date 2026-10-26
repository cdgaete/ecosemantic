"""The databases installed under one data directory: their registry entries, their catalogs and
their compiled backgrounds, served from one worker thread."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypeVar

import duckdb
from pydantic import BaseModel, ConfigDict, model_validator

from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.solver import SolverName, require_solver
from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.model.refs import Database

T = TypeVar("T")
FORMAT = 4
BUNDLES_DIR = "bundles"
DATABASES_DIR = "databases"
ENTRY_FILE = "entry.json"
CATALOG_FILE = "catalog.duckdb"
BACKGROUND_DIR = "background"


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


class NativeStore:
    """Every database installed under one data directory, its registry read when the store is
    built and again when the store lists the databases or is asked for a name it does not hold;
    every port call, catalog query and solve runs on the store's one worker thread."""

    def __init__(self, directory: Path, solver: str = "superlu") -> None:
        self.directory = directory
        self.solver: SolverName = require_solver(solver)
        self._entries: dict[str, Entry] = {}
        self._catalogs: dict[str, duckdb.DuckDBPyConnection] = {}
        self._backgrounds: dict[str, Background] = {}
        self._calculations: dict[str, Calculation] = {}
        self._worker: int | None = None
        self._read()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="native")

    def _read(self) -> None:
        """Read every registry entry under the data directory and close what a database whose
        entry is gone or names another bundle leaves loaded."""
        entries: dict[str, Entry] = {}
        for path in sorted((self.directory / DATABASES_DIR).glob(f"*/{ENTRY_FILE}")):
            if path.parent.name.startswith("."):
                continue
            held = json.loads(path.read_text())
            if held.get("format") != FORMAT:
                raise Unavailable(
                    f"{path.parent.name!r} is installed in entry format {held.get('format')}; "
                    f"this store reads format {FORMAT}",
                    hint="install it again from its bundle with "
                    "`ecosemantic setup openlca --replace`",
                )
            entry = Entry.model_validate(held)
            entries[entry.database.name] = entry
        for name, held in self._entries.items():
            current = entries.get(name)
            if current is None or current.bundle != held.bundle:
                self._drop(name)
        self._entries = entries

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
        """The directory a database is installed in."""
        return self.directory / DATABASES_DIR / slug(self.registered(name).database.name)

    def catalog(self, name: str) -> duckdb.DuckDBPyConnection:
        """The database's catalog, opened read-only on first use; call on the worker thread."""
        if name not in self._catalogs:
            path = self.path_of(name) / CATALOG_FILE
            self._catalogs[name] = duckdb.connect(path, read_only=True)
        return self._catalogs[name]

    def background(self, name: str) -> Background:
        """The database's compiled background, its arrays memory-mapped on first use; call on the
        worker thread."""
        if name not in self._backgrounds:
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
