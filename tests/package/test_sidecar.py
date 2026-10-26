from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.errors import NotFound
from ecosemantic.model.entities import ProductSystem
from ecosemantic.package.sidecar import (
    SIDECAR_DIR,
    ActivityRecord,
    ExchangeIdentity,
    Identities,
    ProcessIdentity,
    ProjectRecord,
    Sidecar,
    read_lines,
    read_sidecar,
    write_lines,
    write_sidecar,
)
from tests.conftest import CO2, COTTON


def test_sidecar_round_trips_through_files(product_system: ProductSystem, tmp_path: Path) -> None:
    first = product_system.processes[0]
    sidecar = Sidecar(
        product_system=ProjectRecord(
            id=product_system.id,
            name=product_system.name,
            description=product_system.description,
            notes=product_system.notes,
            database=product_system.database,
            hash="0" * 64,
            processes=[ActivityRecord(id=a.id, code=a.code) for a in product_system.processes],
        ),
        identities=Identities(
            processes={str(first.id): ProcessIdentity(id=first.id, code="tshirt")},
            exchanges={
                f"{first.id}:1": ExchangeIdentity(id=first.exchanges[0].id, label="cotton t-shirt")
            },
            elementary_flows={"f2": CO2},
            suppliers={"p1:f1": COTTON},
            product_flows={"pf": product_system.processes[1].id},
            locations={"loc": "CH"},
            parameter_prefix="cotton_tshirt__",
        ),
        scenarios=product_system.scenarios,
        metadata={a.id: a.metadata for a in product_system.processes},
    )
    write_sidecar(tmp_path, sidecar)
    assert sorted(p.name for p in (tmp_path / SIDECAR_DIR).iterdir()) == [
        "identities.json",
        "metadata.json",
        "product_system.json",
        "scenarios.json",
    ]
    assert read_sidecar(tmp_path) == sidecar


def test_read_sidecar_requires_the_folder(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        read_sidecar(tmp_path)


def test_identities_default_empty() -> None:
    assert Identities(parameter_prefix="x__").processes == {}


def test_lines_round_trip_under_the_sidecar_folder_and_a_missing_file_reads_as_none(
    tmp_path: Path,
) -> None:
    assert read_lines(tmp_path, "queue.jsonl") == []
    write_lines(tmp_path, "queue.jsonl", ['{"a": 1}', '{"a": 2}'])
    written = tmp_path / SIDECAR_DIR / "queue.jsonl"
    assert written.read_text(encoding="utf-8") == '{"a": 1}\n{"a": 2}\n'
    written.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    assert read_lines(tmp_path, "queue.jsonl") == ['{"a": 1}', '{"a": 2}']
