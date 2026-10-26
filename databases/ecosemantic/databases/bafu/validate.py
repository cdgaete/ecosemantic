"""Compare a built BAFU bundle with the scores its published workbook holds, each cell in the
workbook's terms, and hold the differences it knows to a list."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ecosemantic.databases.bafu.differences import (
    Difference,
    read_differences,
    write_differences,
)
from ecosemantic.databases.bafu.profile import Column, Profile, Validated
from ecosemantic.databases.bafu.workbook import Workbook, matched, read_workbook
from ecosemantic.databases.checks import unnamed
from ecosemantic.databases.lists import (
    distinct_unlinked,
    flow_categories,
    process_ids,
    unlinked_mismatches,
)
from ecosemantic.databases.scores import (
    Scores,
    per_unit,
    relative_differences,
    score_every_dataset,
)
from ecosemantic.errors import Invalid
from ecosemantic.package.background import Dataset, Import, Key, read_background

Cell = tuple[str, str]


@dataclass(frozen=True)
class ColumnDifferences:
    """The pairs beyond the tolerance in one workbook column: how many, and the largest relative
    difference among them."""

    count: int
    largest_rel_diff: float


@dataclass(frozen=True)
class Validation:
    """What a validation measured: the processes and columns it compared, every pair beyond the
    tolerance, the largest relative difference inside it, every mismatch, the differences counted
    by column, and the seconds each step took."""

    processes: int
    columns: int
    differences: tuple[Difference, ...]
    largest_rel_diff_within_tolerance: float
    mismatches: tuple[str, ...]
    seconds: dict[str, float]
    by_column: dict[str, ColumnDifferences]

    def counted(self) -> Counted:
        """The validation as the command answers it, its pairs counted by column rather than
        listed."""
        return Counted(
            processes=self.processes,
            columns=self.columns,
            differences_by_column=self.by_column,
            largest_rel_diff_within_tolerance=self.largest_rel_diff_within_tolerance,
            mismatches=self.mismatches,
            seconds=self.seconds,
        )


@dataclass(frozen=True)
class Counted:
    """A validation as the command answers it: every count and mismatch, the pairs beyond the
    tolerance counted by column because the list runs to thousands of pairs."""

    processes: int
    columns: int
    differences_by_column: dict[str, ColumnDifferences]
    largest_rel_diff_within_tolerance: float
    mismatches: tuple[str, ...]
    seconds: dict[str, float]


def _datasets(imported: Import) -> dict[str, list[tuple[Key, Dataset]]]:
    """Every process's id to the datasets the import holds of it, whose own codes begin with it."""
    found: dict[str, list[tuple[Key, Dataset]]] = {}
    for key, dataset in imported.datasets.items():
        found.setdefault(key[1].split("_", 1)[0], []).append((key, dataset))
    return found


def _dataset(held: Mapping[str, list[tuple[Key, Dataset]]], process: str) -> tuple[Key, Dataset]:
    """The one dataset a process has, and the key it is held under; none or several is `Invalid`
    naming the process."""
    found = held.get(process, [])
    if len(found) != 1:
        names = ", ".join(key[1] for key, _ in found) or "none"
        raise Invalid(f"process {process} has {len(found)} datasets, not one: {names}")
    return found[0]


def _labels(imported: Import) -> dict[str, str]:
    """Every dataset's name and location code as `<name> - <location code>`, to the id of the
    process it belongs to; a label two processes carry is `Invalid` naming both."""
    labels: dict[str, str] = {}
    for key, dataset in imported.datasets.items():
        label = f"{dataset['name']} - {dataset['location']}"
        process = key[1].split("_", 1)[0]
        known = labels.setdefault(label, process)
        if known != process:
            raise Invalid(f"the label {label!r} names two processes, {known} and {process}")
    return labels


def _production(dataset: Dataset) -> float:
    """A dataset's production: the amount of its one production row, negative for a dataset whose
    reference is a treated waste."""
    amounts = [
        float(cast(float, row["amount"]))
        for row in cast(list[Dataset], dataset["exchanges"])
        if row["type"] == "production"
    ]
    if len(amounts) != 1:
        raise Invalid(f"a dataset has {len(amounts)} production rows, not one")
    return amounts[0]


def _cell(score: float, declared: str, unit: str, production: float) -> float:
    """A core score in the workbook's terms: per one unit of the unit the row's column D names,
    with the sign of the dataset's production."""
    return per_unit(score, declared, unit) * math.copysign(1.0, production)


def _score(scores: Scores, code: str, column: Column) -> float:
    """The core's score of a dataset under the method and category a workbook column names."""
    key = (code, column.method, column.category)
    if key not in scores.values:
        raise Invalid(
            f"{column.header!r} names {column.method}, {column.category}, and the import "
            "scores no such category"
        )
    return scores.values[key]


def _total(
    scores: Scores, profile: Profile, code: str, declared: str, unit: str, production: float
) -> float:
    """The core's score of a dataset summed over the profile's columns of the total's method, each
    converted and signed as its column is: the categories the workbook's total sums."""
    return sum(
        _cell(_score(scores, code, column), declared, unit, production)
        for column in profile.columns
        if column.method == profile.total.method
    )


def _compared(
    imported: Import,
    profile: Profile,
    workbook: Workbook,
    rows: Mapping[int, str],
    scores: Scores,
) -> tuple[dict[Cell, float], dict[Cell, float]]:
    """Each compared cell's core score in the workbook's terms and the workbook's value for it:
    every profile column and the total column, for every row the workbook scores, a cell the
    workbook leaves empty being no cell at all."""
    held = _datasets(imported)
    core: dict[Cell, float] = {}
    other: dict[Cell, float] = {}
    for row in workbook.rows:
        process = rows[row.row]
        key, dataset = _dataset(held, process)
        code = key[1]
        production = _production(dataset)
        declared = scores.declared[code]
        for column in profile.columns:
            if column.header not in row.values:
                continue
            core[(process, column.header)] = _cell(
                _score(scores, code, column), declared, row.unit, production
            )
            other[(process, column.header)] = row.values[column.header]
        if profile.total.header in row.values:
            core[(process, profile.total.header)] = _total(
                scores, profile, code, declared, row.unit, production
            )
            other[(process, profile.total.header)] = row.values[profile.total.header]
    return core, other


def _differences(
    core: Mapping[Cell, float], other: Mapping[Cell, float], tolerance: float
) -> tuple[dict[Cell, float], float, dict[str, ColumnDifferences]]:
    """Every pair beyond the tolerance with how far apart it is, the largest difference inside it,
    and the pairs beyond it counted by workbook column."""
    relative = relative_differences(core, other, group=lambda key: key[1])
    beyond = {key: value for key, value in relative.items() if value > tolerance}
    within = [value for key, value in relative.items() if key not in beyond]
    by_column: dict[str, ColumnDifferences] = {}
    for key, value in sorted(beyond.items()):
        known = by_column.get(key[1])
        by_column[key[1]] = ColumnDifferences(
            count=1 if known is None else known.count + 1,
            largest_rel_diff=value if known is None else max(known.largest_rel_diff, value),
        )
    return beyond, max(within, default=0.0), by_column


def _apart(key: Cell, core: Mapping[Cell, float], other: Mapping[Cell, float]) -> str:
    """One compared pair named by its process and column, with both scores."""
    return f"{key[0]} under {key[1]!r}: the core scores {core[key]!r}, the workbook {other[key]!r}"


def _listed(
    beyond: Mapping[Cell, float],
    core: Mapping[Cell, float],
    other: Mapping[Cell, float],
    path: Path,
) -> list[str]:
    """Every pair beyond the tolerance that a list lacks, and every pair a list holds that the run
    compares within it; a pair a list holds that the run does not compare is not compared."""
    listed = {(row.process_id, row.column) for row in read_differences(path)}
    found = [
        f"{_apart(key, core, other)}, {difference:.3e} apart, and the differences list lacks it"
        for key, difference in sorted(beyond.items())
        if key not in listed
    ]
    return found + [
        f"{_apart(pair, core, other)}, within the tolerance, and the differences list holds it"
        for pair in sorted((listed & set(core)) - set(beyond))
    ]


def validate(
    bundle: Path,
    *,
    results: Path,
    profile: Profile,
    unlinked: Path | None,
    differences: Path | None,
    compiled: Path | None = None,
) -> Validation:
    """Read a bundle with the core's importer, check that every factor names a flow of it, every
    linked input a process of it, and that its unlinked inputs are the list named, then compile it
    and score one unit of every process under every category.

    Each workbook row names its process by `<name> - <location code>`, and the core's score of
    that process's dataset under a column's method and category is compared in the workbook's
    terms: converted through the unit table to the unit the row's column D names, and signed by the
    dataset's production, so a waste treatment the core produces at minus one unit is compared per
    the unit the workbook treats. The total column is compared against the sum of the method's
    categories. A pair beyond the profile's tolerance is a difference; when a differences list is
    named, a difference the list lacks and a pair the list holds within the tolerance are
    mismatches, and with no list the differences are answered and not compared."""
    seconds: dict[str, float] = {}
    started = time.perf_counter()

    def lap(step: str) -> None:
        nonlocal started
        now = time.perf_counter()
        seconds[step] = now - started
        started = now

    imported = read_background(bundle, bundle.stem, foreground=frozenset())
    lap("read")
    processes = process_ids(imported)
    mismatches = unnamed(imported) + unlinked_mismatches(
        distinct_unlinked(imported, flow_categories(imported)), unlinked, processes
    )
    lap("checks")
    workbook = read_workbook(results)
    rows = matched(workbook, _labels(imported))
    lap("workbook")
    scores = score_every_dataset(imported, name=bundle.stem, compiled=compiled)
    seconds |= scores.seconds
    core, other = _compared(imported, profile, workbook, rows, scores)
    beyond, largest, by_column = _differences(core, other, profile.tolerance)
    if differences is not None:
        mismatches += _listed(beyond, core, other, differences)
    lap("compare")
    return Validation(
        processes=len(rows),
        columns=len(profile.columns),
        differences=tuple(
            Difference(process_id=process, column=column) for process, column in sorted(beyond)
        ),
        largest_rel_diff_within_tolerance=largest,
        mismatches=tuple(mismatches),
        seconds=seconds,
        by_column=by_column,
    )


def record(profile: Profile, validation: Validation, *, directory: Path) -> Path:
    """Write a passing run's known differences beside the profile and its validated block into
    `<directory>/<version>.yaml`, keeping every other key; refused while the run found a
    mismatch."""
    if validation.mismatches:
        raise Invalid(
            f"{len(validation.mismatches)} mismatches, the first: {validation.mismatches[0]}"
        )
    write_differences(directory / profile.differences, validation.differences)
    updated = profile.model_copy(
        update={
            "validated": Validated(
                processes=validation.processes,
                columns=len(profile.columns),
                differences=len(validation.differences),
                largest_rel_diff_within_tolerance=validation.largest_rel_diff_within_tolerance,
            )
        }
    )
    path = directory / f"{profile.version}.yaml"
    path.write_text(
        yaml.safe_dump(updated.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    return path
