from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ecosemantic.engine.background import Background, Factors, Rows
from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import Method, Uncertainty
from tests.engine.conftest import SMALL, SMALL_GWP, small
from tests.fixture_data import FIXTURE_DATABASE


def test_a_dataset_using_its_own_product_sums_onto_the_diagonal() -> None:
    background = small(
        ["mill", "mill", "energy"],
        ["mill", "mill", "energy"],
        [1.0, 0.2, 1.0],
        [False, True, False],
    )
    assert background.technosphere.nnz == 2
    mill = background.position("activity", "mill")
    assert mill is not None
    assert background.technosphere.to_dense()[mill, mill] == pytest.approx(0.8)
    assert background.exchanges["technosphere"].amount.size == 3


def test_a_dataset_whose_production_enters_the_matrix_negative_is_a_treatment(
    tmp_path: Path,
) -> None:
    background = Background.compile(
        SMALL,
        activities=["mill", "energy", "incineration", "landfill"],
        flows=["co2", "noise"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=["mill", "mill", "energy", "incineration", "landfill"],
            columns=["mill", "mill", "energy", "incineration", "landfill"],
            amounts=[1.0, 0.2, 1.0, -1.0, 1.0],
            flipped=[False, True, False, False, True],
            uncertainties=[None] * 5,
        ),
        biosphere=Rows(
            rows=["co2"], columns=["mill"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )
    # incineration states its waste as a negative output, as ecoinvent does; landfill takes
    # its waste in, as an openLCA treatment does; the mill uses a fifth of its own product
    assert background.treating() == frozenset({"incineration", "landfill"})
    background.save(tmp_path / "background")
    assert Background.load(tmp_path / "background").treating() == background.treating()


def test_the_coordinates_are_sorted_and_hold_every_flow() -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    assert background.coords["activity"].labels.tolist() == ["energy", "mill"]
    assert background.coords["product"] is background.coords["activity"]
    assert background.coords["flow"].labels.tolist() == ["co2", "noise"]
    assert background.position("flow", "noise") == 1
    assert background.position("flow", "absent") is None


def test_a_row_naming_a_label_outside_its_coordinate_is_invalid() -> None:
    with pytest.raises(
        Invalid,
        match="technosphere rows name a label the background does not hold, the first 'kiln'",
    ):
        small(["kiln"], ["mill"], [1.0], [False])


def test_every_exchange_keeps_its_distribution() -> None:
    background = Background.compile(
        SMALL,
        activities=["mill"],
        flows=["co2"],
        methods=[SMALL_GWP],
        technosphere=Rows(
            rows=["mill"], columns=["mill"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        biosphere=Rows(
            rows=["co2", "co2"],
            columns=["mill", "mill"],
            amounts=[1.0, 0.5],
            flipped=[False, False],
            uncertainties=[
                Uncertainty(type="lognormal", params={"loc": 0.0, "scale": 0.1, "negative": True}),
                Uncertainty(type="triangular", params={"minimum": 0.4, "loc": 0.5, "maximum": 0.7}),
            ],
        ),
        factors=Factors(categories=[SMALL_GWP.id], flows=["co2"], values=[1.0]),
    )
    rows = background.exchanges["biosphere"]
    assert rows.uncertainty_type.tolist() == [2, 5]
    assert rows.loc.tolist() == [0.0, 0.5]
    assert rows.scale[0] == 0.1 and np.isnan(rows.scale[1])
    assert np.isnan(rows.minimum[0]) and rows.minimum[1] == 0.4
    assert rows.negative.tolist() == [True, False]
    assert background.biosphere.to_dense().tolist() == [[1.5]]


def test_a_method_the_background_lacks_is_not_found() -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    other = Method.of(("small", "water", "water use > m3"), "m3")
    with pytest.raises(NotFound, match="water use > m3"):
        background.positions([SMALL_GWP, other])


def test_a_saved_background_loads_memory_mapped_and_equal(
    background: Background, tmp_path: Path
) -> None:
    background.save(tmp_path / "saved")
    loaded = Background.load(tmp_path / "saved")
    assert loaded.database == FIXTURE_DATABASE
    assert loaded.methods == background.methods
    for name in ("technosphere", "biosphere", "characterization"):
        before, after = getattr(background, name), getattr(loaded, name)
        assert np.array_equal(before.index, after.index)
        assert np.array_equal(before.data, after.data)
        assert isinstance(after.data, np.memmap)
    assert (
        loaded.coords["activity"].labels.tolist() == background.coords["activity"].labels.tolist()
    )
    for field in ("row", "column", "amount", "uncertainty_type", "negative"):
        assert np.array_equal(
            getattr(background.exchanges["technosphere"], field),
            getattr(loaded.exchanges["technosphere"], field),
        )


def test_saving_over_an_existing_directory_is_a_conflict(
    background: Background, tmp_path: Path
) -> None:
    (tmp_path / "taken").mkdir()
    with pytest.raises(Conflict, match="exists"):
        background.save(tmp_path / "taken")


def test_a_directory_without_a_background_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFound, match="holds no saved background"):
        Background.load(tmp_path)


def test_a_format_the_engine_does_not_read_is_invalid(
    background: Background, tmp_path: Path
) -> None:
    background.save(tmp_path / "saved")
    manifest = tmp_path / "saved" / "background.json"
    written = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps(written | {"format": 99}), encoding="utf-8")
    with pytest.raises(Invalid, match="format 99"):
        Background.load(tmp_path / "saved")


def test_a_background_s_fingerprint_is_the_same_saved_and_loaded(tmp_path: Path) -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    fingerprint = background.fingerprint()
    background.save(tmp_path / "saved")
    assert Background.load(tmp_path / "saved").fingerprint() == fingerprint
    assert len(fingerprint) == 64 and int(fingerprint, 16) >= 0


def test_a_background_s_fingerprint_leaves_out_the_name_it_is_installed_under() -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    renamed = SMALL.model_copy(update={"name": "other", "elementary_flows": "other-biosphere"})
    method = Method.of(("other", *SMALL_GWP.tuple[1:]), "kg CO2-Eq")
    other = Background.compile(
        renamed,
        activities=["mill", "energy"],
        flows=["co2", "noise"],
        methods=[method],
        technosphere=Rows(
            rows=["mill", "energy"],
            columns=["mill", "energy"],
            amounts=[1.0, 1.0],
            flipped=[False, False],
            uncertainties=[None, None],
        ),
        biosphere=Rows(
            rows=["co2"], columns=["mill"], amounts=[1.0], flipped=[False], uncertainties=[None]
        ),
        factors=Factors(categories=[method.id], flows=["co2"], values=[1.0]),
    )
    # the category labels are method ids, which carry the database's name
    assert other.coords["category"].labels.tolist() != background.coords["category"].labels.tolist()
    assert other.fingerprint() == background.fingerprint()


def test_a_background_s_fingerprint_reads_its_arrays_and_its_category_keys(
    tmp_path: Path,
) -> None:
    background = small(["mill", "energy"], ["mill", "energy"], [1.0, 1.0], [False, False])
    background.save(tmp_path / "saved")
    manifest_path = tmp_path / "saved" / "background.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["version"] = "2"
    manifest["methods"] = [{**method, "indicator": "other"} for method in manifest["methods"]]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert Background.load(tmp_path / "saved").fingerprint() == background.fingerprint()
    # one amount changed is another build
    other = small(["mill", "energy"], ["mill", "energy"], [1.0, 0.9], [False, False])
    assert other.fingerprint() != background.fingerprint()
