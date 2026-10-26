"""A synthetic BAFU results workbook, written as Nexus serves it: one workbook under a directory in
a zip, an information sheet before the scored sheet, its labels and scores invented.

The test package's scores, in the terms a workbook holds them, worked out by hand:

- `elec` is declared in kWh and its row is per MJ, so its 1 kg of CO2 per kWh is `1 / 3.6` per MJ.
- `steel`: 0.5 kg of CO2 and 0.01 kg of methane at 28 kg CO2-eq per kg make 0.78, and 7.2 MJ of
  `elec` at `1 / 3.6` add 2, so 2.78 kg CO2-eq per kg.
- `refinery`'s fuel oil carries 0.75 of the refinery's 2 kg of CO2 and of its 4 MJ of `elec`, so
  1.5 kg of CO2 and 0.8333 kWh of `elec` make 2.3333 kg CO2-eq per kg.
- `widget`: 0.1 kg of CO2, 0.5 kg of `steel` at 2.78, 1 kg of fuel oil at 2.3333 and 0.1 kg of
  scrap at the treatment's 0.3 add up to 3.8533 kg CO2-eq per unit, and 0.02 m3 of water make
  0.02.
- `treatment` produces -1 kg of scrap for each kg it treats, so the core's -0.3 per unit is
  compared as 0.3.

`Total [CO2-eq]` sums the method's two categories."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import xlsxwriter

from ecosemantic.databases.bafu.profile import Column, Pack, Profile, Total

DIRECTORY = "Synthetic results"
BOOK = "synthetic results.xlsx"
INFO_SHEET = "Info"
SCORED_SHEET = "Synthetic 2026 v1"
GROUP = "Synthetic 2021"
FIXED = ("Product", "Category", "Sub-category", "Unit")
HEADER_ROW = 1
FIRST_ROW = 2

METHOD = "fixture method"
CLIMATE = "GWP [kg CO2-eq]"
WATER = "Water [m3]"
TOTAL = "Total [CO2-eq]"
ELEC_LABEL = "elec production - GLO"
STEEL_LABEL = "steel production - GLO"
WIDGET_LABEL = "widget production - GLO"
TREATMENT_LABEL = "treatment production - GLO"
ELEC_CLIMATE = 1 / 3.6
STEEL_CLIMATE = 0.5 + 0.01 * 28.0 + 7.2 / 3.6
FUEL_OIL_CLIMATE = 1.5 + 3.0 / 3.6
TREATMENT_CLIMATE = 0.3
WIDGET_CLIMATE = 0.1 + 0.5 * STEEL_CLIMATE + FUEL_OIL_CLIMATE + 0.1 * TREATMENT_CLIMATE
WIDGET_WATER = 0.02

Row = tuple[str, str, dict[str, float]]


def workbook_rows() -> list[Row]:
    """The workbook's rows: each process its label, the unit its column D names, and its scores in
    the workbook's terms."""
    return [
        (ELEC_LABEL, "MJ", {CLIMATE: ELEC_CLIMATE, WATER: 0.0, TOTAL: ELEC_CLIMATE}),
        (STEEL_LABEL, "kg", {CLIMATE: STEEL_CLIMATE, WATER: 0.0, TOTAL: STEEL_CLIMATE}),
        (
            WIDGET_LABEL,
            "unit",
            {
                CLIMATE: WIDGET_CLIMATE,
                WATER: WIDGET_WATER,
                TOTAL: WIDGET_CLIMATE + WIDGET_WATER,
            },
        ),
        (TREATMENT_LABEL, "kg", {CLIMATE: TREATMENT_CLIMATE, WATER: 0.0, TOTAL: TREATMENT_CLIMATE}),
    ]


def fixture_profile(
    *, tolerance: float = 1e-6, differences: str = "differences-fixture.csv"
) -> Profile:
    """A release whose columns map the test package's two categories and whose total sums them."""
    digest = hashlib.sha256(b"a synthetic pack").hexdigest()
    return Profile(
        version="fixture-v1",
        server="https://example.invalid",
        citation="a synthetic release",
        inventory=Pack(pack="fixture", version=1, format="openLCA zolca", sha256=digest),
        results=Pack(pack="fixture results", version=1, format="excel", sha256=digest),
        columns=(
            Column(header=CLIMATE, method=METHOD, category="climate change"),
            Column(header=WATER, method=METHOD, category="water use"),
        ),
        total=Total(header=TOTAL, method=METHOD),
        unlinked="unlinked-fixture.csv",
        differences=differences,
        tolerance=tolerance,
    )


def write_workbook(path: Path, rows: Sequence[tuple[str, str, Mapping[str, float]]]) -> Path:
    """Write an xlsx of a header row and one row per (label, unit, scores) under a directory in a
    zip, and answer the zip's path; a header a row does not carry is written as an empty cell."""
    headers = tuple(dict.fromkeys(header for _, _, scores in rows for header in scores))
    with tempfile.TemporaryDirectory() as directory:
        book = Path(directory) / BOOK
        _write(book, headers, rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{DIRECTORY}/", b"")
            archive.write(book, f"{DIRECTORY}/{BOOK}")
    return path


def _write(
    book: Path,
    headers: tuple[str, ...],
    rows: Sequence[tuple[str, str, Mapping[str, float]]],
) -> None:
    """Write the workbook: an information sheet whose second row does not begin with `Product`, and
    the scored sheet whose second row does."""
    workbook = xlsxwriter.Workbook(str(book))
    info = workbook.add_worksheet(INFO_SHEET)
    info.write_string(HEADER_ROW, 1, "Synthetic")
    sheet = workbook.add_worksheet(SCORED_SHEET)
    sheet.write_string(HEADER_ROW - 1, len(FIXED), GROUP)
    for column, header in enumerate(FIXED):
        sheet.write_string(HEADER_ROW, column, header)
    for offset, header in enumerate(headers):
        sheet.write_string(HEADER_ROW, len(FIXED) + offset, header)
    for index, (label, unit, scores) in enumerate(rows):
        row = FIRST_ROW + index
        sheet.write_string(row, 0, label)
        sheet.write_string(row, 3, unit)
        for offset, header in enumerate(headers):
            if header in scores:
                sheet.write_number(row, len(FIXED) + offset, scores[header])
    workbook.close()
