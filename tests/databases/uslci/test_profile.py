"""The USLCI profile pins the release and the method the spec measured, and lists the versions
its releases directory carries."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ecosemantic.databases.uslci import profile as uslci_profile
from ecosemantic.databases.uslci.profile import RELEASES, Pin, read_profile, versions
from ecosemantic.errors import NotFound


def test_the_shipped_profile_pins_the_release_the_spec_measured() -> None:
    profile = read_profile("1.2026-09.0")
    assert profile.inventory == Pin(
        repository="National_Renewable_Energy_Laboratory/USLCI_Database_Public",
        commit="fddfc1a7a6c93e1a71f457446df7813245c828e6",
        sha256="d1b354d11b757efecd8f456077744e83b9c74b4df0d99e18256bdd0335ac5009",
    )
    assert profile.methods == (
        Pin(
            repository="Federal_LCA_Commons/IPCC_GWP",
            release="1.2026-09.2",
            commit="f0f90ef2f056be6e1686df0858a57b66ecfa2a62",
            sha256="951aaf4bf318a34d54e1b3bf553eac7242f46ca14e96d0ef16b821a4c571b785",
        ),
    )
    assert (profile.unlinked, profile.left_out) == (
        "unlinked-1.2026-09.0.csv",
        "left-out-1.2026-09.0.csv",
    )
    assert profile.tolerance == 1e-8
    assert profile.validated is not None
    assert (profile.validated.datasets, profile.validated.categories) == (2548, 10)


def test_a_version_without_a_profile_names_the_versions_carried() -> None:
    with pytest.raises(NotFound) as missing:
        read_profile("0.0")
    assert "0.0" in str(missing.value)
    assert "1.2026-09.0" in str(missing.value)


def test_versions_are_newest_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shipped = (RELEASES / "1.2026-09.0.yaml").read_text(encoding="utf-8")
    (tmp_path / "1.2026-09.0.yaml").write_text(shipped, encoding="utf-8")
    later = yaml.safe_load(shipped)
    later["version"] = "1.2027-01.0"
    (tmp_path / "1.2027-01.0.yaml").write_text(yaml.safe_dump(later), encoding="utf-8")
    # the releases directory also holds the two lists, which are not versions
    (tmp_path / "unlinked-1.2026-09.0.csv").write_text("", encoding="utf-8")
    monkeypatch.setattr(uslci_profile, "RELEASES", tmp_path)
    assert versions() == ("1.2027-01.0", "1.2026-09.0")
