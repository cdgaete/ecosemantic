"""Reading a folder's inputs: the parameter space it carries, with every bad cell named."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml
from pydantic import ValidationError

from ecosemantic.compute.edits import set_parameter_space
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Conflict, Invalid, NotFound, Refusal, Refused
from ecosemantic.model.canonical import canonical_model, content_hash
from ecosemantic.model.entities import Case, Parameter, ProductSystem
from ecosemantic.tables.folder import (
    CASES,
    DEPENDENT_PARAMETERS,
    FORMULA_COLUMNS,
    INPUT_PARAMETERS,
    INPUTS_DIR,
    LITERAL_COLUMNS,
    MODEL_FILE,
    PARAMETER_COLUMN,
    SCHEMA_FILE,
    read_model,
)


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """A CSV file's header and its rows."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        return header, [dict(row) for row in reader]


def _table(path: Path, expected: list[str], found: list[Refusal]) -> list[dict[str, str]]:
    """The file's rows, or none of them when its header is not the one the schema names."""
    header, rows = _read(path)
    unknown = [column for column in header if column not in expected]
    missing = [column for column in expected if column not in header]
    for column in unknown:
        found.append(
            Refusal(
                file=path.name,
                row=1,
                column=column,
                found=column,
                reason="the schema does not name this column",
            )
        )
    for column in missing:
        found.append(
            Refusal(
                file=path.name,
                row=1,
                column=column,
                found="",
                reason="the schema names this column and the file has not got it",
            )
        )
    return [] if unknown or missing else rows


def _number(file: str, row: int, column: str, text: str, found: list[Refusal]) -> float | None:
    try:
        return float(text)
    except ValueError:
        found.append(
            Refusal(file=file, row=row, column=column, found=text, reason="a number is required")
        )
        return None


def _key(
    file: str, row: int, column: str, text: str, seen: set[str], found: list[Refusal]
) -> str | None:
    if not text:
        reason = "the key is empty"
    elif text in seen:
        reason = "the key is already used"
    else:
        seen.add(text)
        return text
    found.append(Refusal(file=file, row=row, column=column, found=text, reason=reason))
    return None


def _parameter(
    file: str,
    row: int,
    found: list[Refusal],
    name: str,
    unit: str,
    description: str,
    value: float | None = None,
    formula: str | None = None,
) -> Parameter | None:
    try:
        return Parameter(
            name=name, value=value, formula=formula, unit=unit, description=description
        )
    except ValidationError as error:
        found.append(
            Refusal(
                file=file,
                row=row,
                column="name",
                found=name,
                reason=str(error.errors()[0]["msg"]),
            )
        )
        return None


def _parameters(inputs: Path, found: list[Refusal]) -> list[Parameter]:
    out: list[Parameter] = []
    seen: set[str] = set()
    for row, line in enumerate(_table(inputs / INPUT_PARAMETERS, LITERAL_COLUMNS, found), start=2):
        name = _key(INPUT_PARAMETERS, row, "name", line["name"], seen, found)
        value = _number(INPUT_PARAMETERS, row, "value", line["value"], found)
        if name is None or value is None:
            continue
        made = _parameter(
            INPUT_PARAMETERS,
            row,
            found,
            name=name,
            unit=line["unit"],
            description=line["description"],
            value=value,
        )
        if made is not None:
            out.append(made)
    table = _table(inputs / DEPENDENT_PARAMETERS, FORMULA_COLUMNS, found)
    for row, line in enumerate(table, start=2):
        name = _key(DEPENDENT_PARAMETERS, row, "name", line["name"], seen, found)
        if name is None:
            continue
        made = _parameter(
            DEPENDENT_PARAMETERS,
            row,
            found,
            name=name,
            unit=line["unit"],
            description=line["description"],
            formula=line["formula"],
        )
        if made is not None:
            out.append(made)
    return out


def _cases(inputs: Path, descriptions: dict[str, str], found: list[Refusal]) -> list[Case]:
    header, rows = _read(inputs / CASES)
    if not header or header[0] != PARAMETER_COLUMN:
        found.append(
            Refusal(
                file=CASES,
                row=1,
                column=header[0] if header else "",
                found=",".join(header),
                reason=f"the first column is {PARAMETER_COLUMN!r}",
            )
        )
        return []
    names = header[1:]
    for column in sorted({name for name in names if names.count(name) > 1}):
        found.append(
            Refusal(
                file=CASES, row=1, column=column, found=column, reason="the case is named twice"
            )
        )
    values: dict[str, dict[str, float]] = {name: {} for name in names}
    seen: set[str] = set()
    for row, line in enumerate(rows, start=2):
        parameter = _key(CASES, row, PARAMETER_COLUMN, line[PARAMETER_COLUMN], seen, found)
        if parameter is None:
            continue
        for name in names:
            text = line[name]
            if text == "":
                continue
            number = _number(CASES, row, name, text, found)
            if number is not None:
                values[name][parameter] = number
    return [
        Case(name=name, description=descriptions.get(name, ""), values=values[name])
        for name in dict.fromkeys(names)
    ]


def read_inputs(folder: Path) -> tuple[list[Parameter], list[Case], str]:
    """The parameter space the folder's inputs carry, and the hash they were rendered at."""
    inputs = folder / INPUTS_DIR
    schema_file = inputs / SCHEMA_FILE
    if not schema_file.is_file():
        raise NotFound(f"no {INPUTS_DIR}/{SCHEMA_FILE} in {folder}")
    schema = yaml.safe_load(schema_file.read_text(encoding="utf-8"))
    at_hash = str(schema["product_system"]["at_hash"])
    descriptions = {
        name: str(body.get("description", "")) for name, body in (schema.get("cases") or {}).items()
    }
    found: list[Refusal] = []
    parameters = _parameters(inputs, found)
    cases = _cases(inputs, descriptions, found)
    if found:
        raise Refused(found)
    return parameters, cases, at_hash


def apply_inputs(stored: ProductSystem, folder: Path) -> ProductSystem:
    """The stored document with the folder's parameter space applied, under a two-sided guard.

    The folder's hash must be the document's, so a store that moved is refused; and the
    folder's model must be the document's, so a model edited beside the tables is refused
    rather than silently left out of a write that carries only the parameter space.
    """
    parameters, cases, at_hash = read_inputs(folder)
    stored_hash = content_hash(stored)
    if at_hash != stored_hash:
        raise Conflict(
            f"the folder was rendered at {at_hash} and {stored.name!r} is at "
            f"{stored_hash}; export the folder again"
        )
    if canonical_model(read_model(folder)) != canonical_model(stored):
        raise Conflict(
            f"{MODEL_FILE} was edited beside the tables; this path writes the parameter space alone"
        )
    kept = {parameter.name for parameter in parameters}
    named = {case.name for case in cases}
    delete_parameters = [p.name for p in stored.parameters if p.name not in kept]
    delete_cases = [c.name for c in stored.cases if c.name not in named]
    if not (parameters or cases or delete_parameters or delete_cases):
        raise Invalid(f"the inputs under {folder} carry nothing, and neither does {stored.name!r}")
    return set_parameter_space(
        stored,
        parameters=parameters,
        cases=cases,
        delete_parameters=delete_parameters,
        delete_cases=delete_cases,
    )


def assemble(folder: Path) -> ProductSystem:
    """The whole document a folder carries: its model with its parameter space applied, its hash
    set to the state read, as a package's is.

    A folder from another machine has no store behind it, so nothing is compared with a
    stored hash here; the folder is the document. A scenario it carries applies while that
    state is the one the scenario is pinned to, and an edited input is another state.
    """
    model = read_model(folder)
    parameters, cases, _ = read_inputs(folder)
    model.parameters = list(parameters)
    model.cases = list(cases)
    model.hash = content_hash(model)
    return materialize(model)
