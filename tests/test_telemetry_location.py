"""The country a computer's own settings name, and none where they name none."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ecosemantic.telemetry.location import country_here, country_of, country_source, zone_name


@pytest.mark.parametrize(
    ("zone", "country"),
    [
        ("America/Santiago", "CL"),
        ("Pacific/Easter", "CL"),
        ("Chile/Continental", "CL"),
        ("Asia/Calcutta", "IN"),
        ("Europe/Kiev", "UA"),
        ("US/Eastern", "US"),
        # tzdata links each of these to a zone of another country
        ("Europe/Oslo", "NO"),
        ("Europe/Bratislava", "SK"),
        ("Europe/Amsterdam", "NL"),
        ("America/Kralendijk", "BQ"),
        ("Iceland", "IS"),
        ("America/Virgin", "VI"),
        ("Africa/Asmera", "ER"),
        ("Pacific/Truk", "FM"),
        ("Australia/ACT", "AU"),
    ],
)
def test_a_zone_names_its_own_country(zone: str, country: str) -> None:
    assert country_of(zone) == country


@pytest.mark.parametrize(
    "zone",
    [
        "UTC",
        "Etc/UTC",
        "Etc/GMT+4",
        "GMT",
        "CET",
        "EET",
        "EST",
        "HST",
        "MET",
        "MST",
        "WET",
        "EST5EDT",
        "Factory",
        "",
        "../../etc/passwd",
        # tzdata's link alone would name another country
        "Africa/Timbuktu",
        "America/Coral_Harbour",
        "Antarctica/South_Pole",
        "Atlantic/Jan_Mayen",
        "Pacific/Johnston",
        "Pacific/Yap",
    ],
)
def test_a_zone_of_no_one_country_names_none(zone: str) -> None:
    assert country_of(zone) is None


@pytest.mark.parametrize(
    ("named", "zone"),
    [
        ("America/Santiago", "America/Santiago"),
        (":America/Santiago", "America/Santiago"),
        ("/usr/share/zoneinfo/Europe/Zurich", "Europe/Zurich"),
        ("/usr/share/zoneinfo/posix/Europe/Zurich", "Europe/Zurich"),
    ],
)
def test_the_tz_variable_decides_the_zone(tmp_path: Path, named: str, zone: str) -> None:
    assert zone_name({"TZ": named}, tmp_path / "localtime") == zone


def test_a_localtime_that_is_a_copy_names_no_zone(tmp_path: Path) -> None:
    (tmp_path / "localtime").write_bytes(b"TZif")
    assert zone_name({}, tmp_path / "localtime") is None
    assert zone_name({}, tmp_path / "missing") is None


linked = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows reads its region setting and has no localtime link"
)


@linked
@pytest.mark.parametrize(
    ("target", "zone"),
    [
        ("../usr/share/zoneinfo/America/Santiago", "America/Santiago"),
        ("/var/db/timezone/zoneinfo/Europe/Zurich", "Europe/Zurich"),
        ("/usr/share/zoneinfo.default/Asia/Tokyo", "Asia/Tokyo"),
        ("/nix/store/h-tzdata/share/zoneinfo/right/Europe/Oslo", "Europe/Oslo"),
    ],
)
def test_the_localtime_link_names_the_zone(tmp_path: Path, target: str, zone: str) -> None:
    (tmp_path / "localtime").symlink_to(target)
    assert zone_name({}, tmp_path / "localtime") == zone


@linked
def test_a_zone_that_links_into_another_country_keeps_its_own_name(tmp_path: Path) -> None:
    zones = tmp_path / "zoneinfo" / "Europe"
    zones.mkdir(parents=True)
    (zones / "Prague").write_bytes(b"TZif")
    (zones / "Bratislava").symlink_to("Prague")
    (tmp_path / "localtime").symlink_to(zones / "Bratislava")
    assert zone_name({}, tmp_path / "localtime") == "Europe/Bratislava"


@linked
def test_a_link_to_a_link_is_followed_to_the_zone_it_names(tmp_path: Path) -> None:
    (tmp_path / "static").symlink_to("/usr/share/zoneinfo/Europe/Zurich")
    (tmp_path / "localtime").symlink_to("static")
    assert zone_name({}, tmp_path / "localtime") == "Europe/Zurich"


@linked
def test_links_in_a_circle_name_no_zone(tmp_path: Path) -> None:
    (tmp_path / "localtime").symlink_to("other")
    (tmp_path / "other").symlink_to("localtime")
    assert zone_name({}, tmp_path / "localtime") is None


@linked
def test_a_tz_that_names_the_localtime_file_reads_its_link(tmp_path: Path) -> None:
    (tmp_path / "localtime").symlink_to("/usr/share/zoneinfo/America/Santiago")
    named = {"TZ": f":{tmp_path / 'localtime'}"}
    assert zone_name(named, tmp_path / "localtime") == "America/Santiago"


@linked
def test_the_country_here_is_the_time_zone_s() -> None:
    assert country_here({"TZ": "America/Santiago"}) == "CL"
    assert country_here({"TZ": "UTC"}) is None
    assert country_here({"TZ": ""}) is None
    assert country_source() == "time zone"


@pytest.mark.skipif(sys.platform != "win32", reason="the region setting is Windows'")
def test_on_windows_the_country_here_is_the_region_setting_s() -> None:
    import ctypes

    region = ctypes.create_unicode_buffer(16)
    assert ctypes.WinDLL("kernel32").GetUserDefaultGeoName(region, 16) > 0
    expected = region.value if region.value.isalpha() else None
    assert country_here({"TZ": "America/Santiago"}) == expected
    assert country_source() == "region setting"
