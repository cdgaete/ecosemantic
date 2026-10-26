"""The LCIA workbook is read into base methods, and a factor no flow answers is listed."""

from __future__ import annotations

from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.lcia import LciaLayout, Sheet, read_methods
from ecosemantic.databases.ecoinvent.masterdata import read_masterdata
from ecosemantic.errors import Invalid
from tests.databases.spold_fixture import (
    CO2,
    IRON,
    UNUSED,
    UNUSED_FACTOR,
    _write_workbook,
    build_release,
)

LAYOUT = LciaLayout(
    factors=Sheet(
        "CFs",
        ("Method", "Category", "Indicator", "Name", "Compartment", "Subcompartment", "CF"),
    ),
    units=Sheet("Indicators", ("Method", "Category", "Indicator", "Indicator Unit")),
)

_FACTORS = list(LAYOUT.factors.columns)
_UNITS = list(LAYOUT.units.columns)
_GWP = ["IPCC 2021", "climate change", "GWP100"]
_ACID = ["CML", "acidification", "acidification"]


def _write(path: Path, factors: list[list[object]], units: list[list[object]]) -> Path:
    _write_workbook(path, {"CFs": [_FACTORS, *factors], "Indicators": [_UNITS, *units]})
    return path


def test_factors_match_flows_by_name_and_compartments(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    methods, unmatched = read_methods(release.lcia, LAYOUT, read_masterdata(release.ecospold), "db")
    [method] = methods
    assert method.key == ("db", "IPCC 2021", "climate change", "GWP100")
    assert method.unit == "kg CO2-Eq" and method.factors == ((CO2, 1.0), (UNUSED, UNUSED_FACTOR))
    assert unmatched == []


def test_a_factor_for_a_flow_the_release_lacks_is_listed(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_factor_row=True)
    _, unmatched = read_methods(release.lcia, LAYOUT, read_masterdata(release.ecospold), "db")
    assert unmatched == [("Unobtainium", "air", "unspecified")]


def test_a_header_the_layout_does_not_name_is_invalid(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    wrong = LciaLayout(factors=Sheet("CFs", ("Method", "Name", "CF")), units=LAYOUT.units)
    with pytest.raises(Invalid, match="CFs"):
        read_methods(release.lcia, wrong, read_masterdata(release.ecospold), "db")


def test_the_indicators_header_is_checked_too(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    wrong = LciaLayout(
        factors=LAYOUT.factors, units=Sheet("Indicators", ("Method", "Indicator Unit"))
    )
    with pytest.raises(Invalid, match="Indicators"):
        read_methods(release.lcia, wrong, read_masterdata(release.ecospold), "db")


def test_a_method_keeps_its_factors_in_the_workbooks_order(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    path = _write(
        tmp_path / "order.xlsx",
        [
            [*_GWP, "Carbon dioxide, fossil", "air", "unspecified", 1.0],
            [*_GWP, "Iron", "natural resource", "in ground", 0.5],
        ],
        [[*_GWP, "kg CO2-Eq"]],
    )
    methods, unmatched = read_methods(path, LAYOUT, read_masterdata(release.ecospold), "db")
    assert methods[0].factors == ((CO2, 1.0), (IRON, 0.5))
    assert unmatched == []


def test_each_method_category_and_indicator_is_its_own_method(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    path = _write(
        tmp_path / "two.xlsx",
        [
            [*_GWP, "Carbon dioxide, fossil", "air", "unspecified", 1.0],
            [*_ACID, "Iron", "natural resource", "in ground", 2.0],
        ],
        [
            [*_GWP, "kg CO2-Eq"],
            [*_ACID, "mol H+-Eq"],
        ],
    )
    methods, _ = read_methods(path, LAYOUT, read_masterdata(release.ecospold), "db")
    assert [method.key for method in methods] == [
        ("db", "IPCC 2021", "climate change", "GWP100"),
        ("db", "CML", "acidification", "acidification"),
    ]
    assert [method.unit for method in methods] == ["kg CO2-Eq", "mol H+-Eq"]


def test_a_factor_row_matches_on_the_compartment_pair_and_not_the_name(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    path = _write(
        tmp_path / "wrong-compartment.xlsx",
        [[*_GWP, "Carbon dioxide, fossil", "water", "unspecified", 1.0]],
        [[*_GWP, "kg CO2-Eq"]],
    )
    methods, unmatched = read_methods(path, LAYOUT, read_masterdata(release.ecospold), "db")
    assert methods == ()
    assert unmatched == [("Carbon dioxide, fossil", "water", "unspecified")]


def test_an_indicator_the_factors_name_no_unit_for_is_invalid(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    path = _write(
        tmp_path / "no-unit.xlsx",
        [[*_GWP, "Carbon dioxide, fossil", "air", "unspecified", 1.0]],
        [],
    )
    with pytest.raises(Invalid, match="GWP100"):
        read_methods(path, LAYOUT, read_masterdata(release.ecospold), "db")
