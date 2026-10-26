"""The Database Overview's ecoQuery URLs are read by native id, from the sheet the layout names."""

from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.lcia import Sheet
from ecosemantic.databases.ecoinvent.overview import read_urls
from ecosemantic.errors import Invalid
from tests.databases.spold_fixture import (
    AIR,
    ELEC,
    OVERVIEW_COLUMNS,
    STEEL,
    STEEL_ACTIVITY,
    TREAT,
    _write_workbook,
    build_release,
)

LAYOUT = Sheet("Cut-Off AO", ("Activity UUID & Product UUID", "ecoQuery URL"))


def test_urls_are_keyed_by_the_native_id_and_read_as_text(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    urls = read_urls(
        release.overview, Sheet("Cut-Off AO", ("Activity UUID & Product UUID", "ecoQuery URL"))
    )
    assert urls[STEEL].startswith("https://ecoquery.ecoinvent.org/3.10/cutoff/dataset/")
    assert set(urls) == {STEEL, ELEC, TREAT, AIR}


def test_a_sheet_without_the_named_columns_is_invalid(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    with pytest.raises(Invalid, match="ecoQuery"):
        read_urls(
            release.overview, Sheet("Cut-Off AO", ("Activity UUID & Product UUID", "ecoQuery link"))
        )


def test_rows_before_the_header_are_skipped_and_empty_keys_are_not_urls(tmp_path: Path) -> None:
    path = tmp_path / "overview.xlsx"
    _write_workbook(
        path,
        {
            "Cut-Off AO": [
                ["Database Overview"],
                [],
                list(OVERVIEW_COLUMNS),
                [STEEL, STEEL_ACTIVITY, "https://example.test/steel", "steel production", "NA"],
                ["", "", "", "", ""],
            ]
        },
    )
    assert read_urls(path, LAYOUT) == {STEEL: "https://example.test/steel"}
