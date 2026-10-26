"""Read a release's LCIA implementation workbook into base methods."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from python_calamine import CalamineWorkbook

from ecosemantic.databases.ecoinvent.masterdata import MasterData
from ecosemantic.errors import Invalid
from ecosemantic.package.base_writer import BaseMethod


@dataclass(frozen=True)
class Sheet:
    """A workbook sheet and the header row a reader requires of it."""

    sheet: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class LciaLayout:
    """The factor and unit sheets of a release's LCIA implementation workbook."""

    factors: Sheet
    units: Sheet


def _rows(workbook: CalamineWorkbook, sheet: Sheet) -> list[list[str]]:
    """A sheet's rows as text, once its header row equals the layout's columns."""
    raw = workbook.get_sheet_by_name(sheet.sheet).to_python()
    rows = [[str(cell) for cell in row] for row in raw]
    found = tuple(rows[0][: len(sheet.columns)])
    if found != sheet.columns:
        raise Invalid(f"{sheet.sheet} has columns {found}, not {sheet.columns}")
    return rows


def _units(rows: list[list[str]]) -> dict[tuple[str, str, str], str]:
    """The unit of each (method, category, indicator) the Indicators sheet names."""
    units: dict[tuple[str, str, str], str] = {}
    for row in rows[1:]:
        units.setdefault((row[0], row[1], row[2]), row[3])
    return units


def _unit(units: dict[tuple[str, str, str], str], triple: tuple[str, str, str]) -> str:
    """The unit a triple takes from the Indicators sheet; a triple without one is invalid."""
    if triple not in units:
        raise Invalid(f"{triple} names no Indicators row")
    return units[triple]


def read_methods(
    workbook: Path, layout: LciaLayout, master: MasterData, database: str
) -> tuple[tuple[BaseMethod, ...], list[tuple[str, str, str]]]:
    """Read a release's LCIA factors and units as base methods, with every factor row that
    names no elementary exchange of the release listed rather than dropped."""
    book = CalamineWorkbook.from_path(str(workbook))
    units = _units(_rows(book, layout.units))
    codes = {
        (exchange.name, exchange.compartment, exchange.subcompartment): code
        for code, exchange in master.elementary.items()
    }
    factors: dict[tuple[str, str, str], list[tuple[str, float]]] = {}
    unmatched: list[tuple[str, str, str]] = []
    for row in _rows(book, layout.factors)[1:]:
        triple = (row[0], row[1], row[2])
        flow = (row[3], row[4], row[5])
        code = codes.get(flow)
        if code is None:
            unmatched.append(flow)
            continue
        factors.setdefault(triple, []).append((code, float(row[6])))
    return (
        tuple(
            BaseMethod(key=(database, *triple), unit=_unit(units, triple), factors=tuple(rows))
            for triple, rows in factors.items()
        ),
        unmatched,
    )
