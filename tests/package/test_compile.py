from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from ecosemantic.engine.background import Background
from ecosemantic.errors import Invalid
from ecosemantic.package.background import Import, Unlinked, read_background
from ecosemantic.package.base_writer import BaseExchange, BaseFlow, BaseRows, write_base_bundle
from ecosemantic.package.compile import compile_background
from tests.engine_fixture import NOW, fixture_background, fixture_rows
from tests.fixture_data import CODES, FIXTURE_DATABASE, FIXTURE_DB, FLOW_IDS


def compiled(rows: BaseRows, directory: Path) -> Background:
    bundle = write_base_bundle(
        rows,
        scheme="olca",
        name=FIXTURE_DB,
        version="1",
        destination=directory / "bundle.zip",
        now=NOW,
    ).bundle
    imported = read_background(bundle, FIXTURE_DB, foreground=frozenset())
    return compile_background(imported, FIXTURE_DATABASE)


def test_the_fixture_compiles_to_its_datasets_flows_and_methods(tmp_path: Path) -> None:
    background = fixture_background(tmp_path)
    assert background.database == FIXTURE_DATABASE
    assert background.technosphere.shape == (12, 12)
    assert background.biosphere.shape == (4, 12)
    assert [method.spec for method in background.methods] == [
        "fixture > gwp > climate change > GWP100",
        "fixture > water > water use > m3",
    ]
    assert sorted(background.coords["activity"].labels.tolist()) == sorted(CODES.values())


def test_a_dataset_using_its_own_product_sums_onto_the_diagonal(tmp_path: Path) -> None:
    rows = fixture_rows()
    steel = next(d for d in rows.datasets if d.code == CODES["steel"])
    own = BaseExchange(kind="technosphere", input=CODES["steel"], amount=0.2, uncertainty=None)
    used = dataclasses.replace(steel, exchanges=(*steel.exchanges, own))
    rows = dataclasses.replace(
        rows, datasets=tuple(used if d.code == CODES["steel"] else d for d in rows.datasets)
    )
    background = compiled(rows, tmp_path)
    at = background.position("activity", CODES["steel"])
    assert at is not None
    assert background.technosphere.to_dense()[at, at] == pytest.approx(0.8)
    flipped = background.exchanges["technosphere"].flip
    rows_at = background.exchanges["technosphere"].row == at
    columns_at = background.exchanges["technosphere"].column == at
    assert int((rows_at & columns_at).sum()) == 2
    assert int((rows_at & columns_at & flipped).sum()) == 1


def test_every_flow_of_the_bundle_is_in_the_coordinate(tmp_path: Path) -> None:
    rows = fixture_rows()
    quiet = BaseFlow(
        code="99999999-9999-4999-8999-999999999999",
        name="Krypton",
        unit="kilogram",
        categories=("air",),
        type="emission",
        cas=None,
    )
    background = compiled(dataclasses.replace(rows, flows=(*rows.flows, quiet)), tmp_path)
    assert background.position("flow", quiet.code) is not None
    assert len(background.coords["flow"]) == 5


def test_every_exchange_keeps_its_distribution(tmp_path: Path) -> None:
    background = fixture_background(tmp_path)
    rows = background.exchanges["technosphere"]
    steel = background.position("activity", CODES["steel"])
    elec = background.position("activity", CODES["elec"])
    [at] = np.flatnonzero((rows.row == elec) & (rows.column == steel))
    # the fixture's steel takes 2 kWh under a normal of scale 3
    assert rows.uncertainty_type[at] == 3
    assert rows.loc[at] == pytest.approx(2.0) and rows.scale[at] == pytest.approx(3.0)
    assert rows.amount[at] == pytest.approx(2.0) and bool(rows.flip[at])
    biosphere = background.exchanges["biosphere"]
    co2 = background.position("flow", FLOW_IDS["co2"])
    [emitted] = np.flatnonzero((biosphere.row == co2) & (biosphere.column == elec))
    assert biosphere.scale[emitted] == pytest.approx(5.0)


def test_an_import_with_an_unlinked_input_is_invalid() -> None:
    imported = Import(
        database=FIXTURE_DB,
        biosphere=f"{FIXTURE_DB}-biosphere",
        datasets={},
        flows={},
        methods=[],
        processes=0,
        unlinked=[
            Unlinked(
                process="kiln",
                process_id="p",
                flow="clinker",
                flow_id="f",
                provider_id=None,
                reason="no dataset produces it",
                dataset="p_f",
                position=1,
                is_input=True,
                amount=1.0,
                unit="kilogram",
            )
        ],
    )
    with pytest.raises(Invalid, match="1 inputs are unlinked: 'kiln' takes 'clinker'"):
        compile_background(imported, FIXTURE_DATABASE)
