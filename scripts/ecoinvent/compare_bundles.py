"""Compare two openLCA base bundles record by record, without installing either.

Each bundle is read with the core's `read_background` into float64 rows and compared by natural
keys — datasets by name, reference product and location, elementary flows by id, categories by
method and `category > indicator`. Each dataset's unit and reference amount, its exchanges with
their uncertainty, its flows' categories and types, every factor, and one unit of every dataset
under every category are compared. Every difference is printed with its count, its largest
relative difference and up to three examples, and the exit code is 1 when a difference is found.

usage:
  uv run python scripts/compare_bundles.py LEFT.zip RIGHT.zip [--work DIR]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import scipy.sparse as sp
from _compare import _UNCERTAINTY, _Comparison, _Dump, _load, _store

from ecosemantic.package.background import Import, read_background


def _categories(entity: Mapping[str, object]) -> list[object]:
    """A flow's category path, empty when it carries none."""
    return list(entity.get("categories") or [])


def _rows(dataset: Mapping[str, object]) -> list[dict[str, object]]:
    """A dataset's exchange rows."""
    return cast(list[dict[str, object]], dataset["exchanges"])


def _input(row: Mapping[str, object]) -> tuple[str, str]:
    """An exchange row's input database and code."""
    return cast(tuple[str, str], row["input"])


def _bundle_rows(imported: Import, side: str, seconds: float) -> _Dump:
    """One bundle's datasets, flows, exchanges, methods and float64 matrices."""
    datasets = sorted(imported.datasets.items(), key=lambda item: item[0][1])
    flows = sorted(imported.flows.items(), key=lambda item: item[0][1])
    product = {key[1]: position for position, (key, _) in enumerate(datasets)}
    biosphere = {key[1]: position for position, (key, _) in enumerate(flows)}
    A = sp.lil_matrix((len(datasets), len(datasets)))
    B = sp.lil_matrix((len(flows), len(datasets)))
    acts: dict[str, dict[str, object]] = {}
    bio: dict[str, dict[str, object]] = {}
    references: dict[str, float] = {}
    exchanges: list[list[object]] = []
    for (_, code), dataset in datasets:
        column = product[code]
        acts[code] = {
            "code": code,
            "name": dataset["name"],
            "reference product": dataset["reference product"],
            "location": dataset["location"],
            "unit": dataset["unit"],
            "type": dataset["type"],
            "categories": _categories(dataset),
        }
        for row in _rows(dataset):
            kind = str(row["type"])
            amount = float(row["amount"])
            input_database, input_code = _input(row)
            if kind == "production":
                references[code] = amount
                A[column, column] += amount
            elif kind == "technosphere":
                A[product[input_code], column] -= amount
            elif kind == "biosphere":
                B[biosphere[input_code], column] += amount
            exchanges.append(
                [
                    code,
                    input_database,
                    input_code,
                    kind,
                    amount,
                    row["unit"],
                    [row.get(field) for field in _UNCERTAINTY],
                ]
            )
    for (_, code), flow in flows:
        bio[code] = {
            "code": code,
            "name": flow["name"],
            "reference product": None,
            "location": None,
            "unit": flow["unit"],
            "type": flow["type"],
            "categories": _categories(flow),
        }
    methods: list[dict[str, object]] = [
        {
            "key": list(method.key),
            "unit": method.unit,
            "factors": [[code, float(value)] for (_, code), value in method.factors],
        }
        for method in imported.methods
    ]
    return _Dump(
        meta={
            "side": side,
            "database": imported.database,
            "biosphere": imported.biosphere,
            "datasets": len(acts),
            "flows": len(bio),
            "exchanges": len(exchanges),
            "methods": len(methods),
            "seconds": seconds,
        },
        acts=acts,
        bio=bio,
        references=references,
        exchanges=exchanges,
        methods=methods,
        dicts={"product": product, "activity": dict(product), "biosphere": biosphere},
        A=A.tocsc(),
        B=B.tocsc(),
    )


def _read(path: Path, side: str, work: Path | None) -> _Dump:
    """Read one bundle, printing its counts; a work directory stores the dump and its reload."""
    start = time.monotonic()
    imported = read_background(path, path.stem, foreground=frozenset())
    dump = _bundle_rows(imported, side, round(time.monotonic() - start, 1))
    print(
        f"{side} {path.name} dump: {len(dump.acts)} datasets, {len(dump.bio)} flows, "
        f"{len(dump.exchanges)} exchanges, {len(dump.methods)} methods, "
        f"A {dump.A.shape} {dump.A.nnz}, B {dump.B.shape} {dump.B.nnz}",
        flush=True,
    )
    if work is None:
        return dump
    directory = work / side
    _store(directory, dump)
    return _load(directory)


def compare(
    left: Path, right: Path, work: Path | None = None
) -> tuple[_Comparison, dict[str, float]]:
    """Read both bundles, compare them and return the comparison with each side's seconds."""
    dumps: dict[str, _Dump] = {}
    times: dict[str, float] = {}
    for side, path in (("left", left), ("right", right)):
        start = time.monotonic()
        dumps[side] = _read(path, side, work)
        times[side] = time.monotonic() - start
    start = time.monotonic()
    comparison = _Comparison(dumps["left"], dumps["right"], ("left", "right"), examples=3)
    comparison.run()
    times["compare"] = time.monotonic() - start
    print(f"compare {times['compare']:.1f} s", flush=True)
    return comparison, times


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path, help="the first bundle")
    parser.add_argument("right", type=Path, help="the second bundle")
    parser.add_argument("--work", type=Path, help="write each side's dump here and compare it")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Compare the two bundles and answer 1 when a difference is found."""
    arguments = _arguments(argv)
    for path in (arguments.left, arguments.right):
        if not path.is_file():
            raise SystemExit(f"no bundle at {path}")
    comparison, times = compare(arguments.left, arguments.right, arguments.work)
    comparison.print(times)
    return 1 if comparison.report.counts else 0


if __name__ == "__main__":
    sys.exit(main())
