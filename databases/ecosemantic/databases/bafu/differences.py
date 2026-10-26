"""The (process, column) pairs a BAFU validation knows differ beyond its tolerance, keyed by the
process's id and the workbook column's header so neither BAFU's names nor its values are written
into the package."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.errors import Invalid

COLUMNS = ("process_id", "column")


@dataclass(frozen=True)
class Difference:
    """One pair whose two scores differ beyond the tolerance."""

    process_id: str
    column: str


def _order(row: Difference) -> tuple[str, str]:
    """A row's sort position: its process, then its column."""
    return (row.process_id, row.column)


def read_differences(path: Path) -> tuple[Difference, ...]:
    """The pairs a list holds, in process and column order; a pair the list holds twice is
    `Invalid`."""
    with path.open(newline="") as read:
        rows = [
            Difference(process_id=record["process_id"], column=record["column"])
            for record in csv.DictReader(read)
        ]
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if _order(row) in seen:
            raise Invalid(f"{path} holds {row.process_id} under {row.column!r} twice")
        seen.add(_order(row))
    return tuple(sorted(rows, key=_order))


def write_differences(path: Path, rows: Iterable[Difference]) -> None:
    """Write the pairs as CSV, in process and column order."""
    with path.open("w", newline="") as written:
        writer = csv.writer(written, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in sorted(rows, key=_order):
            writer.writerow((row.process_id, row.column))
