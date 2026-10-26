"""The probe lists what a release holds that a build cannot read."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ecosemantic.databases.ecoinvent.probe import Probe, probe, report
from ecosemantic.databases.ecoinvent.profile import Profile, default_profile
from tests.databases.spold_fixture import (
    AIR,
    AIR_ACTIVITY,
    ELEC,
    ELEC_ACTIVITY,
    NS,
    OVERVIEW_COLUMNS,
    STEEL,
    STEEL_ACTIVITY,
    TREAT,
    TREAT_ACTIVITY,
    _write_workbook,
    build_release,
)

GHOST = "00000020-0000-4000-8000-000000000020"


def test_the_probe_of_a_clean_release_is_clean(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    found = probe(release, default_profile(release))
    assert found.datasets == 4 and found.clean(default_profile(release))


def test_the_probe_lists_everything_a_build_would_refuse(tmp_path: Path) -> None:
    release = build_release(
        tmp_path,
        steel_unit="furlong",
        lognormal_variance=0.0,
        extra_factor_row=True,
        overview_missing=True,
    )
    found = probe(release, default_profile(release))
    assert "furlong" in found.unknown_units
    assert len(found.degenerate_uncertainty) == 1
    assert found.unmatched_factors == [("Unobtainium", "air", "unspecified")]
    assert found.without_url == [ELEC]
    assert not found.clean(default_profile(release))


def test_the_probe_is_clean_when_the_profile_expects_its_unmatched_factors(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_factor_row=True)
    profile = default_profile(release).model_copy(update={"expected_unmatched_factors": 1})
    found = probe(release, profile)
    assert len(found.unmatched_factors) == 1 and found.clean(profile)


def test_the_probe_lists_an_overview_url_that_names_no_dataset(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _write_workbook(
        release.overview,
        {
            "Cut-Off AO": [
                list(OVERVIEW_COLUMNS),
                [STEEL, STEEL_ACTIVITY, "https://example.test/steel", "steel production", "NA"],
                [ELEC, ELEC_ACTIVITY, "https://example.test/elec", "electricity", "GLO"],
                [TREAT, TREAT_ACTIVITY, "https://example.test/treat", "treatment", "NA"],
                [AIR, AIR_ACTIVITY, "https://example.test/air", "compressed air", "GLO"],
                [GHOST, GHOST, "https://example.test/ghost", "ghost production", "NA"],
            ]
        },
    )
    found = probe(release, default_profile(release))
    assert found.urls_without_dataset == [GHOST]
    assert found.without_url == []


def test_the_report_cuts_every_list_to_twenty_and_keeps_its_count() -> None:
    found = Probe(
        datasets=25,
        unknown_units={"kg*day": [f"dataset {index}" for index in range(25)]},
        unread={"formula": [f"dataset {index}" for index in range(25)]},
        degenerate_uncertainty=[f"dataset {index}" for index in range(25)],
        unmatched_factors=[("Unobtainium", "air", "unspecified")] * 25,
        without_url=[f"dataset {index}" for index in range(25)],
        urls_without_dataset=[f"url {index}" for index in range(25)],
        documentation={"parameter": [f"dataset {index}" for index in range(25)]},
        units_without_use=[f"unit {index}" for index in range(25)],
        compartments=[("air", "unspecified", "emission")] * 25,
    )
    answer = report(found)
    assert answer["datasets"] == 25
    assert answer["unknown_units"] == {
        "count": 1,
        "first": {"kg*day": {"count": 25, "first": [f"dataset {index}" for index in range(20)]}},
    }
    assert answer["unread"] == {
        "count": 1,
        "first": {"formula": {"count": 25, "first": [f"dataset {index}" for index in range(20)]}},
    }
    assert answer["degenerate_uncertainty"] == {
        "count": 25,
        "first": [f"dataset {index}" for index in range(20)],
    }
    assert answer["unmatched_factors"] == {
        "count": 25,
        "first": [("Unobtainium", "air", "unspecified")] * 20,
    }
    assert answer["without_url"]["count"] == 25
    assert len(answer["without_url"]["first"]) == 20
    assert answer["urls_without_dataset"]["count"] == 25
    assert answer["documentation"] == {
        "count": 1,
        "first": {"parameter": {"count": 25, "first": [f"dataset {index}" for index in range(20)]}},
    }
    assert answer["units_without_use"]["count"] == 25
    assert answer["compartments"]["count"] == 25


def _profile(release, **updates: object) -> Profile:
    return default_profile(release).model_copy(update=updates)


def _write_parameter(release, native: str) -> None:
    path = release.ecospold / "datasets" / f"{native}.spold"
    tree = ET.parse(path)
    dataset = tree.getroot().find(f"{{{NS}}}childActivityDataset")
    assert dataset is not None
    flow_data = dataset.find(f"{{{NS}}}flowData")
    assert flow_data is not None
    ET.SubElement(flow_data, f"{{{NS}}}parameter", {"parameterId": "p", "amount": "1.0"})
    tree.write(path, encoding="utf-8")


def test_a_documentation_feature_the_profile_does_not_pin_is_not_clean(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    _write_parameter(release, STEEL)
    found = probe(release, default_profile(release))
    assert found.documentation == {"parameter": [STEEL]}
    assert not found.clean(default_profile(release))
    assert found.clean(_profile(release, read_as_documentation=["parameter"]))


def test_the_probe_checks_the_zero_spread_count_the_profile_pins(tmp_path: Path) -> None:
    release = build_release(tmp_path, lognormal_variance=0.0)
    accepted = _profile(release, zero_spread="none", expected_zero_spread=1)
    found = probe(release, accepted)
    assert len(found.degenerate_uncertainty) == 1 and found.clean(accepted)
    assert not found.clean(_profile(release, zero_spread="none", expected_zero_spread=0))
    assert not found.clean(default_profile(release))


def test_the_probe_checks_the_datasets_without_a_url_the_profile_pins(tmp_path: Path) -> None:
    release = build_release(tmp_path, overview_missing=True)
    accepted = _profile(release, expected_without_url=1)
    found = probe(release, accepted)
    assert found.without_url == [ELEC] and found.clean(accepted)
    assert not found.clean(default_profile(release))


def test_the_probe_lists_a_unit_the_core_lacks_and_no_exchange_uses(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    found = probe(release, default_profile(release))
    assert found.units_without_use == ["hogshead"]
    assert found.clean(default_profile(release))


def test_the_probe_lists_every_compartment_pair_with_the_category_it_files_under(
    tmp_path: Path,
) -> None:
    release = build_release(tmp_path)
    found = probe(release, default_profile(release))
    assert ("air", "unspecified", "emission") in found.compartments
    assert ("natural resource", "in ground", "natural resource") in found.compartments
