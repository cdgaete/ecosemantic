from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.errors import NotFound, Refused
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.tables import folder as written
from ecosemantic.tables import reader
from ecosemantic.tables.folder import write_folder
from ecosemantic.tables.reader import read_inputs
from tests.tables.test_folder import spaced


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
        "name,value,unit,description\n"
        "transport_km,about 120,km,Road distance\n"
        "transport_km,5,km,\n"
        ",7,,\n",
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
    path.write_text("name,value,unit,description,owner\ntransport_km,1,km,,me\n", encoding="utf-8")
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
    path.write_text("name,value,unit,description\n2fast,1,km,\n", encoding="utf-8")
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
