from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ecosemantic.errors import Conflict, Invalid
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.tables.folder import write_folder
from ecosemantic.tables.reader import apply_inputs
from tests.tables.test_folder import spaced


def test_an_unedited_folder_leaves_the_space_where_it_was(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    changed = apply_inputs(system, folder)
    assert content_hash(changed) == content_hash(system)


def test_a_changed_value_is_applied(tmp_path: Path, product_system: ProductSystem) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("fabric_mass,0.2,", "fabric_mass,0.25,"),
        encoding="utf-8",
    )
    changed = apply_inputs(system, folder)
    assert {p.name: p.value for p in changed.parameters}["fabric_mass"] == 0.25
    assert content_hash(changed) != content_hash(system)


def test_a_renamed_case_column_is_a_delete_and_a_create(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "cases.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("parameter,small,", "parameter,compact,"),
        encoding="utf-8",
    )
    changed = apply_inputs(system, folder)
    names = [case.name for case in changed.cases]
    assert "small" not in names and "compact" in names


def test_a_removed_case_column_deletes_the_case(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "cases.csv"
    path.write_text("parameter,large\nfabric_mass,0.25\nwaste_rate,0.2\n", encoding="utf-8")
    changed = apply_inputs(system, folder)
    assert [case.name for case in changed.cases] == ["large"]


def test_a_removed_parameter_row_deletes_the_parameter(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    added = write_folder(tmp_path / "a", system)
    path = added / "inputs" / "input_parameters.csv"
    path.write_text(path.read_text(encoding="utf-8") + "load_factor,0.8,,\n", encoding="utf-8")
    grown = apply_inputs(system, added)
    assert "load_factor" in {p.name for p in grown.parameters}
    removed = write_folder(tmp_path / "b", grown)
    path = removed / "inputs" / "input_parameters.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("load_factor,0.8,,\n", ""), encoding="utf-8"
    )
    assert "load_factor" not in {p.name for p in apply_inputs(grown, removed).parameters}


def test_a_document_that_moved_is_refused_naming_both_hashes(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    moved = system.model_copy(deep=True)
    moved.parameters[0].value = 0.4
    with pytest.raises(Conflict) as caught:
        apply_inputs(moved, folder)
    assert content_hash(system) in str(caught.value)
    assert content_hash(moved) in str(caught.value)


def test_an_edited_model_file_is_refused_rather_than_ignored(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    raw = yaml.safe_load((folder / "model.yaml").read_text(encoding="utf-8"))
    raw["processes"][0]["name"] = "edited beside the tables"
    (folder / "model.yaml").write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(Conflict) as caught:
        apply_inputs(system, folder)
    assert "model.yaml" in str(caught.value)


def test_an_added_parameter_row_is_applied(tmp_path: Path, product_system: ProductSystem) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(path.read_text(encoding="utf-8") + "load_factor,0.8,,\n", encoding="utf-8")
    changed = apply_inputs(system, folder)
    assert {p.name: p.value for p in changed.parameters}["load_factor"] == 0.8


def test_a_description_edited_alone_is_written_although_the_hash_did_not_move(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("Fabric per shirt", "Fabric mass per shirt"),
        encoding="utf-8",
    )
    changed = apply_inputs(system, folder)
    described = {p.name: p.description for p in changed.parameters}
    assert described["fabric_mass"] == "Fabric mass per shirt"
    # the projection the hash is over carries no description
    assert content_hash(changed) == content_hash(system)


def test_a_case_column_naming_a_formula_parameter_is_refused_by_the_space(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    (folder / "inputs" / "cases.csv").write_text(
        "parameter,small,large\nfibre_mass,1.0,2.0\n", encoding="utf-8"
    )
    with pytest.raises(Invalid, match="not literal parameters"):
        apply_inputs(system, folder)


def test_an_upload_that_changes_nothing_at_all_says_so(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    bare = product_system.model_copy(deep=True)
    bare.parameters = []
    bare.cases = []
    folder = write_folder(tmp_path, bare)
    with pytest.raises(Invalid, match="carry nothing"):
        apply_inputs(bare, folder)
