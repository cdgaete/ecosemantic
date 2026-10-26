"""The results workbook: the headers and scores of its scored sheet, the label that names each
row's process once decoded, and the refusal of a row without one."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ecosemantic.databases.bafu.workbook import decode, matched, read_workbook
from ecosemantic.errors import Invalid
from tests.databases.bafu_fixture import write_workbook

WIDGET = "2f0c6b1e-9a44-4d7c-8e21-6c5b0f3a7d92"
ZURICH = "6d3a8c02-1b57-4e69-9f48-0a2c7e5b1d63"
OBB = "9e1f4a70-3c28-4b95-a6d1-5f8e2b07c493"
SCORES = {"GWP [kg CO2-eq]": 1.5, "Total [UBP]": 2.5}
INLINE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    '<row r="2"><c r="A2" t="inlineStr"><is><t>Product</t></is></c>'
    '<c r="D2" t="inlineStr"><is><t>Unit</t></is></c>'
    '<c r="E2" t="inlineStr"><is><t>GWP [kg CO2-eq]</t></is></c></row>'
    '<row r="3"><c r="A3" t="inlineStr"><is><r><t>widget plant</t></r>'
    "<r><t> - CH</t></r></is></c>"
    '<c r="D3" t="inlineStr"><is><t>kg</t></is></c><c r="E3"><v>1.5</v></c></row>'
    "</sheetData></worksheet>"
)


def test_decode_undoes_two_cp1252_layers() -> None:
    assert decode("ZÃƒÂ¼rich") == "Zürich"
    assert decode("ÃƒÂŸ") == "ß"


def test_decode_undoes_a_c1_layer() -> None:
    assert decode("ÃƒÂ–BB") == "ÖBB"


def test_ascii_is_left_as_it_is() -> None:
    assert decode("widget plant - CH") == "widget plant - CH"
    assert decode("Zürich plant - CH") == "Zürich plant - CH"


def test_rows_match_one_process_each(tmp_path: Path) -> None:
    path = write_workbook(
        tmp_path / "results.zip",
        [
            ("widget plant - CH", "kg", SCORES),
            ("ZÃƒÂ¼rich plant - CH", "kg", SCORES),
            ("ÃƒÂ–BB works - AT", "kg", SCORES),
        ],
    )
    workbook = read_workbook(path)
    assert [row.row for row in workbook.rows] == [3, 4, 5]
    assert matched(
        workbook,
        {
            "widget plant - CH": WIDGET,
            "Zürich plant - CH": ZURICH,
            "ÖBB works - AT": OBB,
        },
    ) == {3: WIDGET, 4: ZURICH, 5: OBB}


def test_a_row_matching_none_is_invalid(tmp_path: Path) -> None:
    path = write_workbook(
        tmp_path / "results.zip",
        [("widget plant - CH", "kg", SCORES), ("nothing here - CH", "kg", SCORES)],
    )
    with pytest.raises(Invalid) as caught:
        matched(read_workbook(path), {"widget plant - CH": WIDGET})
    message = str(caught.value)
    assert "row 4" in message
    assert repr("nothing here - CH") in message


def test_a_row_matching_several_is_invalid(tmp_path: Path) -> None:
    path = write_workbook(tmp_path / "results.zip", [("ÃƒÂ¼ plant - CH", "kg", SCORES)])
    with pytest.raises(Invalid) as caught:
        matched(
            read_workbook(path),
            {"ÃƒÂ¼ plant - CH": WIDGET, "ü plant - CH": ZURICH},
        )
    message = str(caught.value)
    assert "row 3" in message
    assert repr("ÃƒÂ¼ plant - CH") in message
    assert repr("ü plant - CH") in message


def test_the_workbook_reads_headers_and_values(tmp_path: Path) -> None:
    path = write_workbook(
        tmp_path / "results.zip",
        [
            ("widget plant - CH", "kg", SCORES),
            ("ZÃƒÂ¼rich plant - CH", "kWh", {"GWP [kg CO2-eq]": 0.25}),
        ],
    )
    workbook = read_workbook(path)
    assert workbook.headers == ("GWP [kg CO2-eq]", "Total [UBP]")
    first, second = workbook.rows
    assert (first.row, first.label, first.unit) == (3, "widget plant - CH", "kg")
    assert first.values == SCORES
    assert (second.row, second.label, second.unit) == (4, "ZÃƒÂ¼rich plant - CH", "kWh")
    assert second.values == {"GWP [kg CO2-eq]": 0.25}


def test_an_inline_string_is_read_without_a_shared_table(tmp_path: Path) -> None:
    book = tmp_path / "inline.xlsx"
    with zipfile.ZipFile(book, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", INLINE)
    path = tmp_path / "inline.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(book, f"Synthetic/{book.name}")
    workbook = read_workbook(path)
    assert workbook.headers == ("GWP [kg CO2-eq]",)
    assert [(row.row, row.label, row.unit, row.values) for row in workbook.rows] == [
        (3, "widget plant - CH", "kg", {"GWP [kg CO2-eq]": 1.5})
    ]


def test_a_zip_of_two_workbooks_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "two.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Synthetic/first.xlsx", b"")
        archive.writestr("Synthetic/second.xlsx", b"")
    with pytest.raises(Invalid) as caught:
        read_workbook(path)
    assert "Synthetic/first.xlsx" in str(caught.value)
    assert "Synthetic/second.xlsx" in str(caught.value)
