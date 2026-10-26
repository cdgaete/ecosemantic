"""The independent scores of USLCI: the source zips read by a computation that shares no code with
the core's import, its build or its engine."""

from __future__ import annotations

import ast
import csv
from pathlib import Path

import independent_scores
import pytest

from ecosemantic.databases.uslci.build import build
from ecosemantic.package.background import read_background
from tests.databases.uslci_fixture import (
    BRIDGED_CODES,
    BRIDGED_NAME,
    CODES,
    EXPECTED,
    INVENTORY_NAME,
    METHOD_NAME,
    write_bridged,
    write_inventory,
    write_method,
)

VERSION = "1.2026-09.0"
SCRIPT = Path(independent_scores.__file__)


@pytest.fixture
def sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    """The fixture's two zips, and the bundle the build writes beside their left-out list."""
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    built = build(inventory, (method,), version=VERSION, out_dir=tmp_path / "out")
    return inventory, method, built.bundle


def _left_out(bundle: Path) -> Path:
    """The left-out list the build writes beside its bundle."""
    return bundle.with_name(f"left-out-{VERSION}.csv")


def _scored(
    sources: tuple[Path, Path, Path], tmp_path: Path, bridged: Path | None = None
) -> tuple[independent_scores.Scored, Path]:
    """The script's scores, and the CSV it writes its unlinked inputs to, over the sources and the
    bridged repository `bridged` names."""
    inventory, method, bundle = sources
    out = tmp_path / "independent.csv"
    unlinked = tmp_path / "independent-unlinked.csv"
    given = [
        "--inventory",
        str(inventory),
        "--method",
        str(method),
        "--left-out",
        str(_left_out(bundle)),
        "--out",
        str(out),
        "--unlinked-out",
        str(unlinked),
    ]
    if bridged is not None:
        given += ["--bridged", str(bridged)]
    assert independent_scores.main(given) == 0
    with out.open(newline="") as read:
        written = list(csv.DictReader(read))
    return [
        (row["code"], row["method"], row["category"], float(row["score"]), row["unit"])
        for row in written
    ], unlinked


def test_the_script_imports_nothing_of_ecosemantic() -> None:
    tree = ast.parse(SCRIPT.read_text())
    named = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    named += [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None
    ]
    assert [module for module in named if module.startswith("ecosemantic")] == []


def test_scores_on_the_fixture_are_the_hand_computed_ones(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    scored, _ = _scored(sources, tmp_path)
    found = {(code, category): score for code, _method, category, score, _unit in scored}
    for role, expected in EXPECTED["scores"].items():
        for category, score in expected.items():
            assert found[(CODES[role], category)] == pytest.approx(score, rel=1e-12)


def test_the_out_file_has_one_row_per_dataset_and_category(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    scored, _ = _scored(sources, tmp_path)
    categories = EXPECTED["scores"]["widget"]
    assert len(scored) == len(CODES) * len(categories)
    assert {(code, category) for code, _method, category, _score, _unit in scored} == {
        (CODES[role], category)
        for role, expected in EXPECTED["scores"].items()
        for category in expected
    }


def test_each_score_names_the_unit_it_is_per(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    scored, _ = _scored(sources, tmp_path)
    units = {code: unit for code, _method, _category, _score, unit in scored}
    assert units[CODES["widget"]] == "kg"
    assert units[CODES["distillery"]] == "m3"


def test_an_unlinked_input_of_a_process_with_two_products_is_written_once(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, unlinked = _scored(sources, tmp_path)
    with unlinked.open(newline="") as read:
        rows = list(csv.DictReader(read))
    keys = [(row["process_id"], row["flow_id"], row["provider_id"] or None) for row in rows]
    assert len(keys) == len(set(keys)) == len(EXPECTED["unlinked"])


def test_its_unlinked_inputs_are_the_core_s(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    inventory, method, bundle = sources
    _, unlinked = _scored(sources, tmp_path)
    with unlinked.open(newline="") as read:
        rows = list(csv.DictReader(read))
    assert tuple(rows[0]) == independent_scores.UNLINKED_COLUMNS
    imported = read_background(
        build(inventory, (method,), version="again", out_dir=tmp_path / "again").bundle,
        "uslci",
        foreground=frozenset(),
    )
    theirs = {(miss.process_id, miss.flow_id, miss.provider_id) for miss in imported.unlinked}
    assert {
        (row["process_id"], row["flow_id"], row["provider_id"] or None) for row in rows
    } == theirs
    assert bundle.is_file()


def test_the_bridged_scores_are_the_hand_computed_ones(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    inventory, method, _bundle = sources
    bridged = write_bridged(tmp_path / BRIDGED_NAME)
    built = build(
        inventory, (method,), version=VERSION, out_dir=tmp_path / "bridged", bridged=(bridged,)
    )
    scored, _ = _scored((inventory, method, built.bundle), tmp_path, bridged)
    found = {(code, category): score for code, _method, category, score, _unit in scored}
    expected = {**EXPECTED["scores"], **EXPECTED["bridged"]["scores"]}
    codes = {**CODES, **BRIDGED_CODES}
    for role, by_category in expected.items():
        for category, score in by_category.items():
            assert found[(codes[role], category)] == pytest.approx(score, rel=1e-12)
    assert len(found) == len(codes) * len(expected["widget"])


def test_its_unlinked_inputs_are_the_core_s_on_the_merged_bundle(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    inventory, method, _bundle = sources
    bridged = write_bridged(tmp_path / BRIDGED_NAME)
    built = build(
        inventory, (method,), version=VERSION, out_dir=tmp_path / "merged", bridged=(bridged,)
    )
    _, unlinked = _scored((inventory, method, built.bundle), tmp_path, bridged)
    with unlinked.open(newline="") as read:
        rows = list(csv.DictReader(read))
    imported = read_background(built.bundle, "uslci", foreground=frozenset())
    theirs = {(miss.process_id, miss.flow_id, miss.provider_id) for miss in imported.unlinked}
    assert {
        (row["process_id"], row["flow_id"], row["provider_id"] or None) for row in rows
    } == theirs


def test_an_exchange_naming_a_flow_no_zip_holds_is_refused(
    sources: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, method, bundle = sources
    inventory = write_inventory(tmp_path / "dangling.zip", dangling_flow=True)
    with pytest.raises(ValueError, match="names a flow no zip holds"):
        independent_scores.scores(inventory, (method,), _left_out(bundle))
