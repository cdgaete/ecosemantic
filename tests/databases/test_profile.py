"""The profile pins a release's layouts and file hashes, and a build verifies them."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ecosemantic.databases.ecoinvent.profile import (
    default_profile,
    profiled,
    read_profile,
    verify,
)
from ecosemantic.databases.ecoinvent.release import sha256
from ecosemantic.errors import Conflict, Invalid
from tests.databases.spold_fixture import build_release


def test_profiled_lists_the_four_cutoff_releases() -> None:
    assert profiled() == [
        ("3.10", "cutoff"),
        ("3.10.1", "cutoff"),
        ("3.11", "cutoff"),
        ("3.12", "cutoff"),
    ]


def test_a_file_whose_hash_differs_is_a_conflict(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    release.lcia.write_bytes(release.lcia.read_bytes() + b"changed")
    with pytest.raises(Conflict, match="lcia"):
        verify(release, profile)


def test_a_release_whose_files_match_its_profile_verifies(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    assert verify(release, default_profile(release)) is None


def test_a_profile_that_names_no_file_the_release_has_is_invalid(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    without_lcia = {role: file for role, file in profile.files.items() if role != "lcia"}
    with pytest.raises(Invalid, match="lcia"):
        verify(release, profile.model_copy(update={"files": without_lcia}))


def test_the_default_profile_names_the_3_10_layout_and_hashes_every_file(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    assert profile.version == "3.10" and profile.system_model == "cutoff"
    assert profile.lcia.factors.sheet == "CFs"
    assert profile.lcia.factors.columns == (
        "Method",
        "Category",
        "Indicator",
        "Name",
        "Compartment",
        "Subcompartment",
        "CF",
    )
    assert profile.lcia.units.sheet == "Indicators"
    assert profile.lcia.units.columns == ("Method", "Category", "Indicator", "Indicator Unit")
    assert profile.overview.sheet == "Cut-Off AO"
    assert profile.overview.columns == ("Activity UUID & Product UUID", "ecoQuery URL")
    assert set(profile.files) == set(release.files())
    assert profile.files["lcia"].sha256 == sha256(release.lcia)
    assert profile.zero_spread == "refuse"
    assert profile.expected_unmatched_factors == 0
    assert profile.expected_zero_spread == 0
    assert profile.expected_without_url == 0
    assert profile.read_as_documentation == []
    assert profile.validated is None


def test_a_profile_round_trips_through_yaml(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    path = tmp_path / "3.10-cutoff.yaml"
    path.write_text(yaml.safe_dump(profile.model_dump(mode="json")), encoding="utf-8")
    assert read_profile(path) == profile


def test_the_default_profile_names_each_file_relative_to_the_cache_directory(
    tmp_path: Path,
) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    assert all(not Path(file.path).is_absolute() for file in profile.files.values())
    path = tmp_path / "3.10-cutoff.yaml"
    path.write_text(yaml.safe_dump(profile.model_dump(mode="json")), encoding="utf-8")
    assert read_profile(path) == profile


def test_a_profile_naming_an_absolute_path_is_invalid(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    profile = default_profile(release)
    files = {
        role: file.model_copy(update={"path": str(release.files()[role])})
        if role == "lcia"
        else file
        for role, file in profile.files.items()
    }
    path = tmp_path / "absolute.yaml"
    path.write_text(
        yaml.safe_dump(profile.model_copy(update={"files": files}).model_dump(mode="json")),
        encoding="utf-8",
    )
    with pytest.raises(Invalid, match="lcia"):
        read_profile(path)
