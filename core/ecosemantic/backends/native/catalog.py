"""The catalog of one installed database: its datasets, their exchanges, its elementary flows and
its methods, and the terms its search ranks, as tables of one DuckDB file."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import duckdb

from ecosemantic.backends.native.terms import tokens
from ecosemantic.errors import NotSupported
from ecosemantic.model.entities import ExchangeType, Method
from ecosemantic.package.background import Dataset, Import, Unlinked
from ecosemantic.ports.types import FLOW_TYPES, Side

Kind = Literal["process", "flow", "method"]
FIELDS: dict[Kind, tuple[str, ...]] = {
    "process": ("name", "reference_product"),
    "flow": ("name", "compartment", "sub_compartment", "cas"),
    "method": ("spec",),
}
_EXCHANGE_TYPE: dict[str, ExchangeType] = {
    "production": "product",
    "technosphere": "product",
    "biosphere": "elementary",
}

SCHEMA = """
CREATE TABLE processes(
    "row" INTEGER, native_id VARCHAR, name VARCHAR, reference_product VARCHAR,
    location VARCHAR, unit VARCHAR, classifications VARCHAR[], comment VARCHAR, url VARCHAR);
CREATE TABLE exchanges(
    process VARCHAR, position INTEGER, type VARCHAR, side VARCHAR, "reference" BOOLEAN,
    input VARCHAR, flow VARCHAR, supplier VARCHAR, amount DOUBLE, unit VARCHAR,
    cut_off VARCHAR);
CREATE TABLE flows(
    "row" INTEGER, code VARCHAR, name VARCHAR, compartment VARCHAR, sub_compartment VARCHAR,
    unit VARCHAR, flow_type VARCHAR, cas VARCHAR, synonyms VARCHAR[]);
CREATE TABLE methods("row" INTEGER, key VARCHAR[], unit VARCHAR);
CREATE TABLE terms(kind VARCHAR, "row" INTEGER, field INTEGER, position INTEGER, term VARCHAR);
CREATE TABLE lengths(kind VARCHAR, "row" INTEGER, tokens INTEGER);
"""
INDEXES = """
CREATE INDEX processes_native_id ON processes(native_id);
CREATE INDEX exchanges_process ON exchanges(process);
CREATE INDEX flows_code ON flows(code);
CREATE INDEX terms_term ON terms(term);
"""
TABLES = ("processes", "exchanges", "flows", "methods", "terms", "lengths")


def compartments(categories: Sequence[str]) -> tuple[str, str | None]:
    """The compartment and sub-compartment a flow's categories name: the first, and the rest
    joined by `/`."""
    compartment = str(categories[0]) if categories else ""
    rest = "/".join(str(c) for c in categories[1:]) if len(categories) > 1 else None
    return compartment, rest


def _classification(value: object) -> str:
    if isinstance(value, tuple | list):
        return f"{value[0]}: {value[1]}"
    return str(value)


@dataclass
class Table:
    """One table's columns, in its schema's order."""

    columns: tuple[str, ...]
    values: list[list[object]] = field(init=False)

    def __post_init__(self) -> None:
        self.values = [[] for _ in self.columns]

    def add(self, *row: object) -> None:
        """Append one row."""
        for column, value in zip(self.values, row, strict=True):
            column.append(value)


@dataclass
class Rows:
    """Every table of a catalog, filled from one import and checked before anything is
    written."""

    processes: Table
    exchanges: Table
    flows: Table
    methods: Table
    terms: Table
    lengths: Table


def _searched(rows: Rows, kind: Kind, row: int, texts: Sequence[str | None]) -> None:
    count = 0
    for at, text in enumerate(texts):
        for position, term in enumerate(tokens(text)):
            rows.terms.add(kind, row, at, position, term)
            count += 1
    rows.lengths.add(kind, row, count)


def _exchanges(
    rows: Rows,
    code: str,
    dataset: Dataset,
    names: Mapping[str, tuple[str, str]],
    dropped: Sequence[Unlinked],
) -> None:
    """One row per exchange of a dataset, its reference exchange among them with the amount the
    exchange holds, and one row per input the install cut off with its reason and no input."""
    for exchange in cast(list[Dataset], dataset["exchanges"]):
        kind = str(exchange["type"])
        if kind not in _EXCHANGE_TYPE:
            raise NotSupported(
                f"exchange type {kind!r} in {dataset['name']!r} is not one the port names"
            )
        reference = kind == "production"
        target = cast(tuple[str, str], exchange["input"])[1]
        amount = float(cast(float, exchange["amount"]))
        rows.exchanges.add(
            code,
            cast(int, exchange["position"]),
            _EXCHANGE_TYPE[kind],
            cast(Side, str(exchange["side"])),
            reference,
            target,
            str(exchange["name"]),
            names[target][0] if kind == "technosphere" else None,
            abs(amount) if reference else amount,
            str(exchange["unit"]),
            None,
        )
    for record in dropped:
        rows.exchanges.add(
            code,
            record.position,
            _EXCHANGE_TYPE["technosphere"],
            "input" if record.is_input else "output",
            False,
            None,
            record.flow,
            None,
            record.amount,
            record.unit,
            record.reason,
        )


def catalog_rows(imported: Import, dropped: Sequence[Unlinked] = ()) -> Rows:
    """The catalog of an import, with the records its caller dropped listed as cut-off exchanges;
    NotSupported for an exchange type or a flow type the ports do not name."""
    rows = Rows(
        processes=Table(
            (
                "row",
                "native_id",
                "name",
                "reference_product",
                "location",
                "unit",
                "classifications",
                "comment",
                "url",
            )
        ),
        exchanges=Table(
            (
                "process",
                "position",
                "type",
                "side",
                "reference",
                "input",
                "flow",
                "supplier",
                "amount",
                "unit",
                "cut_off",
            )
        ),
        flows=Table(
            (
                "row",
                "code",
                "name",
                "compartment",
                "sub_compartment",
                "unit",
                "flow_type",
                "cas",
                "synonyms",
            )
        ),
        methods=Table(("row", "key", "unit")),
        terms=Table(("kind", "row", "field", "position", "term")),
        lengths=Table(("kind", "row", "tokens")),
    )
    names: dict[str, tuple[str, str]] = {}
    dropped_by_dataset: dict[str, list[Unlinked]] = {}
    for record in dropped:
        dropped_by_dataset.setdefault(record.dataset, []).append(record)
    for (_, code), dataset in imported.datasets.items():
        names[code] = (str(dataset["name"]), str(dataset["unit"]))
    for (_, code), flow in imported.flows.items():
        if flow["type"] not in FLOW_TYPES:
            raise NotSupported(
                f"flow type {flow['type']!r} of {flow['name']!r} is not one the port names"
            )
        names[code] = (str(flow["name"]), str(flow["unit"]))
    for row, ((_, code), dataset) in enumerate(imported.datasets.items()):
        name, product = str(dataset["name"]), str(dataset["reference product"])
        rows.processes.add(
            row,
            code,
            name,
            product,
            dataset.get("location"),
            str(dataset["unit"]),
            [_classification(c) for c in cast(list, dataset.get("classifications") or [])],
            dataset.get("comment"),
            dataset.get("url"),
        )
        _exchanges(rows, code, dataset, names, dropped_by_dataset.get(code, []))
        _searched(rows, "process", row, (name, product))
    for row, ((_, code), flow) in enumerate(imported.flows.items()):
        compartment, sub_compartment = compartments(cast(Sequence[str], flow["categories"]))
        cas = cast("str | None", flow.get("CAS number"))
        rows.flows.add(
            row,
            code,
            flow["name"],
            compartment,
            sub_compartment,
            flow["unit"],
            flow["type"],
            cas,
            list(cast(list[str], flow.get("synonyms") or [])),
        )
        _searched(rows, "flow", row, (str(flow["name"]), compartment, sub_compartment, cas))
    for row, imported_method in enumerate(imported.methods):
        method = Method.of(imported_method.key, imported_method.unit)
        rows.methods.add(row, list(method.tuple), method.unit)
        _searched(rows, "method", row, (method.spec,))
    return rows


def _types(connection: duckdb.DuckDBPyConnection, name: str) -> dict[str, str]:
    """A table's columns and the DuckDB types its schema gives them, in the schema's order."""
    rows = connection.execute(
        "SELECT column_name, data_type FROM duckdb_columns()"
        " WHERE table_name = ? ORDER BY column_index",
        [name],
    ).fetchall()
    return dict(rows)


def _load(connection: duckdb.DuckDBPyConnection, directory: Path, name: str, table: Table) -> None:
    """Write a table's rows as newline-delimited JSON beside the catalog and insert them into it,
    every column typed as the table's schema types it."""
    file = directory / f"{name}.ndjson"
    with file.open("w", encoding="utf-8") as out:
        for row in zip(*table.values, strict=True):
            out.write(json.dumps(dict(zip(table.columns, row, strict=True))) + "\n")
    connection.read_json(
        str(file), format="newline_delimited", columns=_types(connection, name)
    ).insert_into(name)


def write_catalog(path: Path, rows: Rows) -> None:
    """Write the catalog into a new DuckDB file."""
    connection = duckdb.connect(path)
    connection.execute(SCHEMA)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        for name in TABLES:
            table: Table = getattr(rows, name)
            if not table.values[0]:
                continue
            _load(connection, Path(directory), name, table)
    connection.execute(INDEXES)
    connection.close()
