"""The BAFU profile pins the two packs Nexus serves and the 46 workbook columns, and the known
differences a validated run records."""

from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.databases.bafu.differences import Difference, read_differences, write_differences
from ecosemantic.databases.bafu.profile import RELEASES, Column, read_profile, recorded, versions
from ecosemantic.errors import Invalid, NotFound

PAIRS = (
    Difference(process_id="06f1a9d2-4c6a-3a0b-9f24-1d3cba8e5f70", column="Water use [m3 world eq]"),
    Difference(process_id="1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d", column="Energy resources [UBP]"),
    Difference(process_id="1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d", column="Mineral resources [UBP]"),
)


def test_the_shipped_profile_pins_the_2026_v1_packs_and_columns() -> None:
    profile = read_profile("2026-v1")
    assert versions() == ("2026-v1",)
    assert profile.version == "2026-v1"
    assert profile.server == "https://nexus.openlca.org"
    assert profile.citation == (
        "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026"
    )
    assert profile.inventory.pack == "c31fbb3c-ff98-4f50-8ceb-737ef690ce90"
    assert profile.inventory.version == 2
    assert profile.inventory.format == "openLCA zolca"
    assert profile.inventory.sha256 == (
        "e63b7e7ef5cde04bfe1176a783a55b5f72e2b73f42c36632b6150af39d348c4c"
    )
    assert profile.results.pack == "86aa5c2b-3334-4cc2-96f7-aaa6fd2494cb"
    assert profile.results.version == 2
    assert profile.results.format == "excel"
    assert profile.results.sha256 == (
        "a692f72705baac82fc59e85e00389302446ac2d5e921ab9df86fce7441a49e01"
    )
    assert len(profile.columns) == 46
    assert len({column.header for column in profile.columns}) == 46
    assert profile.columns[0] == Column(
        header="GWP 100 [kg CO2-eq]",
        method="IPCC 2021",
        category="IPCC 2021 GWP 100",
    )
    assert profile.columns[-1] == Column(
        header="Water use [m3 world eq]",
        method="EF 3.1 Method (adapted)",
        category="Water use",
    )
    assert profile.total.header == "Total [UBP]"
    assert profile.total.method == "Ecological Scarcity 2021"
    assert profile.tolerance == 1e-4
    assert profile.validated is not None
    assert profile.validated.processes == 11947
    assert profile.validated.columns == 46
    assert profile.validated.differences == 12402
    assert profile.validated.largest_rel_diff_within_tolerance == 8.327755357860483e-05
    assert (profile.unlinked, profile.differences) == (
        "unlinked-2026-v1.csv",
        "differences-2026-v1.csv",
    )
    assert recorded(profile.unlinked) == RELEASES / "unlinked-2026-v1.csv"
    listed = recorded(profile.differences)
    assert listed == RELEASES / "differences-2026-v1.csv"
    assert len(read_differences(listed)) == profile.validated.differences


def test_a_version_without_a_profile_names_the_versions_carried() -> None:
    with pytest.raises(NotFound) as missing:
        read_profile("2025-v1")
    assert "2025-v1" in str(missing.value)
    assert "2026-v1" in str(missing.value)


def test_the_differences_round_trip_in_process_and_column_order(tmp_path: Path) -> None:
    path = tmp_path / "differences-2026-v1.csv"
    write_differences(path, reversed(PAIRS))
    assert read_differences(path) == PAIRS
    assert path.read_text().splitlines()[0] == "process_id,column"


def test_a_pair_listed_twice_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "differences-2026-v1.csv"
    path.write_text(
        "process_id,column\n"
        f"{PAIRS[0].process_id},Energy resources [UBP]\n"
        f"{PAIRS[0].process_id},Energy resources [UBP]\n"
    )
    with pytest.raises(Invalid) as refused:
        read_differences(path)
    message = str(refused.value)
    assert PAIRS[0].process_id in message
    assert "Energy resources [UBP]" in message
