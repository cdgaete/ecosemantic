"""One side's dump and the comparison of two dumps by natural keys.

A dump holds one database's datasets, elementary flows, exchanges, methods, matrices and the row
maps of its matrices, as documents and sparse matrices that a later process loads. Two dumps are
compared by natural keys — datasets by name, reference product and location, elementary flows by
their code, methods by method and `category > indicator` — and one unit of every dataset is scored
under every shared category with a sparse LU solve. Every difference is recorded in a report with
its count, its largest relative difference and up to a limit of examples, numbers agreeing within
1e-12 relative.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

_TOLERANCE = 1e-12
_SCORE_TOLERANCE = 1e-9
_EXAMPLES = 20
_UNCERTAINTY = ("uncertainty type", "loc", "scale", "shape", "minimum", "maximum", "negative")
_CATEGORICAL = ("uncertainty type", "negative")


@dataclass(frozen=True)
class _Dump:
    """One side's dump: its counts, datasets, flows, references, exchanges, methods and matrices."""

    meta: dict[str, object]
    acts: dict[str, dict[str, object]]
    bio: dict[str, dict[str, object]]
    references: dict[str, float]
    exchanges: list[list[object]]
    methods: list[dict[str, object]]
    dicts: dict[str, dict[str, int]]
    A: sp.csc_matrix
    B: sp.csc_matrix


class _Report:
    """Every difference found, by kind: its count, its largest relative difference and examples,
    beside the counts of what was compared and of what was seen but is not a difference."""

    def __init__(self, examples: int = _EXAMPLES) -> None:
        self.counts: Counter[str] = Counter()
        self.largest: dict[str, float] = {}
        self.examples: defaultdict[str, list[str]] = defaultdict(list)
        self.observed: Counter[str] = Counter()
        self.limit = examples

    def difference(self, kind: str, message: str, relative: float = 1.0) -> None:
        """Record one difference of a kind, keeping the largest relative value and an example."""
        self.mismatches(kind, 1, relative)
        self.example(kind, message)

    def mismatches(self, kind: str, count: int, largest: float) -> None:
        """Record how many differences of a kind there are and the largest of them."""
        self.counts[kind] += count
        self.largest[kind] = max(self.largest.get(kind, 0.0), largest)

    def example(self, kind: str, message: str) -> None:
        """Keep one example of a kind, up to the limit."""
        if len(self.examples[kind]) < self.limit:
            self.examples[kind].append(message)

    def within(self, kind: str, relative: float) -> None:
        """Raise the largest relative difference recorded for a kind that agreed."""
        self.largest[kind] = max(self.largest.get(kind, 0.0), relative)

    def observe(self, kind: str, count: int = 1) -> None:
        """Record a count that is not a difference."""
        self.observed[kind] += count


def _act_key(dataset: Mapping[str, object]) -> object:
    """A dataset's natural key: its name, its reference product and its location."""
    return (dataset["name"], dataset["reference product"], dataset["location"])


def _bio_key(dataset: Mapping[str, object]) -> object:
    """An elementary flow's natural key: the code it carries."""
    return dataset["code"]


def _category_key(key: list[str]) -> tuple[str, str]:
    """A method's key as the method and its `category > indicator` path."""
    return (key[1], " > ".join(key[2:]))


def _category_normal(category: tuple[str, ...]) -> tuple[str, ...]:
    """A category with openLCA's `Resource` spelled as ecoinvent's `natural resource` and any
    trailing `unspecified` subcompartment left off."""
    parts = ["natural resource" if part == "Resource" else part for part in category]
    while parts and parts[-1].lower() == "unspecified":
        parts = parts[:-1]
    return tuple(parts)


def _category_difference(left: tuple[str, ...], right: tuple[str, ...]) -> str:
    """How two elementary-flow categories that differ are related: a resource spelling, a
    trailing `unspecified` subcompartment on one side, or a difference in the data."""
    if _category_normal(left) != _category_normal(right):
        return "flow category differs"
    if ("Resource" in left) != ("Resource" in right):
        return "flow category: natural resource spelled Resource"
    return "flow category: trailing unspecified subcompartment on one side"


def _same(left: object, right: object) -> bool:
    """Whether two uncertainty fields agree, two NaNs counting as equal."""
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
    return left == right


def _relative(left: object, right: object) -> float:
    """Two numbers' relative difference; zero when they agree and one when either is not a
    number."""
    if left == right:
        return 0.0
    if isinstance(left, bool) or isinstance(right, bool):
        return 1.0
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        return 1.0
    return abs(left - right) / max(abs(left), abs(right))


def _agrees(field: str, left: object, right: object) -> bool:
    """Whether two uncertainty fields agree: a type or a flag exactly, a number within the
    tolerance, two NaNs counting as equal."""
    if field in _CATEGORICAL:
        return _same(left, right)
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return _relative(left, right) <= _TOLERANCE
    return _same(left, right)


def _amount(record: list[object]) -> float:
    """An exchange record's amount, the field its group sorts by."""
    return float(record[0])


def _absent(record: list[object]) -> bool:
    """Whether an exchange states no uncertainty at all."""
    return all(value is None for value in record)


def _undefined(record: list[object], amount: float) -> bool:
    """Whether a record is the undefined distribution of a deterministic exchange."""
    return (
        record[0] in (0, None)
        and all(value is None for value in record[2:6])
        and (record[1] is None or record[1] == amount)
    )


def _group_label(key: tuple[object, object, object]) -> str:
    """One exchange group as text: its output dataset, its type and its input."""
    output, kind, target = key
    source = f"{output[0]!r} [{output[2]}]" if isinstance(output, tuple) else repr(output)
    return f"{source} {kind} {target!r}"


def _write(directory: Path, name: str, value: object) -> None:
    """Write one dump document as JSON."""
    (directory / name).write_text(json.dumps(value), encoding="utf-8")


def _store(directory: Path, dump: _Dump) -> None:
    """Write one dump's documents and matrices so another process can load it."""
    directory.mkdir(parents=True, exist_ok=True)
    sp.save_npz(directory / "A.npz", dump.A)
    sp.save_npz(directory / "B.npz", dump.B)
    _write(directory, "acts.json", dump.acts)
    _write(directory, "bio.json", dump.bio)
    _write(directory, "references.json", dump.references)
    _write(directory, "exchanges.json", dump.exchanges)
    _write(directory, "methods.json", dump.methods)
    _write(directory, "dicts.json", dump.dicts)
    _write(directory, "meta.json", dump.meta)


def _load(directory: Path) -> _Dump:
    """One side's dump as read from disk."""
    meta: dict[str, object] = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    acts: dict[str, dict[str, object]] = json.loads(
        (directory / "acts.json").read_text(encoding="utf-8")
    )
    bio: dict[str, dict[str, object]] = json.loads(
        (directory / "bio.json").read_text(encoding="utf-8")
    )
    references: dict[str, float] = json.loads(
        (directory / "references.json").read_text(encoding="utf-8")
    )
    exchanges: list[list[object]] = json.loads(
        (directory / "exchanges.json").read_text(encoding="utf-8")
    )
    methods: list[dict[str, object]] = json.loads(
        (directory / "methods.json").read_text(encoding="utf-8")
    )
    dicts: dict[str, dict[str, int]] = json.loads(
        (directory / "dicts.json").read_text(encoding="utf-8")
    )
    return _Dump(
        meta=meta,
        acts=acts,
        bio=bio,
        references=references,
        exchanges=exchanges,
        methods=methods,
        dicts=dicts,
        A=sp.load_npz(directory / "A.npz"),
        B=sp.load_npz(directory / "B.npz"),
    )


class _Comparison:
    """Two dumps compared by natural keys, recording every difference in a report."""

    def __init__(
        self, left: _Dump, right: _Dump, names: tuple[str, str], examples: int = _EXAMPLES
    ) -> None:
        self.left = left
        self.right = right
        self.left_name, self.right_name = names
        self.report = _Report(examples)
        self.examples = examples
        self.left_methods: dict[tuple[str, str], dict[str, object]] = {}
        self.right_methods: dict[tuple[str, str], dict[str, object]] = {}
        self.bio_map: dict[str, str] = {}

    def run(self) -> None:
        """Compare datasets, flows, exchanges, matrices, categories and scores."""
        self._datasets()
        self._flows()
        self._exchanges()
        self._matrices()
        self._categories()
        self._scores()

    def _index(
        self,
        nodes: Mapping[str, Mapping[str, object]],
        key_of: Callable[[Mapping[str, object]], object],
        label: str,
    ) -> dict[object, str]:
        """The row ids of a database keyed by natural key, a key naming two datasets left out."""
        groups: defaultdict[object, list[str]] = defaultdict(list)
        for row, dataset in nodes.items():
            groups[key_of(dataset)].append(row)
        unique: dict[object, str] = {}
        for key, rows in groups.items():
            if len(rows) > 1:
                self.report.difference(f"{label} key names more than one dataset", repr(key))
                continue
            unique[key] = rows[0]
        return unique

    def _datasets(self) -> None:
        """Compare datasets by name, reference product and location, and their units and types."""
        left = self._index(self.left.acts, _act_key, "dataset")
        right = self._index(self.right.acts, _act_key, "dataset")
        for key in left.keys() - right.keys():
            self.report.difference(f"dataset only in {self.left_name}", repr(key))
        for key in right.keys() - left.keys():
            self.report.difference(f"dataset only in {self.right_name}", repr(key))
        worst = 0.0
        missing = 0
        for key in left.keys() & right.keys():
            a, b = self.left.acts[left[key]], self.right.acts[right[key]]
            if a["unit"] != b["unit"]:
                self.report.difference(
                    "dataset unit differs", f"{key}: {a['unit']!r} vs {b['unit']!r}"
                )
            if a["type"] != b["type"]:
                self.report.difference(
                    "dataset type differs", f"{key}: {a['type']!r} vs {b['type']!r}"
                )
            left_amount = self.left.references.get(a["code"])
            right_amount = self.right.references.get(b["code"])
            if left_amount is None or right_amount is None:
                missing += 1
                continue
            worst = max(worst, _relative(left_amount, right_amount))
        self.report.within("dataset reference amount", worst)
        self.report.observe("datasets compared", len(left.keys() & right.keys()))
        self.report.observe("datasets without a production exchange", missing)

    def _flows(self) -> None:
        """Compare elementary flows by code: name, unit, type and category."""
        left = self._index(self.left.bio, _bio_key, "flow")
        right = self._index(self.right.bio, _bio_key, "flow")
        for key in left.keys() - right.keys():
            self.report.difference(f"flow only in {self.left_name}", repr(key))
        for key in right.keys() - left.keys():
            self.report.difference(f"flow only in {self.right_name}", repr(key))
        self.bio_map = {left[key]: right[key] for key in left.keys() & right.keys()}
        for row_left, row_right in self.bio_map.items():
            a, b = self.left.bio[row_left], self.right.bio[row_right]
            code = _bio_key(b)
            if a["name"] != b["name"]:
                self.report.difference(
                    "flow name differs", f"{code}: {a['name']!r} vs {b['name']!r}"
                )
            if a["unit"] != b["unit"]:
                self.report.difference(
                    "flow unit differs", f"{code}: {a['unit']!r} vs {b['unit']!r}"
                )
            if a["type"] != b["type"]:
                self.report.difference(
                    "flow type differs", f"{code}: {a['type']!r} vs {b['type']!r}"
                )
            left_category = tuple(a["categories"])
            right_category = tuple(b["categories"])
            if left_category != right_category:
                self.report.difference(
                    _category_difference(left_category, right_category),
                    f"{code}: {left_category} vs {right_category}",
                )
        self.report.observe("flows compared", len(self.bio_map))

    def _groups(
        self, dump: _Dump
    ) -> tuple[dict[tuple[object, object, object], list[list[object]]], int]:
        """A side's exchanges grouped by output dataset, exchange type and input dataset."""
        acts = {dataset["code"]: _act_key(dataset) for dataset in dump.acts.values()}
        biosphere = str(dump.meta["biosphere"])
        groups: defaultdict[tuple[object, object, object], list[list[object]]] = defaultdict(list)
        unresolved = 0
        for output, input_database, input_code, kind, amount, unit, uncertainty in dump.exchanges:
            target: object | None = (
                input_code if input_database == biosphere else acts.get(input_code)
            )
            if target is None:
                unresolved += 1
                target = f"{input_database}:{input_code}"
            groups[(acts[output], kind, target)].append([amount, unit, uncertainty])
        return groups, unresolved

    def _uncertainty(
        self,
        key: tuple[object, object, object],
        amount: float,
        left: list[object],
        right: list[object],
    ) -> None:
        """Record how two exchanges' uncertainty records differ: a type or a flag exactly, a
        number beyond the tolerance, and a number within it as an observation. An exchange whose
        only difference is the negative flag is named as that and not as a field."""
        if left == right:
            return
        label = _group_label(key)
        if (_absent(left) and _undefined(right, amount)) or (
            _absent(right) and _undefined(left, amount)
        ):
            self.report.difference(
                "uncertainty: one side states undefined, the other omits it",
                f"{label}: {left} vs {right}",
            )
            return
        beyond = [
            (field, a, b)
            for field, a, b in zip(_UNCERTAINTY, left, right, strict=True)
            if not _agrees(field, a, b)
        ]
        for field, a, b in zip(_UNCERTAINTY, left, right, strict=True):
            if _agrees(field, a, b) and not _same(a, b):
                self.report.observe(f"uncertainty {field} within tolerance")
        if not beyond:
            return
        if len(beyond) == 1 and beyond[0][0] == "negative":
            self.report.difference(
                "uncertainty: one side states the negative flag, the other omits it",
                f"{label}: {left} vs {right}",
            )
            if amount < 0:
                self.report.observe("negative flag omitted, amount below zero")
            return
        for field, a, b in beyond:
            self.report.difference(
                f"uncertainty {field} differs",
                f"{label}: {left} vs {right}",
                _relative(a, b),
            )

    def _exchanges(self) -> None:
        """Compare raw exchanges by their group, record by record, with their uncertainty."""
        left, left_unresolved = self._groups(self.left)
        right, right_unresolved = self._groups(self.right)
        self.report.observe(f"inputs resolving to no dataset, {self.left_name}", left_unresolved)
        self.report.observe(f"inputs resolving to no dataset, {self.right_name}", right_unresolved)
        worst = 0.0
        for key in left.keys() | right.keys():
            before, after = left.get(key, []), right.get(key, [])
            if len(before) != len(after):
                self.report.difference(
                    "exchange count differs", f"{_group_label(key)}: {len(before)} vs {len(after)}"
                )
                continue
            for a, b in zip(sorted(before, key=_amount), sorted(after, key=_amount), strict=True):
                relative = _relative(a[0], b[0])
                worst = max(worst, relative)
                if relative > _TOLERANCE:
                    self.report.difference(
                        "exchange amount differs",
                        f"{_group_label(key)}: {a[0]!r} vs {b[0]!r}",
                        relative,
                    )
                if a[1] != b[1]:
                    self.report.difference(
                        "exchange unit differs", f"{_group_label(key)}: {a[1]!r} vs {b[1]!r}"
                    )
                self._uncertainty(key, _amount(a), a[2], b[2])
        self.report.within("exchange amount", worst)
        self.report.observe("exchanges compared", len(self.left.exchanges))

    def _row_keys(self, dump: _Dump, name: str) -> list[object | None]:
        """The natural key of every matrix row: a dataset's for A, a flow's code for B."""
        mapping = dump.dicts["product"] if name == "A" else dump.dicts["biosphere"]
        keys: list[object | None] = [None] * (max(mapping.values()) + 1)
        for node, index in mapping.items():
            keys[index] = _act_key(dump.acts[node]) if name == "A" else dump.bio[node]["code"]
        return keys

    def _column_keys(self, dump: _Dump) -> list[object | None]:
        """The natural key of every matrix column, a dataset's."""
        mapping = dump.dicts["activity"]
        keys: list[object | None] = [None] * (max(mapping.values()) + 1)
        for node, index in mapping.items():
            keys[index] = _act_key(dump.acts[node])
        return keys

    def _entries(self, dump: _Dump, name: str) -> dict[tuple[object, object], float]:
        """A matrix's nonzero entries keyed by the natural keys of their row and column."""
        matrix = getattr(dump, name).tocoo()
        rows = self._row_keys(dump, name)
        columns = self._column_keys(dump)
        entries: dict[tuple[object, object], float] = {}
        for row, column, value in zip(matrix.row, matrix.col, matrix.data, strict=True):
            if rows[row] is None or columns[column] is None:
                continue
            entries[(rows[row], columns[column])] = float(value)
        return entries

    def _matrices(self) -> None:
        """Compare A and B entry by entry by the natural keys of their rows and columns."""
        for name in ("A", "B"):
            left = self._entries(self.left, name)
            right = self._entries(self.right, name)
            self.report.observe(f"{name} nnz, {self.left_name}", getattr(self.left, name).nnz)
            self.report.observe(f"{name} nnz, {self.right_name}", getattr(self.right, name).nnz)
            worst = 0.0
            pattern = 0
            keys = left.keys() | right.keys()
            for key in keys:
                a, b = left.get(key, 0.0), right.get(key, 0.0)
                relative = _relative(a, b)
                worst = max(worst, relative)
                if (a == 0.0) != (b == 0.0):
                    pattern += 1
                if relative > _TOLERANCE:
                    self.report.difference(
                        f"{name} entry differs", f"{key}: {a!r} vs {b!r}", relative
                    )
            self.report.within(name, worst)
            self.report.observe(f"{name} entries compared", len(keys))
            self.report.observe(f"{name} positions present on one side only", pattern)

    def _factor_values(self, factors: list[list[object]]) -> dict[str, float]:
        """One category's factors summed by the code of the flow they name."""
        values: defaultdict[str, float] = defaultdict(float)
        for code, value in factors:
            values[str(code)] += float(value)
        return values

    def _categories(self) -> None:
        """Compare impact categories by method and `category > indicator`, factor by factor."""
        self.left_methods = {_category_key(m["key"]): m for m in self.left.methods}
        self.right_methods = {_category_key(m["key"]): m for m in self.right.methods}
        for key in self.left_methods.keys() - self.right_methods.keys():
            self.report.difference(f"category only in {self.left_name}", repr(key))
        for key in self.right_methods.keys() - self.left_methods.keys():
            self.report.difference(f"category only in {self.right_name}", repr(key))
        worst = 0.0
        compared = 0
        for key in self.left_methods.keys() & self.right_methods.keys():
            a, b = self.left_methods[key], self.right_methods[key]
            left_factors = self._factor_values(a["factors"])
            right_factors = self._factor_values(b["factors"])
            if a["unit"] != b["unit"]:
                self.report.difference(
                    "category unit differs", f"{key}: {a['unit']!r} vs {b['unit']!r}"
                )
            if len(a["factors"]) != len(b["factors"]):
                self.report.difference(
                    "category factor count differs",
                    f"{key}: {len(a['factors'])} vs {len(b['factors'])}",
                )
            for code in left_factors.keys() | right_factors.keys():
                compared += 1
                relative = _relative(left_factors.get(code, 0.0), right_factors.get(code, 0.0))
                worst = max(worst, relative)
                if relative > _TOLERANCE:
                    self.report.difference(
                        "CF differs",
                        f"{key} flow {code}: "
                        f"{left_factors.get(code, 0.0)!r} vs {right_factors.get(code, 0.0)!r}",
                        relative,
                    )
        self.report.within("CF", worst)
        self.report.observe(
            "categories compared", len(self.left_methods.keys() & self.right_methods.keys())
        )
        self.report.observe("CFs compared", compared)

    def _score(
        self,
        dump: _Dump,
        methods: dict[tuple[str, str], dict[str, object]],
        categories: list[tuple[str, str]],
    ) -> tuple[np.ndarray, list[object | None]]:
        """Every dataset's score under every category, for one unit of its reference product.

        The sparse factorisation loses accuracy on ecoinvent's ill-conditioned technosphere
        matrix, so the solve is refined once against its own residual."""
        rows = {
            str(dataset["code"]): dump.dicts["biosphere"].get(row)
            for row, dataset in dump.bio.items()
        }
        C = sp.lil_matrix((len(categories), dump.B.shape[0]))
        for index, key in enumerate(categories):
            for code, value in self._factor_values(methods[key]["factors"]).items():
                row = rows.get(code)
                if row is not None:
                    C[index, row] += value
        M = np.asarray((C.tocsr() @ dump.B).toarray())
        system = dump.A.T.tocsc()
        solve = splu(system)
        solution = solve.solve(M.T)
        solution = solution + solve.solve(M.T - system @ solution)
        amounts = np.zeros(dump.A.shape[0])
        products: list[object | None] = [None] * dump.A.shape[0]
        for node, index in dump.dicts["product"].items():
            amount = dump.references.get(str(dump.acts[node]["code"]), 0.0)
            amounts[index] = amount
            products[index] = _act_key(dump.acts[node])
        return amounts[None, :] * solution.T, products

    def _scores(self) -> None:
        """Compare every dataset's score under every shared category."""
        categories = sorted(self.left_methods.keys() & self.right_methods.keys())
        if not categories:
            return
        left_scores, left_products = self._score(self.left, self.left_methods, categories)
        right_scores, right_products = self._score(self.right, self.right_methods, categories)
        left_index = {key: index for index, key in enumerate(left_products) if key is not None}
        right_index = {key: index for index, key in enumerate(right_products) if key is not None}
        common = [key for key in left_index if key in right_index]
        ours = left_scores[:, [left_index[key] for key in common]]
        theirs = right_scores[:, [right_index[key] for key in common]]
        scale = np.abs(ours).max(axis=1, keepdims=True)
        denominator = np.maximum(np.maximum(np.abs(ours), np.abs(theirs)), 1e-12 * scale)
        difference = np.abs(ours - theirs)
        relative = np.divide(
            difference, denominator, out=np.zeros_like(difference), where=denominator > 0
        )
        self.report.within("score", float(relative.max()))
        for threshold in (1e-9, 1e-6, 1e-3):
            self.report.observe(f"scores above {threshold:g}", int((relative > threshold).sum()))
        self.report.observe(
            "score zero-pattern differences", int(((ours == 0) != (theirs == 0)).sum())
        )
        self.report.observe("scores compared", relative.size)
        count = int((relative > _SCORE_TOLERANCE).sum())
        if not count:
            return
        self.report.mismatches("score differs", count, float(relative.max()))
        flat = relative.ravel()
        k = min(self.examples, flat.size - 1)
        worst = np.argpartition(-flat, k)[: self.examples]
        for index in worst[np.argsort(-flat[worst])]:
            row, column = np.unravel_index(index, relative.shape)
            if relative[row, column] <= _SCORE_TOLERANCE:
                break
            self.report.example(
                "score differs",
                f"{categories[row]} {common[column]}: "
                f"{float(ours[row, column])!r} vs {float(theirs[row, column])!r}",
            )

    def print(self, times: Mapping[str, float]) -> None:
        """Print what was compared, what was seen and every difference with its examples."""
        for side in (self.left, self.right):
            meta = side.meta
            name = str(meta["side"])
            print(
                f"{name}: {meta['datasets']} datasets, {meta['flows']} flows, "
                f"{meta['exchanges']} exchanges, {meta['methods']} methods, "
                f"dumped in {meta['seconds']} s of {times[name]:.1f} s",
                flush=True,
            )
        print("\n=== observed ===", flush=True)
        for kind in sorted(self.report.observed):
            print(f"{kind}: {self.report.observed[kind]}", flush=True)
        print("\n=== largest relative difference ===", flush=True)
        for kind in sorted(self.report.largest):
            print(f"{kind}: {self.report.largest[kind]:.3e}", flush=True)
        print(f"\n=== differences ({len(self.report.counts)} kinds) ===", flush=True)
        for kind in sorted(self.report.counts):
            print(f"{kind}: {self.report.counts[kind]}", flush=True)
            for example in self.report.examples[kind]:
                print(f"    {example[:300]}", flush=True)
