"""The probe of a zolca: its tables, its counts, and what the core would not take of it."""

from __future__ import annotations

import json

import pytest

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.bafu.probe import probe
from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.errors import NotSupported
from ecosemantic.model import units
from tests.databases.zolca.fixture import FIXTURES, recorded

ZOLCA = FIXTURES / "openlca.zip"


def test_the_probe_answers_the_schema_version_and_every_table_with_its_types() -> None:
    found = probe(ZOLCA)
    described = Database(ZOLCA).tables()
    located = {table.name: table for table in found.tables}

    assert found.schema_version == "15"
    assert set(located) == set(described)
    assert {name: table.columns for name, table in located.items()} == {
        name: {column.name: column.type.name for column in table.columns}
        for name, table in described.items()
    }
    assert located["TBL_LOCATIONS"].columns["GEODATA"] == "BLOB"
    assert located["TBL_EXCHANGES"].columns["IS_INPUT"] == "SMALLINT"


def test_the_probe_counts_the_rows_of_every_table_that_holds_any() -> None:
    found = probe(ZOLCA)
    counted = {table.name: table.rows for table in found.tables}

    assert {name: counted[name] for name in recorded()} == {
        name: len(rows) for name, rows in recorded().items()
    }
    assert counted["TBL_EXCHANGES"] == 4


def test_the_probe_counts_what_the_export_becomes_in_the_core() -> None:
    found = probe(ZOLCA)

    assert (found.processes, found.flows, found.methods, found.categories) == (2, 1, 1, 2)
    assert found.set_apart == 1
    assert found.unlinked == {}
    assert found.refused == {}


def test_the_probe_names_the_rows_the_package_does_not_carry() -> None:
    found = probe(ZOLCA)

    assert {(entry.table, entry.rows) for entry in found.not_carried} == {
        ("OPENLCA_VERSION", 1),
        ("SEQUENCE", 1),
        ("TBL_CATEGORIES", 12),
        ("TBL_FLOW_PROPERTIES", 1),
        ("TBL_LOCATIONS.OTHER_PROPERTIES", 1),
        ("TBL_MAPPING_FILES", 1),
        ("TBL_PROCESS_DOCS.PRECEDING_DATASET", 1),
    }


def test_the_probe_writes_nothing_beside_the_zolca() -> None:
    before = set(FIXTURES.iterdir())

    probe(ZOLCA)

    assert set(FIXTURES.iterdir()) == before


def test_a_unit_the_core_lacks_stops_the_probe_naming_every_lacking_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known = units.by_symbol

    def without_kilogram_and_kilowatt_hour(symbol: str) -> units.Unit:
        if symbol in {"kg", "kWh"}:
            raise NotSupported(f"unit symbol {symbol!r} is not one the core knows")
        return known(symbol)

    monkeypatch.setattr(units, "by_symbol", without_kilogram_and_kilowatt_hour)
    with pytest.raises(NotSupported) as raised:
        probe(ZOLCA)

    assert "kg" in str(raised.value)
    assert "kWh" in str(raised.value)


def test_the_command_answers_a_probe_as_one_json_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert databases_cli.main(["bafu", "probe", str(ZOLCA)]) == 0
    answer = json.loads(capsys.readouterr().out)

    assert answer["schema_version"] == "15"
    assert answer["processes"] == 2
    assert answer["tables"][0]["name"] == "OPENLCA_VERSION"
    assert answer["not_carried"][0] == {
        "table": "OPENLCA_VERSION",
        "rows": 1,
        "reason": "no openLCA JSON-LD record holds this table's rows",
    }
