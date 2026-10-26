"""The catalog of one installed database, written table by table."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from ecosemantic.backends.native.catalog import TABLES, Rows, Table, catalog_rows, write_catalog
from ecosemantic.package.background import read_background
from tests.engine_fixture import fixture_bundle
from tests.fixture_data import FIXTURE_DB

ROUNDED = 0.037399999999999996


def _set(table: Table, row: int, **values: object) -> None:
    """Set named cells of one row of a table."""
    for column, value in values.items():
        table.values[table.columns.index(column)][row] = value


def _in_order(rows: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    """The rows in an order both readers of the same multiset agree on."""
    return sorted(rows, key=lambda row: tuple((v is not None, str(v)) for v in row))


@pytest.fixture(scope="module")
def rows(tmp_path_factory: pytest.TempPathFactory) -> Rows:
    """The fixture's catalog, its cells holding a NULL, an empty and a filled VARCHAR[], and a
    double that the decimal literal 0.0374 would round."""
    bundle = fixture_bundle(tmp_path_factory.mktemp("sources"))
    given = catalog_rows(read_background(bundle, FIXTURE_DB, foreground=frozenset()))
    _set(given.processes, 0, comment=None, url=None, classifications=[])
    _set(given.processes, 1, classifications=["Category: steel", "steel"])
    _set(given.exchanges, 0, amount=ROUNDED)
    _set(given.flows, 0, cas=None, synonyms=[])
    _set(given.flows, 1, synonyms=["CO2", "carbon dioxide"])
    return given


def test_the_catalog_reads_back_every_row(rows: Rows, tmp_path: Path) -> None:
    path = tmp_path / "catalog.duckdb"
    write_catalog(path, rows)
    connection = duckdb.connect(path, read_only=True)
    for name in TABLES:
        table: Table = getattr(rows, name)
        read = connection.table(name).order("ALL").fetchall()
        assert _in_order(list(read)) == _in_order(list(zip(*table.values, strict=True))), name
    amounts = connection.execute("SELECT amount FROM exchanges").fetchall()
    assert [amount for (amount,) in amounts].count(ROUNDED) == 1
    connection.close()
