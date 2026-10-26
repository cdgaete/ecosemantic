from __future__ import annotations

import csv
from pathlib import Path

import yaml

from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import slug
from ecosemantic.tables.folder import (
    FORMULA_COLUMNS,
    LITERAL_COLUMNS,
    folder_name,
    read_model,
    write_folder,
)


def spaced(product_system: ProductSystem) -> ProductSystem:
    """The fixture document with a unit, a description, and one case value only `large` sets.

    The fixture already carries three literal parameters, one formula parameter over them and
    two cases; this adds only what the tables have columns for and cannot otherwise show.
    """
    out = product_system.model_copy(deep=True)
    for parameter in out.parameters:
        if parameter.name == "fabric_mass":
            parameter.unit = "kg"
            parameter.description = "Fabric per shirt"
    for case in out.cases:
        if case.name == "small":
            case.description = "A small shirt."
        if case.name == "large":
            case.values["waste_rate"] = 0.2
    return out


def test_the_folder_is_named_for_the_system_and_the_head_of_its_id(
    product_system: ProductSystem,
) -> None:
    assert slug("Battery pack (NMC)", "-") == "battery-pack-nmc"
    name = folder_name(product_system)
    assert name == f"{slug(product_system.name, '-')}-{str(product_system.id)[:8]}"


def test_the_model_file_holds_the_model_without_the_parameter_space(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    raw = yaml.safe_load((folder / "model.yaml").read_text())
    assert "parameters" not in raw and "cases" not in raw and "hash" not in raw
    assert raw["id"] == str(system.id)
    assert len(raw["processes"]) == len(system.processes)
    assert read_model(folder).processes == system.processes
    assert read_model(folder).reference_process == system.reference_process == "tshirt"


def test_the_input_tables_split_literal_from_formula(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, spaced(product_system))
    literal = list(csv.DictReader((folder / "inputs" / "input_parameters.csv").open()))
    assert [row["name"] for row in literal] == [
        "fabric_mass",
        "waste_rate",
        "elec_per_kg",
        "organic_share",
    ]
    assert literal[0] == {
        "name": "fabric_mass",
        "value": "0.2",
        "unit": "kg",
        "description": "Fabric per shirt",
    }
    formula = list(csv.DictReader((folder / "inputs" / "dependent_parameters.csv").open()))
    assert formula == [
        {
            "name": "fibre_mass",
            "formula": "fabric_mass * (1 + waste_rate)",
            "unit": "kilogram",
            "description": "",
        }
    ]


def test_the_case_table_is_a_grid_with_a_blank_for_the_base_value(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, spaced(product_system))
    rows = list(csv.reader((folder / "inputs" / "cases.csv").open()))
    assert rows[0] == ["parameter", "small", "large"]
    assert rows[1] == ["fabric_mass", "0.15", "0.25"]
    # blank where the case leaves the base value
    assert rows[2] == ["waste_rate", "", "0.2"]


def test_the_schema_carries_the_hash_the_files_were_rendered_at(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    folder = write_folder(tmp_path, system)
    schema = yaml.safe_load((folder / "inputs" / "schema.yaml").read_text())
    assert schema["format"] == 1
    assert schema["product_system"]["at_hash"] == content_hash(system)
    assert schema["product_system"]["id"] == str(system.id)
    assert set(schema["files"]) == {
        "input_parameters.csv",
        "dependent_parameters.csv",
        "cases.csv",
    }
    assert schema["files"]["input_parameters.csv"]["columns"]["name"]["key"] is True
    assert schema["cases"]["small"]["description"] == "A small shirt."


def test_writing_twice_produces_the_same_bytes(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spaced(product_system)
    first = (write_folder(tmp_path / "a", system) / "inputs" / "cases.csv").read_bytes()
    second = (write_folder(tmp_path / "b", system) / "inputs" / "cases.csv").read_bytes()
    assert first == second


def test_the_schema_names_the_columns_the_tables_carry(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, product_system)
    schema = yaml.safe_load((folder / "inputs" / "schema.yaml").read_text(encoding="utf-8"))
    for file, columns in (
        ("input_parameters.csv", LITERAL_COLUMNS),
        ("dependent_parameters.csv", FORMULA_COLUMNS),
    ):
        with (folder / "inputs" / file).open(newline="", encoding="utf-8") as handle:
            assert next(csv.reader(handle)) == columns
        assert list(schema["files"][file]["columns"]) == columns
