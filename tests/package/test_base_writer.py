from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, NotSupported
from ecosemantic.model.entities import Uncertainty
from ecosemantic.package.background import read_background
from ecosemantic.package.base_writer import (
    BaseDataset,
    BaseExchange,
    BaseFlow,
    BaseMethod,
    BaseRows,
    write_base_bundle,
)

STEEL = "aaaaaaaa-0000-4000-8000-000000000001_bbbbbbbb-0000-4000-8000-000000000001"
ELEC = "aaaaaaaa-0000-4000-8000-000000000002_bbbbbbbb-0000-4000-8000-000000000002"
CO2 = "cccccccc-0000-4000-8000-000000000001"
ORE = "cccccccc-0000-4000-8000-000000000002"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _rows(unit: str = "kilogram") -> BaseRows:
    steel = BaseDataset(
        code=STEEL,
        native=STEEL,
        name="steel production",
        reference_product="steel",
        unit=unit,
        location="NA",
        comment=None,
        url="https://example.org/dataset/1",
        exchanges=(
            BaseExchange(kind="production", input=STEEL, amount=1.0, uncertainty=None),
            BaseExchange(
                kind="technosphere",
                input=ELEC,
                amount=2.0,
                uncertainty=Uncertainty(type="lognormal", params={"loc": 0.693, "scale": 0.1}),
            ),
            BaseExchange(kind="biosphere", input=CO2, amount=3.0, uncertainty=None),
            BaseExchange(kind="biosphere", input=ORE, amount=1.5, uncertainty=None),
        ),
    )
    elec = BaseDataset(
        code=ELEC,
        native=ELEC,
        name="electricity production",
        reference_product="electricity",
        unit="kilowatt hour",
        location="GLO",
        comment="a comment",
        url=None,
        exchanges=(
            BaseExchange(kind="production", input=ELEC, amount=1.0, uncertainty=None),
            BaseExchange(kind="biosphere", input=CO2, amount=0.5, uncertainty=None),
        ),
    )
    flows = (
        BaseFlow(
            code=CO2,
            name="Carbon dioxide",
            unit="kilogram",
            categories=("air", "unspecified"),
            type="emission",
            cas="124-38-9",
        ),
        BaseFlow(
            code=ORE,
            name="Iron",
            unit="kilogram",
            categories=("natural resource", "in ground"),
            type="natural resource",
            cas=None,
        ),
    )
    methods = (
        BaseMethod(
            key=("db", "IPCC", "climate change", "GWP100"),
            unit="kg CO2-Eq",
            factors=((CO2, 1.0),),
        ),
    )
    return BaseRows(datasets=(steel, elec), flows=flows, methods=methods)


def test_rows_write_an_bundle_the_core_installs_whole(tmp_path: Path) -> None:
    written = write_base_bundle(
        _rows(),
        scheme="ecoinvent",
        name="db",
        version="1",
        destination=tmp_path / "db.zip",
        now=NOW,
    )
    assert (written.processes, written.flows, written.methods) == (2, 4, 1)
    imported = read_background(written.bundle, "db", foreground=frozenset())
    assert imported.unlinked == []
    ore = next(f for f in imported.flows.values() if f["name"] == "Iron")
    # ecoinvent's "natural resource" files under openLCA's "Resource"
    assert ore["categories"] == ("Resource", "in ground") and ore["type"] == "natural resource"
    steel = next(d for d in imported.datasets.values() if d["name"] == "steel production")
    assert steel["location"] == "NA"


def test_an_unknown_unit_names_every_one(tmp_path: Path) -> None:
    with pytest.raises(NotSupported, match="furlong"):
        write_base_bundle(
            _rows(unit="furlong"),
            scheme="ecoinvent",
            name="db",
            version="1",
            destination=tmp_path / "db.zip",
            now=NOW,
        )


def test_a_dataset_url_reaches_the_installed_dataset(tmp_path: Path) -> None:
    written = write_base_bundle(
        _rows(),
        scheme="ecoinvent",
        name="db",
        version="1",
        destination=tmp_path / "db.zip",
        now=NOW,
    )
    imported = read_background(written.bundle, "db", foreground=frozenset())
    by_name = {d["name"]: d for d in imported.datasets.values()}
    assert by_name["steel production"]["url"] == "https://example.org/dataset/1"
    assert "url" not in by_name["electricity production"]


def test_an_existing_bundle_is_not_overwritten(tmp_path: Path) -> None:
    (tmp_path / "db.zip").write_bytes(b"")
    with pytest.raises(Conflict, match="db.zip"):
        write_base_bundle(
            _rows(),
            scheme="ecoinvent",
            name="db",
            version="1",
            destination=tmp_path / "db.zip",
            now=NOW,
        )
