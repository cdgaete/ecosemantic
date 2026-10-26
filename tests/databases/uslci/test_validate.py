"""Validate a built USLCI bundle against the independent computation's scores and its two lists."""

from __future__ import annotations

import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import independent_scores
import pytest
import yaml

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.lists import (
    LeftOutRow,
    UnlinkedRow,
    read_left_out,
    read_unlinked,
    write_left_out,
    write_unlinked,
)
from ecosemantic.databases.uslci import profile as releases
from ecosemantic.databases.uslci.build import build
from ecosemantic.databases.uslci.profile import read_profile
from ecosemantic.databases.uslci.validate import (
    Validation,
    _converted,
    _tolerance,
    record,
    validate,
)
from tests.databases.uslci_fixture import (
    CODES,
    EXPECTED,
    FLOW_NAMES,
    INVENTORY_NAME,
    METHOD_NAME,
    PROCESSES,
    _flow_id,
    write_inventory,
    write_method,
)

VERSION = "1.2026-09.0"
WIDGET = CODES["widget"]
CLIMATE = "climate change"


@dataclass(frozen=True)
class Prepared:
    """A built bundle, the left-out list beside it, and the independent scores of its sources."""

    inventory: Path
    method: Path
    bundle: Path
    left_out: Path
    independent: Path


@pytest.fixture
def prepared(tmp_path: Path) -> Prepared:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    built = build(inventory, (method,), version=VERSION, out_dir=tmp_path / "out")
    left_out = built.bundle.with_name(f"left-out-{VERSION}.csv")
    independent = tmp_path / "independent.csv"
    assert (
        independent_scores.main(
            [
                "--inventory",
                str(inventory),
                "--method",
                str(method),
                "--left-out",
                str(left_out),
                "--out",
                str(independent),
                "--unlinked-out",
                str(tmp_path / "independent-unlinked.csv"),
            ]
        )
        == 0
    )
    return Prepared(inventory, method, built.bundle, left_out, independent)


def _shipped(tmp_path: Path) -> Path:
    """A copy of the shipped profiles without the recorded lists, so a fixture bundle is compared
    with no list at all."""
    shipped = tmp_path / "releases"
    shutil.copytree(releases.RELEASES, shipped)
    for path in shipped.glob("*.csv"):
        path.unlink()
    return shipped


def _first(prepared: Prepared) -> Validation:
    """The run a release makes before either list or a tolerance is recorded."""
    return validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=None,
        tolerance=None,
    )


def _changed(prepared: Prepared, tmp_path: Path, factor: float) -> tuple[Path, float]:
    """The independent scores with the widget's climate score multiplied by a factor."""
    with prepared.independent.open(newline="", encoding="utf-8") as read:
        rows = list(csv.DictReader(read))
    changed = 0.0
    for row in rows:
        if (row["code"], row["category"]) == (WIDGET, CLIMATE):
            changed = float(row["score"]) * factor
            row["score"] = repr(changed)
    with (tmp_path / "changed.csv").open("w", newline="", encoding="utf-8") as written:
        writer = csv.DictWriter(written, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return tmp_path / "changed.csv", changed


def test_the_fixture_s_bundle_validates_against_its_independent_scores(
    prepared: Prepared,
) -> None:
    validation = _first(prepared)
    assert validation.mismatches == ()
    assert validation.largest_rel_diff == 0.0
    assert (validation.datasets, validation.categories) == (
        EXPECTED["bundle"]["datasets"],
        EXPECTED["categories"],
    )
    assert sorted((row.process_name, row.flow_name) for row in validation.unlinked) == sorted(
        (row["process"], FLOW_NAMES[row["flow"]]) for row in EXPECTED["unlinked"]
    )
    assert {(row.process_name, row.what) for row in validation.left_out} == {
        (row["process"], row["what"]) for row in EXPECTED["left_out"]
    }


def test_one_more_unlinked_input_than_the_list_is_named(prepared: Prepared, tmp_path: Path) -> None:
    rows = _first(prepared).unlinked
    assert len(rows) == len(EXPECTED["unlinked"])
    listed = tmp_path / "unlinked.csv"
    write_unlinked(listed, rows[1:])
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=listed,
        left_out=None,
        tolerance=None,
    )
    row = rows[0]
    assert validation.mismatches == (
        f"{row.process_name} takes {row.flow_name} and the unlinked list lacks it",
    )


def test_a_product_declared_in_litres_is_converted_to_its_reference_unit() -> None:
    key = (CODES["distillery"], "IPCC GWP", CLIMATE)
    converted, mismatches = _converted({key: 1.0}, {key: (1000.0, "m3")}, {key[0]: "litre"})
    assert converted == {key: 1000.0}
    assert mismatches == []


def test_a_declared_unit_of_another_quantity_is_named() -> None:
    key = (CODES["distillery"], "IPCC GWP", CLIMATE)
    converted, mismatches = _converted({key: 1.0}, {key: (1.0, "kg")}, {key[0]: "litre"})
    assert converted == {}
    assert mismatches == [
        f"{key[0]} under {CLIMATE}: the core scores it per litre, the independent computation per "
        "kilogram, units of different quantities"
    ]


def test_a_list_row_the_release_lacks_is_named(prepared: Prepared, tmp_path: Path) -> None:
    listed = tmp_path / "unlinked.csv"
    write_unlinked(
        listed,
        (
            *_first(prepared).unlinked,
            UnlinkedRow(
                process_id="a-process-the-release-lacks",
                process_name="a process the release lacks",
                flow_id="a-flow",
                flow_name="a flow",
                flow_category="Technosphere Flows",
                provider_id=None,
            ),
        ),
    )
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=listed,
        left_out=None,
        tolerance=None,
    )
    assert validation.mismatches == (
        "the unlinked list holds a row of a process the release lacks, which the import lacks",
    )


def test_a_left_out_exchange_not_in_the_list_is_named(prepared: Prepared, tmp_path: Path) -> None:
    built = read_left_out(prepared.left_out)
    listed = tmp_path / "left-out.csv"
    write_left_out(listed, built[1:])
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=listed,
        tolerance=None,
    )
    row = built[0]
    assert validation.mismatches == (
        f"{row.process_name} leaves out {row.flow_name} of exchange {row.exchange_id} and the "
        "left-out list lacks it",
    )


def _renamed(prepared: Prepared, tmp_path: Path, field: str, old: str, new: str) -> Path:
    """The independent scores with one column's value replaced, as a dataset or category a side
    does not hold."""
    with prepared.independent.open(newline="", encoding="utf-8") as read:
        rows = list(csv.DictReader(read))
    for row in rows:
        if row[field] == old:
            row[field] = new
    path = tmp_path / f"renamed-{field}.csv"
    with path.open("w", newline="", encoding="utf-8") as written:
        writer = csv.DictWriter(written, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_a_dataset_only_one_side_scores_is_named(prepared: Prepared, tmp_path: Path) -> None:
    renamed = _renamed(prepared, tmp_path, "code", WIDGET, "a-dataset-the-core-lacks")
    validation = validate(
        prepared.bundle,
        independent=renamed,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=None,
        tolerance=None,
    )
    assert validation.mismatches == (
        f"{WIDGET} under climate change: only the core scores it",
        "a-dataset-the-core-lacks under climate change: only the independent computation scores it",
        f"{WIDGET} under water use: only the core scores it",
        "a-dataset-the-core-lacks under water use: only the independent computation scores it",
    )


def test_a_category_only_one_side_scores_is_named(prepared: Prepared, tmp_path: Path) -> None:
    renamed = _renamed(prepared, tmp_path, "category", "water use", "water use, renamed")
    validation = validate(
        prepared.bundle,
        independent=renamed,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=None,
        tolerance=None,
    )
    assert validation.mismatches[0] == ("IPCC GWP, water use: only the core scores it")
    assert "IPCC GWP, water use, renamed: only the independent computation scores it" in (
        validation.mismatches
    )


def test_a_left_out_row_the_build_did_not_write_is_named(
    prepared: Prepared, tmp_path: Path
) -> None:
    listed = tmp_path / "left-out.csv"
    write_left_out(
        listed,
        (
            *read_left_out(prepared.left_out),
            LeftOutRow(
                process_id=PROCESSES["widget"],
                process_name="widget",
                exchange_id=99,
                flow_id=_flow_id("so2"),
                flow_name="Sulfur dioxide",
                what="exchange",
                reason="refused",
            ),
        ),
    )
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=listed,
        tolerance=None,
    )
    assert validation.mismatches == (
        "the left-out list holds widget leaving out Sulfur dioxide of exchange 99, which the "
        "build did not",
    )


def test_the_tolerance_is_ten_times_the_largest_difference_rounded_up() -> None:
    assert _tolerance(0.0) == 1e-9
    assert _tolerance(1e-12) == 1e-9
    assert _tolerance(3e-10) == 1e-8
    assert _tolerance(1e-7) == 1e-6
    assert _tolerance(1.5e-7) == 1e-5


def test_two_exchanges_of_one_flow_are_two_left_out_rows(
    prepared: Prepared, tmp_path: Path
) -> None:
    built = read_left_out(prepared.left_out)
    rows = [row for row in built if row.flow_name == "Particulate matter, < 10 µm"]
    assert len(rows) == 2
    assert len({row.key for row in rows}) == 2
    assert rows[0].flow_id == rows[1].flow_id
    listed = tmp_path / "left-out.csv"
    write_left_out(listed, tuple(row for row in built if row != rows[0]))
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=listed,
        tolerance=None,
    )
    assert validation.mismatches == (
        f"{rows[0].process_name} leaves out {rows[0].flow_name} of exchange "
        f"{rows[0].exchange_id} and the left-out list lacks it",
    )


def test_a_score_beyond_the_tolerance_is_named_with_both_values(
    prepared: Prepared, tmp_path: Path
) -> None:
    changed, score = _changed(prepared, tmp_path, 1.01)
    validation = validate(
        prepared.bundle,
        independent=changed,
        built_left_out=prepared.left_out,
        unlinked=None,
        left_out=None,
        tolerance=1e-9,
    )
    assert len(validation.mismatches) == 1
    [mismatch] = validation.mismatches
    assert WIDGET in mismatch
    assert CLIMATE in mismatch
    assert "11.0" in mismatch
    assert repr(score) in mismatch
    assert validation.largest_rel_diff == pytest.approx(abs(score - 11.0) / abs(score), rel=1e-12)


def test_record_writes_the_lists_the_tolerance_and_the_validated_block(
    prepared: Prepared, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = _shipped(tmp_path)
    monkeypatch.setattr(releases, "RELEASES", shipped)
    validation = _first(prepared)
    assert validation.mismatches == ()
    path = record(read_profile(VERSION), validation)
    assert path == shipped / f"{VERSION}.yaml"
    assert read_unlinked(shipped / f"unlinked-{VERSION}.csv") == validation.unlinked
    assert read_left_out(shipped / f"left-out-{VERSION}.csv") == validation.left_out
    profile = read_profile(VERSION)
    assert profile.validated is not None
    assert profile.validated.datasets == validation.datasets
    assert profile.validated.categories == validation.categories
    assert profile.validated.largest_rel_diff_to_independent == validation.largest_rel_diff
    assert profile.tolerance is not None
    assert profile.tolerance >= 1e-9
    assert math.log10(profile.tolerance).is_integer()
    written = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(written) == [
        "version",
        "server",
        "inventory",
        "methods",
        "bridged",
        "unlinked",
        "left_out",
        "tolerance",
        "validated",
    ]


def test_the_recorded_profile_validates_against_its_own_lists(
    prepared: Prepared, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = _shipped(tmp_path)
    monkeypatch.setattr(releases, "RELEASES", shipped)
    record(read_profile(VERSION), _first(prepared))
    profile = read_profile(VERSION)
    validation = validate(
        prepared.bundle,
        independent=prepared.independent,
        built_left_out=prepared.left_out,
        unlinked=shipped / profile.unlinked,
        left_out=shipped / profile.left_out,
        tolerance=profile.tolerance,
    )
    assert validation.mismatches == ()


def test_the_validate_command_prints_one_json_document(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shipped = _shipped(tmp_path)
    monkeypatch.setattr(releases, "RELEASES", shipped)
    assert (
        databases_cli.main(
            [
                "uslci",
                "validate",
                VERSION,
                "--bundle",
                str(prepared.bundle),
                "--independent",
                str(prepared.independent),
                "--record",
            ]
        )
        == 0
    )
    answer = json.loads(capsys.readouterr().out)
    assert answer["datasets"] == EXPECTED["bundle"]["datasets"]
    assert answer["categories"] == EXPECTED["categories"]
    assert answer["mismatches"] == []
    assert (shipped / f"unlinked-{VERSION}.csv").is_file()


def test_the_validate_command_exits_one_on_a_mismatch(
    prepared: Prepared,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shipped = _shipped(tmp_path)
    monkeypatch.setattr(releases, "RELEASES", shipped)
    recorded = read_profile(VERSION).model_copy(update={"tolerance": 1e-9})
    (shipped / f"{VERSION}.yaml").write_text(
        yaml.safe_dump(recorded.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    changed, _ = _changed(prepared, tmp_path, 1.01)
    assert (
        databases_cli.main(
            [
                "uslci",
                "validate",
                VERSION,
                "--bundle",
                str(prepared.bundle),
                "--independent",
                str(changed),
            ]
        )
        == 1
    )
    answer = json.loads(capsys.readouterr().out)
    assert len(answer["mismatches"]) == 1
    assert WIDGET in answer["mismatches"][0]
