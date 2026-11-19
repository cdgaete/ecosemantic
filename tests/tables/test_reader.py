from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from ecosemantic.errors import Invalid, NotFound, Refused
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.tables import folder as written
from ecosemantic.tables import reader
from ecosemantic.tables.folder import LITERAL_COLUMNS, write_folder
from ecosemantic.tables.reader import read_inputs
from tests.tables.test_folder import spaced, spread

HEADER = ",".join(LITERAL_COLUMNS)


def row(*cells: str) -> str:
    """One literal table row, its cells the writer's order and the rest blank."""
    return ",".join([*cells, *[""] * (len(LITERAL_COLUMNS) - len(cells))])


def rendered(tmp_path: Path, product_system: ProductSystem) -> tuple[Path, ProductSystem]:
    system = spaced(product_system)
    return write_folder(tmp_path, system), system


def test_an_unedited_folder_reads_back_the_space_it_was_written_from(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder, system = rendered(tmp_path, product_system)
    parameters, cases, at_hash = read_inputs(folder)
    assert at_hash == content_hash(system)
    assert {p.name: p.value for p in parameters} == {
        "fabric_mass": 0.2,
        "waste_rate": 0.1,
        "elec_per_kg": 1.5,
        "fibre_mass": None,
        "organic_share": 0.0,
    }
    assert {p.name: p.formula for p in parameters}["fibre_mass"] == "fabric_mass * (1 + waste_rate)"
    assert {c.name: c.values for c in cases} == {
        "small": {"fabric_mass": 0.15},
        "large": {"fabric_mass": 0.25, "waste_rate": 0.2},
    }


def test_a_parameters_distribution_survives_a_tables_round_trip(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    system = spread(product_system)
    folder = write_folder(tmp_path, system)
    parameters, _, at_hash = read_inputs(folder)
    back = {p.name: p for p in parameters}
    assert at_hash == content_hash(system)
    assert back["waste_rate"].uncertainty == system.parameter("waste_rate").uncertainty
    assert back["waste_rate"].uncertainty.bounds() == (0.05, 0.2)
    assert back["organic_share"].uncertainty == system.parameter("organic_share").uncertainty
    assert back["organic_share"].uncertainty.bounds() == (-0.1, 0.1)
    assert back["fabric_mass"].uncertainty is None
    assert back["waste_credit"].uncertainty == system.parameter("waste_credit").uncertainty
    assert back["waste_credit"].uncertainty.params["negative"] is True


def test_a_distribution_cell_the_type_does_not_take_is_refused_by_row_and_column(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    stated = row("fabric_mass", "0.2", "kg", "", "triangular", "2.0", "", "1.0", "3.0", "true")
    path.write_text(f"{HEADER}\n{stated}\n", encoding="utf-8")
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    assert [(r.file, r.row, r.column) for r in caught.value.refusals] == [
        ("input_parameters.csv", 2, "negative")
    ]
    assert "triangular takes no negative" in caught.value.refusals[0].reason


def test_a_distribution_cell_stated_without_a_type_is_refused(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        f"{HEADER}\n{row('fabric_mass', '0.2', 'kg', '', '', '', '0.2')}\n", encoding="utf-8"
    )
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    assert [(r.row, r.column) for r in caught.value.refusals] == [(2, "scale")]


def test_a_type_the_model_does_not_know_is_refused_by_the_distribution_cell(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(
        f"{HEADER}\n{row('fabric_mass', '0.2', 'kg', '', 'gamma', '1.0', '0.2')}\n",
        encoding="utf-8",
    )
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    refusal = caught.value.refusals[0]
    assert (refusal.row, refusal.column, refusal.found) == (2, "distribution", "gamma")
    assert "lognormal, normal, uniform, triangular" in refusal.reason


def test_a_distribution_the_model_refuses_names_the_distribution_cell(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder = write_folder(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    stated = row("fabric_mass", "0.2", "kg", "", "lognormal", repr(math.log(0.2)), "0.0")
    path.write_text(f"{HEADER}\n{stated}\n", encoding="utf-8")
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    refusal = caught.value.refusals[0]
    assert (refusal.row, refusal.column) == (2, "distribution")
    assert refusal.reason == "scale must be > 0"


def test_a_folder_of_format_1_is_refused(tmp_path: Path, product_system: ProductSystem) -> None:
    folder = write_folder(tmp_path, product_system)
    path = folder / "inputs" / "schema.yaml"
    schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema["format"] = 1
    path.write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")
    with pytest.raises(Invalid, match="states format 1; this reader reads format 2"):
        read_inputs(folder)


def test_a_blank_case_cell_leaves_the_base_value_and_is_not_a_zero(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder, _ = rendered(tmp_path, product_system)
    _, cases, _ = read_inputs(folder)
    assert "waste_rate" not in {c.name: c.values for c in cases}["small"]


def test_every_bad_cell_is_named_and_nothing_is_read(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder, _ = rendered(tmp_path, product_system)
    literal = folder / "inputs" / "input_parameters.csv"
    literal.write_text(
        f"{HEADER}\n"
        f"{row('transport_km', 'about 120', 'km', 'Road distance')}\n"
        f"{row('transport_km', '5', 'km')}\n"
        f"{row('', '7')}\n",
        encoding="utf-8",
    )
    cases = folder / "inputs" / "cases.csv"
    cases.write_text("parameter,lean,heavy\ntransport_km,eighty,300.0\n", encoding="utf-8")
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    seen = {(r.file, r.row, r.column, r.reason) for r in caught.value.refusals}
    assert ("input_parameters.csv", 2, "value", "a number is required") in seen
    assert ("input_parameters.csv", 3, "name", "the key is already used") in seen
    assert ("input_parameters.csv", 4, "name", "the key is empty") in seen
    assert ("cases.csv", 2, "lean", "a number is required") in seen
    assert len(caught.value.refusals) == 4


def test_a_column_the_schema_does_not_name_is_refused(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder, _ = rendered(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(f"{HEADER},owner\n{row('transport_km', '1', 'km')},me\n", encoding="utf-8")
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    assert [(r.column, r.reason) for r in caught.value.refusals] == [
        ("owner", "the schema does not name this column")
    ]


def test_a_parameter_name_the_model_refuses_is_refused_by_cell(
    tmp_path: Path, product_system: ProductSystem
) -> None:
    folder, _ = rendered(tmp_path, product_system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(f"{HEADER}\n{row('2fast', '1', 'km')}\n", encoding="utf-8")
    with pytest.raises(Refused) as caught:
        read_inputs(folder)
    assert caught.value.refusals[0].column == "name"
    assert caught.value.refusals[0].found == "2fast"


def test_a_folder_with_no_schema_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFound):
        read_inputs(tmp_path)


def test_the_reader_expects_the_columns_the_writer_writes() -> None:
    assert reader.LITERAL_COLUMNS is written.LITERAL_COLUMNS
    assert reader.FORMULA_COLUMNS is written.FORMULA_COLUMNS
    assert reader.PARAMETER_COLUMN is written.PARAMETER_COLUMN
