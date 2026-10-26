"""BAFU's results workbook: the headers and scores of the sheet that scores every process, and the
process each row names once a label encoded twice is decoded."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from ecosemantic.errors import Invalid

NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
WORKSHEETS = "xl/worksheets/"
SHARED = "xl/sharedStrings.xml"
PRODUCT = "Product"
LABEL_COLUMN = 1
UNIT_COLUMN = 4
FIRST_VALUE_COLUMN = 5


@dataclass(frozen=True)
class WorkbookRow:
    """One scored row: the sheet row it sits on, the label it names its process by, the unit its
    scores are per, and each value header's score, a header whose cell holds no value absent."""

    row: int
    label: str
    unit: str
    values: dict[str, float]


@dataclass(frozen=True)
class Workbook:
    """The workbook's value headers in column order, and its scored rows in the sheet's order."""

    headers: tuple[str, ...]
    rows: tuple[WorkbookRow, ...]


def _column(reference: str) -> int:
    """A cell reference's column, numbered from one at `A`."""
    number = 0
    for letter in reference.rstrip("0123456789"):
        number = number * 26 + (ord(letter) - ord("A") + 1)
    return number


def _shared(book: zipfile.ZipFile) -> tuple[str, ...]:
    """A workbook's shared strings by index, in the order its table holds them."""
    if SHARED not in book.namelist():
        return ()
    root = ElementTree.fromstring(book.read(SHARED))
    return tuple(
        "".join(run.text or "" for run in entry.iter(f"{NAMESPACE}t"))
        for entry in root.findall(f"{NAMESPACE}si")
    )


def _text(cell: Element, shared: Sequence[str]) -> str | None:
    """A cell's text: a shared string by its index, an inline string's runs joined, or a number as
    it is stored; nothing when the cell holds no value."""
    inline = cell.find(f"{NAMESPACE}is")
    if inline is not None:
        return "".join(run.text or "" for run in inline.iter(f"{NAMESPACE}t"))
    value = cell.find(f"{NAMESPACE}v")
    if value is None or value.text is None:
        return None
    if cell.get("t") == "s":
        return shared[int(value.text)]
    return value.text


def _rows(
    book: zipfile.ZipFile, sheet: str, shared: Sequence[str]
) -> Iterator[tuple[int, dict[int, str | None]]]:
    """One sheet's rows in the sheet's order, each as its number and the text of every cell it
    holds, by column."""
    for _, row in ElementTree.iterparse(io.BytesIO(book.read(sheet)), events=("end",)):
        if row.tag != f"{NAMESPACE}row":
            continue
        yield (
            int(row.get("r", "0")),
            {
                _column(cell.get("r", "")): _text(cell, shared)
                for cell in row.findall(f"{NAMESPACE}c")
            },
        )
        row.clear()


def _scored(
    book: zipfile.ZipFile, shared: Sequence[str]
) -> tuple[dict[int, str | None], list[tuple[int, dict[int, str | None]]]]:
    """The header row and the data rows of the one sheet whose second row begins with `Product`;
    a workbook without such a sheet is `Invalid`."""
    sheets = sorted(
        name for name in book.namelist() if name.startswith(WORKSHEETS) and name.endswith(".xml")
    )
    for sheet in sheets:
        stream = _rows(book, sheet, shared)
        found = next(((number, cells) for number, cells in stream if number >= 2), None)
        if found is None or found[0] != 2 or found[1].get(LABEL_COLUMN) != PRODUCT:
            continue
        return found[1], list(stream)
    raise Invalid(f"no sheet of the workbook begins its second row with {PRODUCT}: {sheets}")


def _rows_read(
    header: dict[int, str | None], data: Sequence[tuple[int, dict[int, str | None]]]
) -> Workbook:
    """The workbook a header row and data rows make: every named value column in column order, and
    each data row's label, unit and scores by that column's header."""
    named = {
        column: text for column, text in header.items() if column >= FIRST_VALUE_COLUMN and text
    }
    return Workbook(
        headers=tuple(named[column] for column in sorted(named)),
        rows=tuple(
            WorkbookRow(
                row=number,
                label=cells.get(LABEL_COLUMN) or "",
                unit=cells.get(UNIT_COLUMN) or "",
                values={
                    named[column]: float(text)
                    for column, text in cells.items()
                    if column in named and text is not None
                },
            )
            for number, cells in data
        ),
    )


def read_workbook(results: Path) -> Workbook:
    """Read the results zip Nexus serves: its one workbook, and of that workbook the sheet that
    scores every process. A zip holding two workbooks or none is `Invalid`."""
    with zipfile.ZipFile(results) as outer:
        members = [name for name in outer.namelist() if name.endswith(".xlsx")]
        if len(members) != 1:
            raise Invalid(
                f"{results} holds {len(members)} .xlsx members, not one: "
                f"{', '.join(members) or 'none'}"
            )
        with zipfile.ZipFile(io.BytesIO(outer.read(members[0]))) as book:
            header, data = _scored(book, _shared(book))
    return _rows_read(header, data)


def _undone(text: str) -> str | None:
    """One layer of double encoding undone: the text read as the UTF-8 bytes it names, or nothing
    when the layer is not valid UTF-8 or leaves the text unchanged."""
    codec = "latin-1" if any("\x80" <= character <= "\x9f" for character in text) else "cp1252"
    try:
        again = text.encode(codec).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return None if again == text else again


def decode(label: str) -> str:
    """A label with each layer of double encoding undone, so a label already valid text is
    answered as it is."""
    text = label
    while (layer := _undone(text)) is not None:
        text = layer
    return text


def matched(workbook: Workbook, labels: Mapping[str, str]) -> dict[int, str]:
    """Each row's number to the one process its label names, as read or once decoded; a row naming
    no process, or two, is `Invalid`, its number and both forms of its label named."""
    answered: dict[int, str] = {}
    for row in workbook.rows:
        decoded = decode(row.label)
        found = {labels[form] for form in (row.label, decoded) if form in labels}
        if len(found) != 1:
            raise Invalid(
                f"workbook row {row.row} names {len(found)} processes, not one: "
                f"{row.label!r} as read and {decoded!r} decoded"
            )
        answered[row.row] = found.pop()
    return answered
