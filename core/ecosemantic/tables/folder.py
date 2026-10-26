"""Writing a product system as a folder: the model in YAML, the parameter space in CSV."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from ecosemantic.compute.parameters import case_matrix
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.model.refs import slug

FORMAT = 1
MODEL_FILE = "model.yaml"
INPUTS_DIR = "inputs"
SCHEMA_FILE = "schema.yaml"
INPUT_PARAMETERS = "input_parameters.csv"
DEPENDENT_PARAMETERS = "dependent_parameters.csv"
CASES = "cases.csv"
PARAMETER_COLUMN = "parameter"

_LITERAL_SCHEMA: dict[str, dict[str, object]] = {
    "name": {"type": "string", "key": True},
    "value": {"type": "number"},
    "unit": {"type": "string"},
    "description": {"type": "string"},
}
_FORMULA_SCHEMA: dict[str, dict[str, object]] = {
    "name": {"type": "string", "key": True},
    "formula": {"type": "string"},
    "unit": {"type": "string"},
    "description": {"type": "string"},
}
LITERAL_COLUMNS = list(_LITERAL_SCHEMA)
FORMULA_COLUMNS = list(_FORMULA_SCHEMA)


def folder_name(system: ProductSystem) -> str:
    """The directory one product system takes, so two systems sharing a name stay apart."""
    return f"{slug(system.name, '-')}-{str(system.id)[:8]}"


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """One table, with the line ending fixed so a rewrite with no edit produces no diff."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def number(value: float | None) -> str:
    """A cell holding a number, blank where there is none."""
    return "" if value is None else repr(value)


def _schema(system: ProductSystem) -> dict[str, object]:
    return {
        "format": FORMAT,
        "product_system": {
            "id": str(system.id),
            "name": system.name,
            "at_hash": content_hash(system),
        },
        "files": {
            INPUT_PARAMETERS: {
                "description": "Literal parameters. The name is the key; edit the value.",
                "columns": _LITERAL_SCHEMA,
            },
            DEPENDENT_PARAMETERS: {
                "description": "Parameters derived by formula. The value is not written.",
                "columns": _FORMULA_SCHEMA,
            },
            CASES: {
                "description": (
                    "One column per case, one row per parameter a case sets. "
                    "A blank cell leaves the base value."
                ),
                "columns": {PARAMETER_COLUMN: {"type": "string", "key": True}},
            },
        },
        "cases": {case.name: {"description": case.description} for case in system.cases},
    }


def write_folder(root: Path, system: ProductSystem) -> Path:
    """Write the model and the parameter space under root, and answer the folder."""
    folder = root / folder_name(system)
    inputs = folder / INPUTS_DIR
    inputs.mkdir(parents=True, exist_ok=True)
    model = system.model_dump(mode="json", exclude={"parameters", "cases", "hash"})
    (folder / MODEL_FILE).write_text(
        yaml.safe_dump(model, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    write_csv(
        inputs / INPUT_PARAMETERS,
        LITERAL_COLUMNS,
        [
            {
                "name": p.name,
                "value": number(p.value),
                "unit": p.unit,
                "description": p.description,
            }
            for p in system.parameters
            if p.formula is None
        ],
    )
    write_csv(
        inputs / DEPENDENT_PARAMETERS,
        FORMULA_COLUMNS,
        [
            {
                "name": p.name,
                "formula": p.formula or "",
                "unit": p.unit,
                "description": p.description,
            }
            for p in system.parameters
            if p.formula is not None
        ],
    )
    matrix = case_matrix(system.cases)
    write_csv(
        inputs / CASES,
        [PARAMETER_COLUMN, *matrix.cases],
        [
            {PARAMETER_COLUMN: row.parameter}
            | {name: number(value) for name, value in zip(matrix.cases, row.values, strict=True)}
            for row in matrix.rows
        ],
    )
    (inputs / SCHEMA_FILE).write_text(
        yaml.safe_dump(_schema(system), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return folder


def read_model(folder: Path) -> ProductSystem:
    """The model the folder carries, without the parameter space the inputs hold."""
    raw = yaml.safe_load((folder / MODEL_FILE).read_text(encoding="utf-8"))
    return ProductSystem.model_validate(raw)
