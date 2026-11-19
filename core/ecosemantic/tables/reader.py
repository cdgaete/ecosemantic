"""Reading a folder's inputs: the parameter space it carries, with every bad cell named."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import cast, get_args

import yaml
from pydantic import ValidationError

from ecosemantic.compute.edits import set_parameter_space
from ecosemantic.compute.parameters import materialize
from ecosemantic.errors import Conflict, Invalid, NotFound, Refusal, Refused, said
from ecosemantic.model.canonical import canonical_model, content_hash
from ecosemantic.model.entities import (
    Case,
    Parameter,
    ProductSystem,
    Uncertainty,
    UncertaintyType,
    takes,
)
from ecosemantic.tables.folder import (
    CASES,
    DEPENDENT_PARAMETERS,
    DISTRIBUTION_COLUMNS,
    FORMAT,
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
    """A CSV file's header and its rows, a row's cells past its last written one read as the
    blanks they hold."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, restval="")
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


def _type(file: str, row: int, text: str, found: list[Refusal]) -> UncertaintyType | None:
    """The distribution type a cell names, or None after a refusal naming the types the model
    holds."""
    if text in get_args(UncertaintyType):
        return cast(UncertaintyType, text)
    found.append(
        Refusal(
            file=file,
            row=row,
            column="distribution",
            found=text,
            reason=f"a distribution is {', '.join(get_args(UncertaintyType))} or blank",
        )
    )
    return None


def _distribution(
    file: str, row: int, line: dict[str, str], found: list[Refusal]
) -> Uncertainty | None:
    """The distribution a row's cells state, none for a row that states none; a cell the type
    does not take, a type the model does not know and a distribution the model refuses are each a
    Refusal naming file, row and column."""
    named = line["distribution"].strip()
    if not named:
        for column in DISTRIBUTION_COLUMNS[1:]:
            if line[column].strip():
                found.append(
                    Refusal(
                        file=file,
                        row=row,
                        column=column,
                        found=line[column],
                        reason="a parameter with no distribution takes no cell of one",
                    )
                )
        return None
    type = _type(file, row, named, found)
    if type is None:
        return None
    params: dict[str, float | bool] = {}
    for column in DISTRIBUTION_COLUMNS[1:]:
        text = line[column].strip()
        if not text:
            continue
        if column not in takes(type):
            found.append(
                Refusal(
                    file=file,
                    row=row,
                    column=column,
                    found=text,
                    reason=f"a {type} takes no {column}",
                )
            )
            continue
        if column == "negative":
            if text != "true":
                found.append(
                    Refusal(
                        file=file,
                        row=row,
                        column=column,
                        found=text,
                        reason="negative is true or blank",
                    )
                )
                continue
            params[column] = True
            continue
        value = _number(file, row, column, text, found)
        if value is not None:
            params[column] = value
    try:
        return Uncertainty(type=type, params=params)
    except ValidationError as error:
        found.append(
            Refusal(
                file=file,
                row=row,
                column="distribution",
                found=named,
                reason=said(error.errors()[0]["msg"]),
            )
        )
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
    uncertainty: Uncertainty | None = None,
) -> Parameter | None:
    try:
        return Parameter(
            name=name,
            value=value,
            formula=formula,
            unit=unit,
            description=description,
            uncertainty=uncertainty,
        )
    except ValidationError as error:
        found.append(
            Refusal(
                file=file,
                row=row,
                column="name",
                found=name,
                reason=said(error.errors()[0]["msg"]),
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
            uncertainty=_distribution(INPUT_PARAMETERS, row, line, found),
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
    stated = schema["format"]
    if stated != FORMAT:
        raise Invalid(f"{schema_file} states format {stated}; this reader reads format {FORMAT}")
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
