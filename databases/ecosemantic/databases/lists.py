"""The two lists a source's profile holds its validation to: the inputs the core's import leaves
unlinked, and the exchanges the build leaves out or writes without a distribution."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from ecosemantic.errors import Invalid
from ecosemantic.package.background import Import

UNLINKED_COLUMNS = (
    "process_id",
    "process_name",
    "flow_id",
    "flow_name",
    "flow_category",
    "provider_id",
)
LEFT_OUT_COLUMNS = (
    "process_id",
    "process_name",
    "exchange_id",
    "flow_id",
    "flow_name",
    "what",
    "reason",
)

LeftOut = Literal["distribution", "exchange"]


@dataclass(frozen=True)
class UnlinkedRow:
    """One distinct input the import leaves unlinked: the process and flow of the exchange, the
    top category of the flow, and the provider the input names."""

    process_id: str
    process_name: str
    flow_id: str
    flow_name: str
    flow_category: str
    provider_id: str | None

    @property
    def key(self) -> tuple[str, str, str | None]:
        """What makes two rows the same input."""
        return (self.process_id, self.flow_id, self.provider_id)


@dataclass(frozen=True)
class LeftOutRow:
    """One exchange the build leaves out, or writes without its distribution; a process may carry
    the same flow in two exchanges, so the exchange's own id names it."""

    process_id: str
    process_name: str
    exchange_id: int
    flow_id: str
    flow_name: str
    what: LeftOut
    reason: str

    @property
    def key(self) -> tuple[str, int, LeftOut]:
        """What makes two rows the same exclusion."""
        return (self.process_id, self.exchange_id, self.what)


def _unlinked_order(row: UnlinkedRow) -> tuple[str, str, str]:
    """A row's sort position: its key, an unnamed provider first as the CSV writes it empty."""
    process_id, flow_id, provider_id = row.key
    return (process_id, flow_id, provider_id or "")


def read_unlinked(path: Path) -> tuple[UnlinkedRow, ...]:
    """The unlinked inputs a list holds, in key order."""
    with path.open(newline="", encoding="utf-8") as read:
        rows = (
            UnlinkedRow(
                process_id=record["process_id"],
                process_name=record["process_name"],
                flow_id=record["flow_id"],
                flow_name=record["flow_name"],
                flow_category=record["flow_category"],
                provider_id=record["provider_id"] or None,
            )
            for record in csv.DictReader(read)
        )
        return tuple(sorted(rows, key=_unlinked_order))


def write_unlinked(path: Path, rows: Iterable[UnlinkedRow]) -> None:
    """Write the unlinked inputs as CSV, in key order."""
    with path.open("w", newline="", encoding="utf-8") as written:
        writer = csv.writer(written, lineterminator="\n")
        writer.writerow(UNLINKED_COLUMNS)
        for row in sorted(rows, key=_unlinked_order):
            writer.writerow(
                (
                    row.process_id,
                    row.process_name,
                    row.flow_id,
                    row.flow_name,
                    row.flow_category,
                    row.provider_id or "",
                )
            )


def process_ids(imported: Import) -> set[str]:
    """The ids of the processes the import holds a dataset of: a dataset's code is its process's id,
    an underscore, and what names the dataset."""
    return {code.split("_", 1)[0] for _, code in imported.datasets}


def flow_categories(imported: Import) -> dict[str, str]:
    """The top category of every elementary flow the import holds, by flow id."""
    return {
        code: next(iter(cast(tuple[str, ...], dataset["categories"])), "")
        for (_, code), dataset in imported.flows.items()
    }


def distinct_unlinked(imported: Import, categories: Mapping[str, str]) -> tuple[UnlinkedRow, ...]:
    """The import's distinct unlinked inputs, one per process, flow and provider, each with the top
    category its flow's id names."""
    found: dict[tuple[str, str, str | None], UnlinkedRow] = {}
    for miss in imported.unlinked:
        found.setdefault(
            (miss.process_id, miss.flow_id, miss.provider_id),
            UnlinkedRow(
                process_id=miss.process_id,
                process_name=miss.process,
                flow_id=miss.flow_id,
                flow_name=miss.flow,
                flow_category=categories.get(miss.flow_id, ""),
                provider_id=miss.provider_id,
            ),
        )
    return tuple(sorted(found.values(), key=_unlinked_order))


def unlinked_mismatches(
    found: tuple[UnlinkedRow, ...], path: Path | None, processes: set[str]
) -> list[str]:
    """Every unlinked input one side holds and the other lacks, and every list row whose process
    the import lacks; a list not named is not compared."""
    if path is None:
        return []
    listed = read_unlinked(path)
    mine = {row.key for row in found}
    theirs = {row.key for row in listed}
    return (
        [
            f"{row.process_name} takes {row.flow_name} and the unlinked list lacks it"
            for row in found
            if row.key not in theirs
        ]
        + [
            f"the unlinked list holds a row of {row.process_name}, which the import lacks"
            for row in listed
            if row.process_id not in processes
        ]
        + [
            f"the unlinked list holds {row.process_name} taking {row.flow_name}, "
            "which the import leaves linked"
            for row in listed
            if row.process_id in processes and row.key not in mine
        ]
    )


def _left_out_row(path: Path, record: dict[str, str]) -> LeftOutRow:
    """One left-out row of a list, its kind checked against the kinds a list holds."""
    what = record["what"]
    if what not in get_args(LeftOut):
        raise Invalid(
            f"{path} holds {record['process_id']} for {record['flow_id']} of kind {what!r}; "
            f"a row's kind is one of {', '.join(get_args(LeftOut))}"
        )
    return LeftOutRow(
        process_id=record["process_id"],
        process_name=record["process_name"],
        exchange_id=int(record["exchange_id"]),
        flow_id=record["flow_id"],
        flow_name=record["flow_name"],
        what=cast(LeftOut, what),
        reason=record["reason"],
    )


def read_left_out(path: Path) -> tuple[LeftOutRow, ...]:
    """The left-out exchanges a list holds, in key order."""
    with path.open(newline="", encoding="utf-8") as read:
        rows = (_left_out_row(path, record) for record in csv.DictReader(read))
        return tuple(sorted(rows, key=lambda row: row.key))


def write_left_out(path: Path, rows: Iterable[LeftOutRow]) -> None:
    """Write the left-out exchanges as CSV, in key order."""
    with path.open("w", newline="", encoding="utf-8") as written:
        writer = csv.writer(written, lineterminator="\n")
        writer.writerow(LEFT_OUT_COLUMNS)
        for row in sorted(rows, key=lambda row: row.key):
            writer.writerow(
                (
                    row.process_id,
                    row.process_name,
                    row.exchange_id,
                    row.flow_id,
                    row.flow_name,
                    row.what,
                    row.reason,
                )
            )
