"""A built BAFU bundle validated against its results workbook: each cell in the workbook's terms,
its total column, and the differences a release knows of, held as a list."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.bafu import cli as bafu_cli
from ecosemantic.databases.bafu import validate as validate_module
from ecosemantic.databases.bafu.differences import (
    Difference,
    read_differences,
    write_differences,
)
from ecosemantic.databases.bafu.validate import Validation, record, validate
from ecosemantic.errors import Invalid
from tests.databases.bafu_fixture import (
    CLIMATE,
    ELEC_CLIMATE,
    ELEC_LABEL,
    FUEL_OIL_CLIMATE,
    STEEL_LABEL,
    TOTAL,
    TREATMENT_CLIMATE,
    TREATMENT_LABEL,
    WATER,
    WIDGET_CLIMATE,
    WIDGET_LABEL,
    fixture_profile,
    workbook_rows,
    write_workbook,
)
from tests.openlca_fixture import PROCESSES, build_package

Row = tuple[str, str, Mapping[str, float]]


def _bundle(tmp_path: Path, name: str = "fixture.zip") -> Path:
    """A bundle of the test package, with the electricity process declared in kilowatt hours."""
    return build_package(tmp_path / name, elec_in_kwh=True)


def _workbook(tmp_path: Path, rows: Sequence[Row] | None = None) -> Path:
    """A results workbook as Nexus serves it, of the hand-computed rows unless others are given."""
    return write_workbook(tmp_path / "results.zip", workbook_rows() if rows is None else rows)


def _with(rows: Sequence[Row], label: str, header: str, value: float) -> list[Row]:
    """The rows with one process's cell set to another value."""
    return [
        (each, unit, {**scores, header: value} if each == label else dict(scores))
        for each, unit, scores in rows
    ]


def _checked(bundle: Path, results: Path, *, differences: Path | None = None) -> Validation:
    """The validation of a bundle against a workbook, under the test release's profile."""
    return validate(
        bundle,
        results=results,
        profile=fixture_profile(),
        unlinked=None,
        differences=differences,
    )


def test_a_matching_workbook_passes(tmp_path: Path) -> None:
    validation = _checked(_bundle(tmp_path), _workbook(tmp_path))

    assert validation.mismatches == ()
    assert validation.differences == ()
    assert validation.processes == 4
    assert validation.columns == 2
    assert validation.by_column == {}
    assert validation.largest_rel_diff_within_tolerance <= 1e-6


def test_a_score_beyond_the_tolerance_is_a_difference(tmp_path: Path) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    validation = _checked(_bundle(tmp_path), _workbook(tmp_path, rows))

    assert validation.differences == (Difference(process_id=PROCESSES["elec"], column=CLIMATE),)
    assert validation.mismatches == ()
    assert validation.by_column[CLIMATE].count == 1
    assert validation.largest_rel_diff_within_tolerance <= 1e-6


def test_a_listed_difference_passes(tmp_path: Path) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    listed = tmp_path / "differences.csv"
    write_differences(listed, [Difference(process_id=PROCESSES["elec"], column=CLIMATE)])

    validation = _checked(_bundle(tmp_path), _workbook(tmp_path, rows), differences=listed)

    assert validation.differences == (Difference(process_id=PROCESSES["elec"], column=CLIMATE),)
    assert validation.mismatches == ()


def test_a_difference_not_listed_is_a_mismatch(tmp_path: Path) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    listed = tmp_path / "differences.csv"
    write_differences(listed, [])

    validation = _checked(_bundle(tmp_path), _workbook(tmp_path, rows), differences=listed)

    assert len(validation.mismatches) == 1
    message = validation.mismatches[0]
    assert PROCESSES["elec"] in message
    assert CLIMATE in message
    assert "the differences list lacks it" in message
    assert repr(4.0) in message


def test_a_listed_pair_within_the_tolerance_is_a_mismatch(tmp_path: Path) -> None:
    listed = tmp_path / "differences.csv"
    write_differences(listed, [Difference(process_id=PROCESSES["elec"], column=WATER)])

    validation = _checked(_bundle(tmp_path), _workbook(tmp_path), differences=listed)

    assert len(validation.mismatches) == 1
    message = validation.mismatches[0]
    assert PROCESSES["elec"] in message
    assert WATER in message
    assert "within the tolerance, and the differences list holds it" in message


def test_a_row_whose_process_has_several_datasets_is_invalid(tmp_path: Path) -> None:
    refined = (
        "refinery production - GLO",
        "kg",
        {CLIMATE: FUEL_OIL_CLIMATE, TOTAL: FUEL_OIL_CLIMATE},
    )
    rows = [*workbook_rows(), refined]

    with pytest.raises(Invalid) as refused:
        _checked(_bundle(tmp_path), _workbook(tmp_path, rows))

    assert PROCESSES["refinery"] in str(refused.value)
    assert "has 2 datasets, not one" in str(refused.value)


def test_a_row_whose_process_has_no_dataset_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absent = "5f2e9a41-0000-4000-8000-000000000000"
    labels = {
        ELEC_LABEL: absent,
        STEEL_LABEL: PROCESSES["steel"],
        WIDGET_LABEL: PROCESSES["widget"],
        TREATMENT_LABEL: PROCESSES["treatment"],
    }
    monkeypatch.setattr(validate_module, "_labels", lambda imported: labels)

    with pytest.raises(Invalid) as refused:
        _checked(_bundle(tmp_path), _workbook(tmp_path))

    assert absent in str(refused.value)
    assert "has 0 datasets, not one: none" in str(refused.value)


def test_a_waste_treatment_is_compared_with_its_sign_reversed(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    raw = _with(workbook_rows(), TREATMENT_LABEL, CLIMATE, -TREATMENT_CLIMATE)

    assert _checked(bundle, _workbook(tmp_path / "raw", raw)).differences == (
        Difference(process_id=PROCESSES["treatment"], column=CLIMATE),
    )
    assert _checked(bundle, _workbook(tmp_path / "reversed")).differences == ()


def test_a_kwh_process_is_compared_per_mj(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    raw = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 1.0)

    assert _checked(bundle, _workbook(tmp_path / "raw", raw)).differences == (
        Difference(process_id=PROCESSES["elec"], column=CLIMATE),
    )
    assert ELEC_CLIMATE == pytest.approx(1 / 3.6)
    assert _checked(bundle, _workbook(tmp_path / "converted")).differences == ()


def test_the_total_is_the_sum_of_its_method(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    climate_only = _with(workbook_rows(), WIDGET_LABEL, TOTAL, WIDGET_CLIMATE)

    assert _checked(bundle, _workbook(tmp_path / "summed")).differences == ()
    assert _checked(bundle, _workbook(tmp_path / "climate", climate_only)).differences == (
        Difference(process_id=PROCESSES["widget"], column=TOTAL),
    )


def test_the_total_sums_only_the_columns_the_profile_maps(tmp_path: Path) -> None:
    bundle = build_package(tmp_path / "unmapped.zip", elec_in_kwh=True, unmapped_category=True)
    workbook = _workbook(tmp_path)

    assert _checked(bundle, workbook).differences == ()


def test_record_writes_the_list_and_the_block(tmp_path: Path) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    profile = fixture_profile()
    validation = _checked(_bundle(tmp_path), _workbook(tmp_path, rows))
    directory = tmp_path / "releases"
    directory.mkdir()

    path = record(profile, validation, directory=directory)

    assert path == directory / "fixture-v1.yaml"
    assert read_differences(directory / profile.differences) == (
        Difference(process_id=PROCESSES["elec"], column=CLIMATE),
    )
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert written["validated"] == {
        "processes": 4,
        "columns": 2,
        "differences": 1,
        "largest_rel_diff_within_tolerance": validation.largest_rel_diff_within_tolerance,
    }
    assert written["tolerance"] == profile.tolerance
    assert isinstance(written["tolerance"], float)
    assert written["inventory"]["sha256"] == profile.inventory.sha256
    assert written["total"] == {"header": TOTAL, "method": "fixture method"}


def test_record_is_refused_with_a_mismatch(tmp_path: Path) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    listed = tmp_path / "differences.csv"
    write_differences(listed, [])
    validation = _checked(_bundle(tmp_path), _workbook(tmp_path, rows), differences=listed)
    directory = tmp_path / "releases"
    directory.mkdir()

    with pytest.raises(Invalid) as refused:
        record(fixture_profile(), validation, directory=directory)

    assert "the differences list lacks it" in str(refused.value)
    assert list(directory.iterdir()) == []


def test_the_command_answers_the_differences_by_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _with(workbook_rows(), ELEC_LABEL, CLIMATE, 4.0)
    profile = fixture_profile()
    listed = tmp_path / "differences.csv"
    write_differences(listed, [])
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: profile)
    monkeypatch.setattr(
        bafu_cli, "recorded", lambda name: listed if name == profile.differences else None
    )

    assert (
        databases_cli.main(
            [
                "bafu",
                "validate",
                "fixture-v1",
                "--bundle",
                str(_bundle(tmp_path)),
                "--results",
                str(_workbook(tmp_path, rows)),
                "--compiled",
                str(tmp_path / "compiled"),
            ]
        )
        == 1
    )
    answer = json.loads(capsys.readouterr().out)

    assert "differences" not in answer
    assert answer["processes"] == 4
    assert answer["columns"] == 2
    assert answer["differences_by_column"][CLIMATE]["count"] == 1
    assert answer["differences_by_column"][CLIMATE]["largest_rel_diff"] == pytest.approx(
        (4.0 - ELEC_CLIMATE) / 4.0
    )
    assert PROCESSES["elec"] in answer["mismatches"][0]


def test_the_command_records_the_run_it_was_asked_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = fixture_profile()
    releases = tmp_path / "releases"
    releases.mkdir()
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: profile)
    monkeypatch.setattr(bafu_cli, "recorded", lambda name: None)
    monkeypatch.setattr(bafu_cli, "RELEASES", releases)

    assert (
        databases_cli.main(
            [
                "bafu",
                "validate",
                "fixture-v1",
                "--bundle",
                str(_bundle(tmp_path)),
                "--results",
                str(_workbook(tmp_path)),
                "--compiled",
                str(tmp_path / "compiled"),
                "--record",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["mismatches"] == []
    assert (releases / "fixture-v1.yaml").is_file()
    assert read_differences(releases / profile.differences) == ()
