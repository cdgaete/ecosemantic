"""Compare a built bundle with a release's matrix export and cumulative LCIA."""

from __future__ import annotations

import csv
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

import numpy as np
from python_calamine import CalamineWorkbook
from scipy.sparse import csr_matrix, diags, lil_matrix

from ecosemantic.databases.ecoinvent.masterdata import unit_name
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.engine.solver import Solver
from ecosemantic.errors import Invalid
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import Database
from ecosemantic.package.background import Dataset, Import, read_background
from ecosemantic.package.compile import compile_background

TOLERANCE = 1e-6
_LIMIT = 50
_CUMULATIVE_SHEET = "LCIA"
_CUMULATIVE_START = 6
_MATRICES = ("A", "B", "C")
_AGAINST_MATRIX_EXPORT = "scores_against_matrix_export"
_LARGEST_KINDS = (*_MATRICES, "units", "scores", _AGAINST_MATRIX_EXPORT, "workbook_disagrees")


@dataclass(frozen=True)
class Validation:
    """What a validation measured: the bundle's counts, the largest relative difference of each
    kind, every mismatch up to fifty, the categories no reference names, the seconds each step
    took and the bytes the compiled background takes on disk."""

    counts: dict[str, int]
    largest_rel_diff: dict[str, float]
    mismatches: list[str]
    unreferenced: list[str]
    seconds: dict[str, float]
    saved_bytes: int


@dataclass(frozen=True)
class _Activity:
    """An activity as the matrix export knows it: its unit, its matrix positions and the amount
    of the reference product it makes."""

    unit: str
    row: int
    column: int
    reference: float


@dataclass(frozen=True)
class _Flow:
    """An elementary flow of the bundle: its code, its unit and its biosphere row, absent when
    no exchange uses the flow."""

    code: str
    unit: str
    row: int | None


@dataclass(frozen=True)
class _Installed:
    """The compiled bundle as the comparison reads it: its datasets, its flows, each method's
    factors and the method itself, its A and B matrices, and the calculation over it."""

    activities: dict[tuple[str, str, str], _Activity]
    flows: dict[tuple[str, tuple[str, ...]], _Flow]
    methods: dict[tuple[str, ...], dict[str, float]]
    method_of: dict[tuple[str, ...], Method]
    catalog: list[tuple[str, str, str]]
    used_flows: list[tuple[str, tuple[str, ...]]]
    A: csr_matrix
    B: csr_matrix
    calculation: Calculation


@dataclass(frozen=True)
class _Export:
    """ecoinvent's matrix export and cumulative LCIA, in the export's own index order."""

    activities: list[tuple[str, str, str, str]]
    flows: list[tuple[str, str, str, str]]
    lcia: list[tuple[str, str, str, str]]
    A: csr_matrix
    B: csr_matrix
    C: csr_matrix
    cumulative_triples: list[tuple[str, str, str]]
    cumulative: dict[tuple[str, str, str], np.ndarray]


def _label(triple: tuple[str, str, str]) -> str:
    """A method, category and indicator as one name."""
    return " > ".join(triple)


def _differences(
    ours: np.ndarray, theirs: np.ndarray, reference: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One category's bundled scores and ecoinvent's, and their relative and absolute
    differences."""
    mine = ours[:, reference]
    scale = float(np.abs(theirs).max())
    denominator = np.maximum(np.maximum(np.abs(mine), np.abs(theirs)), 1e-12 * scale)
    difference = np.abs(mine - theirs)
    relative = np.divide(
        difference, denominator, out=np.zeros_like(difference), where=denominator > 0
    )
    return mine, difference, relative


def _matrix_export_scores(export: _Export, labels: Sequence[str]) -> dict[str, np.ndarray]:
    """The scores ecoinvent's matrix export implies, per dataset, for each named category: the
    export's own reference amount times ``C B A^-1``, solved by the engine's refined SuperLU as
    the bundle's are. A category whose cumulative workbook disagrees
    with these is compared against them instead. A named label that no category of the release's
    cumulative workbook or matrix export names is invalid."""
    known = {_label(tuple(triple[:3])) for triple in export.lcia} | {
        _label(triple) for triple in export.cumulative_triples
    }
    for label in labels:
        if label not in known:
            raise Invalid(
                f"workbook_disagrees names {label}, which no category of the release names"
            )
    wanted = [
        (position, _label(tuple(export.lcia[position][:3])))
        for position in range(len(export.lcia))
        if _label(tuple(export.lcia[position][:3])) in labels
    ]
    if not wanted:
        return {}
    rows = np.array([position for position, _label_ in wanted])
    amounts = np.asarray(export.A.diagonal()).ravel()
    characterised = np.asarray((export.C.tocsr()[rows] @ export.B).toarray())
    solved = Solver("superlu", export.A).adjoint(characterised.T)
    return {label: amounts * solved[:, index] for index, (_, label) in enumerate(wanted)}


def _score_label(
    triple: tuple[str, str, str],
    naturals: list[tuple[str, str, str]],
    mine: np.ndarray,
    theirs: np.ndarray,
    position: int,
) -> str:
    """One score's dataset, category and the two numbers."""
    return (
        f"score {naturals[position][0]} [{naturals[position][1]}] {_label(triple)}: "
        f"the bundle says {mine[position]}, ecoinvent {theirs[position]}"
    )


def _entries(matrix: csr_matrix) -> dict[tuple[int, int], float]:
    """A sparse matrix as its nonzero entries, keyed by position."""
    coo = matrix.tocoo()
    return {
        (int(row), int(column)): float(value)
        for row, column, value in zip(coo.row, coo.col, coo.data, strict=True)
    }


def _subset(matrix: csr_matrix, rows: list[int], columns: list[int]) -> csr_matrix:
    """A matrix's rows and columns, in the order given."""
    return matrix[rows][:, columns]


def _index(path: Path) -> list[tuple[str, str, str, str]]:
    """An index file's rows, every field text, placed at the index each row carries."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    out: list[tuple[str, str, str, str]] = [("", "", "", "")] * len(rows[1:])
    for row in rows[1:]:
        out[int(row[4])] = (row[0], row[1], row[2], row[3])
    return out


def _matrix(path: Path, rows: int, columns: int) -> csr_matrix:
    """A sparse matrix file, its header row skipped, every coefficient text read as a number."""
    row_index: list[int] = []
    column_index: list[int] = []
    data: list[float] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle, delimiter=";")
        next(reader)
        for row in reader:
            row_index.append(int(row[0]))
            column_index.append(int(row[1]))
            data.append(float(row[2]))
    return csr_matrix((data, (row_index, column_index)), shape=(rows, columns))


def _cumulative(
    path: Path,
) -> tuple[list[tuple[str, str, str]], dict[tuple[str, str, str], np.ndarray]]:
    """The cumulative LCIA's categories and each dataset's score under each of them."""
    sheet = CalamineWorkbook.from_path(str(path)).get_sheet_by_name(_CUMULATIVE_SHEET)
    rows = sheet.iter_rows()
    header = [[str(cell) for cell in next(rows)] for _ in range(3)]
    next(rows)
    columns = list(range(_CUMULATIVE_START, len(header[0])))
    triples = [(header[0][column], header[1][column], header[2][column]) for column in columns]
    scores: dict[tuple[str, str, str], np.ndarray] = {}
    for row in rows:
        cells = list(row)
        if len(cells) < _CUMULATIVE_START or not str(cells[0]):
            continue
        scores[(str(cells[1]), str(cells[2]), str(cells[3]))] = np.array(
            [float(cells[column]) for column in columns]
        )
    return triples, scores


def _read_export(release: Release) -> _Export:
    """A release's matrix export and cumulative LCIA."""
    directory = release.matrix
    activities = _index(directory / "ie_index.csv")
    flows = _index(directory / "ee_index.csv")
    lcia = _index(directory / "LCIA_index.csv")
    triples, cumulative = _cumulative(release.cumulative_lcia)
    return _Export(
        activities=activities,
        flows=flows,
        lcia=lcia,
        A=_matrix(directory / "A_public.csv", len(activities), len(activities)),
        B=_matrix(directory / "B_public.csv", len(flows), len(activities)),
        C=_matrix(directory / "C.csv", len(lcia), len(flows)),
        cumulative_triples=triples,
        cumulative=cumulative,
    )


def _installed(imported: Import, background: Background, calculation: Calculation) -> _Installed:
    """The compiled bundle as the comparison reads it: each dataset's and flow's name, unit and
    reference amount from the import, the matrices, the factors and the calculation from the
    background. A flow is used when its row of B holds an entry."""
    activities: dict[tuple[str, str, str], _Activity] = {}
    catalog: list[tuple[str, str, str]] = []
    for (_, code), dataset in imported.datasets.items():
        at = background.position("activity", code)
        if at is None:
            raise Invalid(f"dataset {code} is not in the compiled background")
        rows = cast(list[Dataset], dataset["exchanges"])
        reference = next(
            float(cast(float, row["amount"])) for row in rows if row["type"] == "production"
        )
        key = (str(dataset["name"]), str(dataset["location"]), str(dataset["reference product"]))
        activities[key] = _Activity(
            unit=str(dataset["unit"]), row=at, column=at, reference=reference
        )
        catalog.append(key)
    used = np.diff(calculation.biosphere.indptr) > 0
    flows: dict[tuple[str, tuple[str, ...]], _Flow] = {}
    used_flows: list[tuple[str, tuple[str, ...]]] = []
    for (_, code), flow in imported.flows.items():
        categories = tuple(str(category) for category in cast(tuple, flow["categories"]))
        at = background.position("flow", code)
        row = at if at is not None and bool(used[at]) else None
        flows[(str(flow["name"]), categories)] = _Flow(code=code, unit=str(flow["unit"]), row=row)
        if row is not None:
            used_flows.append((str(flow["name"]), categories))
    factors = calculation.characterization
    labels = background.coords["flow"].labels
    methods: dict[tuple[str, ...], dict[str, float]] = {}
    method_of: dict[tuple[str, ...], Method] = {}
    for position, method in enumerate(background.methods):
        start, end = factors.indptr[position], factors.indptr[position + 1]
        methods[method.tuple] = {
            str(labels[flow]): float(value)
            for flow, value in zip(factors.indices[start:end], factors.data[start:end], strict=True)
        }
        method_of[method.tuple] = method
    return _Installed(
        activities=activities,
        flows=flows,
        methods=methods,
        method_of=method_of,
        catalog=catalog,
        used_flows=used_flows,
        A=calculation.technosphere,
        B=calculation.biosphere,
        calculation=calculation,
    )


def _fold_self_consumption(
    A: csr_matrix, B: csr_matrix, reference: np.ndarray
) -> tuple[csr_matrix, csr_matrix, int]:
    """Fold each activity column as ecoinvent's matrix export states it: the column is scaled by
    the activity's reference-product amount over its net production, the column's diagonal, so
    its diagonal becomes the reference amount and an activity's consumption of its own product
    leaves the matrix. An activity that consumes none of its own product is unchanged."""
    diagonal = np.asarray(A.diagonal()).ravel()
    factor = np.divide(reference, diagonal, out=np.ones_like(reference), where=diagonal != 0)
    scale = diags(factor)
    return (A @ scale).tocsr(), (B @ scale).tocsr(), int(np.count_nonzero(factor != 1.0))


class _Report:
    """The bundle comparison's findings: the largest relative difference of each kind, every
    mismatch up to a limit, the categories no reference names, and the shape counts. Every score
    is compared strictly against its reference."""

    def __init__(self, tolerance: float) -> None:
        self.tolerance = tolerance
        self.mismatches: list[str] = []
        self.unreferenced: list[str] = []
        self.counts: dict[str, int] = {"workbook_disagreeing_scores": 0}
        self.largest: dict[str, float] = {kind: 0.0 for kind in _LARGEST_KINDS}

    def difference(self, kind: str, relative: float) -> None:
        """Raise the largest relative difference recorded for a kind."""
        self.largest[kind] = max(self.largest[kind], relative)

    def note(self, message: str) -> None:
        """Keep a mismatch, up to the limit."""
        if len(self.mismatches) < _LIMIT:
            self.mismatches.append(message)

    def entry(self, kind: str, relative: float, message: str) -> None:
        """Record one relative difference and, above the tolerance, its mismatch."""
        self.difference(kind, relative)
        if relative > self.tolerance:
            self.note(message)

    def scores(
        self, kind: str, tolerance: float, relative: np.ndarray, describe: Callable[[int], str]
    ) -> None:
        """Record one category's scores under its kind: the largest relative difference and every
        dataset above the tolerance as a mismatch."""
        if relative.size:
            self.difference(kind, float(relative.max()))
        for position in np.flatnonzero(relative > tolerance):
            self.note(describe(int(position)))


class _Comparison:
    """One compiled bundle against one release's matrix export, cumulative LCIA and scores."""

    def __init__(
        self,
        name: str,
        installed: _Installed,
        export: _Export,
        report: _Report,
        disagreeing: dict[str, tuple[np.ndarray, float]] | None = None,
    ) -> None:
        self.name = name
        self.report = report
        self.export = export
        self.installed = installed
        self.disagreeing = disagreeing or {}
        self.activity_keep: list[int] = []
        self.activity_columns: list[int] = []
        self.product_rows: list[int] = []
        self.reference: list[float] = []
        self.flow_keep: list[int] = []
        self.flow_rows: list[int] = []
        self.flow_positions: dict[int, int] = {}
        self.code_export: dict[str, int] = {}
        self.lcia_keep: list[int] = []
        self.lcia_positions: dict[tuple[str, str, str], int] = {}
        self.factors: list[dict[str, float]] = []
        self.methods: list[Method] = []
        self.A = csr_matrix((0, 0))
        self.B = csr_matrix((0, 0))
        self.amounts = np.zeros(0)

    def run(self) -> None:
        """Compare the bundle with the release's own numbers."""
        self._map_activities()
        self._map_flows()
        self._mirror()
        self._map_lcia()
        self._fold()
        self._compare_matrices()
        self._compare_scores()
        self._unreferenced()
        self.report.counts["datasets"] = len(self.export.activities)
        self.report.counts["flows"] = len(self.export.flows)
        self.report.counts["categories"] = len(self.lcia_keep)
        self.report.counts["categories_without_reference"] = len(self.report.unreferenced)

    def _natural(self, position: int) -> tuple[str, str, str]:
        name, location, product, _symbol = self.export.activities[position]
        return (name, location, product)

    def _compare_unit(self, owner: str, installed: str, symbol: str) -> None:
        expected = unit_name(symbol)
        if installed != expected:
            self.report.entry("units", 1.0, f"{owner} is {installed}, the export says {expected}")

    def _map_activities(self) -> None:
        for position, (name, location, product, symbol) in enumerate(self.export.activities):
            found = self.installed.activities.get((name, location, product))
            if found is None:
                self.report.note(
                    f"matrix export activity {position} names no installed dataset: "
                    f"{name} [{location}] {product}"
                )
                continue
            self._compare_unit(f"{name} [{location}]", found.unit, symbol)
            self.activity_keep.append(position)
            self.activity_columns.append(found.column)
            self.product_rows.append(found.row)
            self.reference.append(found.reference)

    def _map_flows(self) -> None:
        for position, (name, compartment, subcompartment, symbol) in enumerate(self.export.flows):
            category = "Resource" if compartment == "natural resource" else compartment
            found = self.installed.flows.get((name, (category, subcompartment)))
            if found is None:
                self.report.note(
                    f"matrix export flow {position} names no installed flow: "
                    f"{name} ({compartment}/{subcompartment})"
                )
                continue
            if found.row is None:
                self.report.note(
                    f"matrix export flow {position} names an installed flow no exchange uses: "
                    f"{name} ({compartment}/{subcompartment})"
                )
                continue
            self._compare_unit(f"{name} ({compartment}/{subcompartment})", found.unit, symbol)
            self.flow_positions[position] = len(self.flow_keep)
            self.code_export[found.code] = position
            self.flow_keep.append(position)
            self.flow_rows.append(found.row)

    def _mirror(self) -> None:
        """Name every installed dataset and used flow the matrix export holds no row for, the
        mirror of the export entries that name no installed counterpart."""
        exported = Counter(
            (name, location, product) for name, location, product, _symbol in self.export.activities
        )
        for triple, count in (Counter(self.installed.catalog) - exported).items():
            for _ in range(count):
                self.report.note(
                    f"installed dataset names no matrix export activity: "
                    f"{triple[0]} [{triple[1]}] {triple[2]}"
                )
        exported_flows: Counter[tuple[str, tuple[str, ...]]] = Counter()
        for name, compartment, subcompartment, _symbol in self.export.flows:
            category = "Resource" if compartment == "natural resource" else compartment
            exported_flows[(name, (category, subcompartment))] += 1
        for key, count in (Counter(self.installed.used_flows) - exported_flows).items():
            for _ in range(count):
                self.report.note(
                    f"installed flow names no matrix export flow: {key[0]} ({'/'.join(key[1])})"
                )

    def _map_lcia(self) -> None:
        for position, (method, category, indicator, _symbol) in enumerate(self.export.lcia):
            key = (self.name, method, f"{category} > {indicator}")
            found = self.installed.methods.get(key)
            if found is None:
                self.report.note(
                    f"matrix export category {position} names no installed method: "
                    f"{method} > {category} > {indicator}"
                )
                continue
            self.lcia_positions[(method, category, indicator)] = len(self.lcia_keep)
            self.lcia_keep.append(position)
            self.factors.append(found)
            self.methods.append(self.installed.method_of[key])

    def _fold(self) -> None:
        """Restrict the matrices to the export's activities and fold every column ecoinvent
        folds: it is scaled by the activity's reference amount over its diagonal."""
        A = _subset(self.installed.A, self.product_rows, self.activity_columns).tocsr()
        B = _subset(self.installed.B, self.flow_rows, self.activity_columns).tocsr()
        amounts = np.array(self.reference)
        self.A, self.B, folded = _fold_self_consumption(A, B, amounts)
        self.amounts = amounts
        self.report.counts["self_consumption_folded"] = folded

    def _characterization(self) -> csr_matrix:
        matrix = lil_matrix((len(self.lcia_keep), len(self.flow_keep)))
        for row, factors in enumerate(self.factors):
            for code, value in factors.items():
                position = self.code_export.get(code)
                if position is not None:
                    matrix[row, self.flow_positions[position]] += value
        return csr_matrix(matrix)

    def _compare_matrices(self) -> None:
        activity_labels = [
            f"{name} [{location}]"
            for name, location, _product, _symbol in (
                self.export.activities[position] for position in self.activity_keep
            )
        ]
        flow_labels = [
            _label((name, compartment, subcompartment))
            for name, compartment, subcompartment, _symbol in (
                self.export.flows[position] for position in self.flow_keep
            )
        ]
        lcia_labels = [
            _label(triple)
            for triple in (self.export.lcia[position][:3] for position in self.lcia_keep)
        ]
        _compare_matrix(
            self.report,
            "A",
            _subset(self.export.A, self.activity_keep, self.activity_keep),
            self.A,
            activity_labels,
            activity_labels,
        )
        _compare_matrix(
            self.report,
            "B",
            _subset(self.export.B, self.flow_keep, self.activity_keep),
            self.B,
            flow_labels,
            activity_labels,
        )
        _compare_matrix(
            self.report,
            "C",
            _subset(self.export.C, self.lcia_keep, self.flow_keep),
            self._characterization(),
            lcia_labels,
            flow_labels,
        )

    def _scores(self) -> np.ndarray:
        """Every kept dataset's score under every kept category, for its reference-product
        amount: the engine's cradle-to-gate intensity of the dataset times the amount it makes.
        The intensities do not change under the column scaling `_fold` applies."""
        intensities = self.installed.calculation.intensities(self.methods)
        rows = np.asarray(intensities.data).reshape(len(self.methods), -1)
        return self.amounts[:, None] * rows[:, self.activity_columns].T

    def _reference(
        self,
        triple: tuple[str, str, str],
        column: int,
        positions: list[int],
        naturals: list[tuple[str, str, str]],
    ) -> tuple[np.ndarray, float, str]:
        """The scores this category is compared against, the tolerance, and the kind its largest
        difference is recorded under: the cumulative workbook at the command's tolerance, or, for
        a category the profile lists as workbook-disagreeing, the matrix export's own scores at
        the matrix reference tolerance."""
        reference = self.disagreeing.get(_label(triple))
        if reference is None:
            return (
                np.array([self.export.cumulative[key][column] for key in naturals]),
                self.report.tolerance,
                "scores",
            )
        matrix, tolerance = reference
        return (
            matrix[[self.activity_keep[position] for position in positions]],
            tolerance,
            _AGAINST_MATRIX_EXPORT,
        )

    def _compare_scores(self) -> None:
        if not self.activity_keep or not self.lcia_keep:
            self.report.counts["scores"] = 0
            return
        positions: list[int] = []
        for position, native in enumerate(self.activity_keep):
            key = self._natural(native)
            if key in self.export.cumulative:
                positions.append(position)
            else:
                self.report.note(f"the cumulative LCIA has no row for {key[0]} [{key[1]}] {key[2]}")
        naturals = [self._natural(self.activity_keep[position]) for position in positions]
        if not positions:
            self.report.counts["scores"] = 0
            return
        ours = self._scores()[positions]
        seen: set[str] = set()
        compared = 0
        for column, triple in enumerate(self.export.cumulative_triples):
            reference = self.lcia_positions.get(triple)
            if reference is None:
                continue
            theirs, tolerance, kind = self._reference(triple, column, positions, naturals)
            label = _label(triple)
            if label in self.disagreeing:
                workbook = np.array([self.export.cumulative[key][column] for key in naturals])
                _, _, workbook_relative = _differences(theirs[:, None], workbook, 0)
                seen.add(label)
                if workbook_relative.size:
                    self.report.difference("workbook_disagrees", float(workbook_relative.max()))
                    self.report.counts["workbook_disagreeing_scores"] += int(
                        (workbook_relative > self.report.tolerance).sum()
                    )
                    if float(workbook_relative.max()) <= self.report.tolerance:
                        self.report.note(
                            f"the profile lists {label} as workbook-disagreeing, but its "
                            "workbook scores agree"
                        )
            mine, _, relative = _differences(ours, theirs, reference)
            self.report.scores(
                kind, tolerance, relative, partial(_score_label, triple, naturals, mine, theirs)
            )
            compared += len(theirs)
        for label in sorted(set(self.disagreeing) - seen):
            self.report.note(
                f"the profile lists {label} as workbook-disagreeing, but no compared category "
                "names it"
            )
        self.report.counts["scores"] = compared

    def _unreferenced(self) -> None:
        matrix = {_label(triple[:3]) for triple in self.export.lcia}
        scores = {_label(triple) for triple in self.export.cumulative_triples}
        referenced = matrix & scores
        self.report.unreferenced = sorted(
            f"{key[1]} > {key[2]}"
            for key in self.installed.methods
            if f"{key[1]} > {key[2]}" not in referenced
        )


def _compare_matrix(
    report: _Report,
    kind: str,
    expected: csr_matrix,
    actual: csr_matrix,
    row_labels: list[str],
    column_labels: list[str],
) -> None:
    """Compare two sparse matrices entry for entry, naming every position that differs."""
    theirs = _entries(expected)
    mine = _entries(actual)
    for position in theirs.keys() | mine.keys():
        e = theirs.get(position, 0.0)
        a = mine.get(position, 0.0)
        scale = max(abs(e), abs(a))
        relative = abs(e - a) / scale if scale else 0.0
        report.entry(
            kind,
            relative,
            f"{kind}[{row_labels[position[0]]}, {column_labels[position[1]]}]: "
            f"ecoinvent says {e!r}, the bundle {a!r}",
        )


def _reference_tolerance(
    workbook_disagrees: Sequence[str], matrix_reference_tolerance: float | None, tolerance: float
) -> float:
    """The tolerance a workbook-disagreeing category is compared with against the matrix export:
    required when the list is non-empty, the command's tolerance when it is not."""
    if workbook_disagrees and matrix_reference_tolerance is None:
        raise Invalid(
            "workbook_disagrees names categories, so matrix_reference_tolerance is required"
        )
    return matrix_reference_tolerance if matrix_reference_tolerance is not None else tolerance


def validate(
    release: Release,
    bundle: Path,
    compiled: Path,
    tolerance: float,
    workbook_disagrees: Sequence[str] = (),
    matrix_reference_tolerance: float | None = None,
) -> Validation:
    """Compile a built bundle for the engine, save it to `compiled`, load it memory-mapped, and
    compare what was loaded with the release's own matrix export and cumulative LCIA, every
    score strictly. A category the profile lists as workbook-disagreeing is compared against the
    matrix export's own scores, its workbook difference counted rather than failed, and a listed
    label no category of the release names is invalid. The seconds of each step and the bytes
    the saved background takes are reported."""
    reference_tolerance = _reference_tolerance(
        workbook_disagrees, matrix_reference_tolerance, tolerance
    )
    name = f"ecoinvent-{release.version}-{release.system_model}"
    seconds: dict[str, float] = {}
    started = time.perf_counter()

    def lap(step: str) -> None:
        nonlocal started
        now = time.perf_counter()
        seconds[step] = now - started
        started = now

    imported = read_background(bundle, name, foreground=frozenset())
    lap("read")
    database = Database(
        name=name,
        elementary_flows=imported.biosphere,
        scheme="olca",
        version=release.version,
        system_model=release.system_model,
    )
    background = compile_background(imported, database)
    lap("compile")
    background.save(compiled)
    lap("save")
    loaded = Background.load(compiled)
    lap("load")
    calculation = Calculation(loaded)
    lap("factorise")
    installed = _installed(imported, loaded, calculation)
    calculation.intensities(list(installed.method_of.values()))
    lap("intensities")
    export = _read_export(release)
    disagreeing = {
        label: (scores, reference_tolerance)
        for label, scores in _matrix_export_scores(export, workbook_disagrees).items()
    }
    lap("read_export")
    report = _Report(tolerance)
    _Comparison(name, installed, export, report, disagreeing).run()
    lap("compare")
    return Validation(
        counts=report.counts,
        largest_rel_diff=report.largest,
        mismatches=report.mismatches,
        unreferenced=report.unreferenced,
        seconds=seconds,
        saved_bytes=sum(path.stat().st_size for path in compiled.iterdir()),
    )
