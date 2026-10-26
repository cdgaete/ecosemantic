"""What a BAFU zolca holds and what of it the core's reader takes: its schema version, its tables,
the counts its export becomes, the inputs that stay unlinked, the exchanges the core refuses and
the rows its package does not carry."""

from __future__ import annotations

import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipReader

from ecosemantic.databases.lists import distinct_unlinked
from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.databases.zolca.export.write import NotCarried, export
from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model import units
from ecosemantic.package.background import Import, exchange_refusal, read_background
from ecosemantic.package.olca import uncertainty_refusal

BUNDLE = "probe.zip"
DATABASE = "bafu-probe"
VERSION_TABLE = "OPENLCA_VERSION"
VERSION_COLUMN = "VERSION"
PREFIX = "ecosemantic-bafu-probe-"


@dataclass(frozen=True)
class TableProbe:
    """One table of the database: its rows, and the SQL type each column is stored as."""

    name: str
    rows: int
    columns: dict[str, str]


@dataclass(frozen=True)
class Probe:
    """What a zolca holds and what the core would take of it: its schema version, every table with
    its rows and column types, what its export becomes in the core, the unlinked inputs by their
    flow's top category, the exchanges the core refuses by its own reason, the rows the package
    does not carry, and the factors method categories set apart."""

    schema_version: str
    tables: tuple[TableProbe, ...]
    processes: int
    flows: int
    methods: int
    categories: int
    unlinked: dict[str, int]
    refused: dict[str, int]
    not_carried: tuple[NotCarried, ...]
    set_apart: int


def _schema_version(database: Database) -> str:
    """The openLCA schema version the database stores."""
    stored = list(database.rows(VERSION_TABLE))
    if len(stored) != 1:
        raise Invalid(f"{database.path} stores {len(stored)} {VERSION_TABLE} rows, not one")
    return str(stored[0][VERSION_COLUMN])


def _tables(database: Database) -> tuple[TableProbe, ...]:
    """Every table of schema `APP`, its rows counted and each column's SQL type named."""
    return tuple(
        TableProbe(
            name=name,
            rows=sum(1 for _ in database.rows(table)),
            columns={column.name: column.type.name for column in table.columns},
        )
        for name, table in sorted(database.tables().items())
    )


def _read(bundle: Path) -> tuple[tuple[o.Process, ...], dict[str, o.Flow]]:
    """A package's processes, and its flows by id."""
    with ZipReader(str(bundle)) as reader:
        processes = tuple(reader.read_each(o.Process))
        flows = {flow.id: flow for flow in reader.read_each(o.Flow)}
    return processes, flows


def _factors(bundle: Path) -> list[o.ImpactFactor]:
    """Every impact factor the package's categories carry."""
    with ZipReader(str(bundle)) as reader:
        return [
            factor
            for category in reader.read_each(o.ImpactCategory)
            for factor in category.impact_factors or []
        ]


def _symbols(records: Iterable[o.Exchange | o.ImpactFactor]) -> set[str]:
    """The unit symbols a run of exchanges or impact factors names."""
    return {
        record.unit.name
        for record in records
        if record.unit is not None and record.unit.name is not None
    }


def _known(symbol: str) -> bool:
    """Whether the core's unit table holds a symbol."""
    try:
        units.by_symbol(symbol)
    except NotSupported:
        return False
    return True


def _lacking(bundle: Path, processes: Sequence[o.Process]) -> tuple[str, ...]:
    """Every unit symbol the package's exchanges and impact factors name that the core's table
    lacks, in one sorted tuple."""
    named = _symbols(
        exchange for process in processes for exchange in process.exchanges or []
    ) | _symbols(_factors(bundle))
    return tuple(sorted(symbol for symbol in named if not _known(symbol)))


def _unlinked(imported: Import, flows: dict[str, o.Flow]) -> dict[str, int]:
    """The import's distinct unlinked inputs, counted by the top category of their flow."""
    tops = {flow_id: (flow.category or "").split("/")[0] for flow_id, flow in flows.items()}
    return dict(Counter(row.flow_category for row in distinct_unlinked(imported, tops)))


def _refused(processes: Sequence[o.Process], flows: dict[str, o.Flow]) -> Counter[str]:
    """What the core's two refusals answer over the package's exchanges, counted by reason."""
    return Counter(
        reason
        for process in processes
        for exchange in process.exchanges or []
        if exchange.flow is not None
        and exchange.flow.id in flows
        and (
            reason := uncertainty_refusal(exchange.uncertainty, exchange.amount or 0.0)
            or exchange_refusal(exchange, flows[exchange.flow.id])
        )
    )


def probe(zolca: Path) -> Probe:
    """Read a zolca through the export and the core's importer in a temporary directory, and answer
    what it holds, what the core refuses of it and what its package does not carry; a unit symbol
    the core's table lacks is `NotSupported`, every lacking symbol named at once."""
    database = Database(zolca)
    with tempfile.TemporaryDirectory(prefix=PREFIX) as directory:
        written = export(zolca, Path(directory) / BUNDLE)
        processes, flows = _read(written.bundle)
        lacking = _lacking(written.bundle, processes)
        if lacking:
            raise NotSupported(f"{zolca}: the core's unit table lacks {', '.join(lacking)}")
        imported = read_background(written.bundle, DATABASE, foreground=frozenset())
        return Probe(
            schema_version=_schema_version(database),
            tables=_tables(database),
            processes=imported.processes,
            flows=len(imported.flows),
            methods=len({method.key[1] for method in imported.methods}),
            categories=len(imported.methods),
            unlinked=_unlinked(imported, flows),
            refused=dict(_refused(processes, flows)),
            not_carried=written.not_carried,
            set_apart=sum(method.set_apart for method in imported.methods),
        )
