"""What an ecoinvent release prepares for an install: one bundle built, validated and read."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from ecoinvent_interface import ReleaseType

from ecosemantic.databases.ecoinvent.profile import default_profile
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.databases.ecoinvent.setup import prepare
from ecosemantic.errors import Invalid
from ecosemantic.ports.types import InstallProgress
from tests.databases.spold_fixture import ELEC, build_release, offset_cumulative

STEPS = ["downloading", "downloaded", "building", "validating", "reading"]


class FixtureClient:
    """A release client answering the files a synthetic release holds, fetching nothing."""

    def __init__(self, release: Release, root: Path) -> None:
        self.release = release
        self.root = root

    def _alone(self, name: str, path: Path) -> Path:
        """A folder holding a copy of one file, the way a release's archive holds it."""
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, folder / path.name)
        return folder

    def get_release(
        self, version: str, system_model: str, release_type: ReleaseType, _extract: bool
    ) -> Path:
        if release_type is ReleaseType.ecospold:
            return self.release.ecospold
        if release_type is ReleaseType.matrix:
            return self.release.matrix
        return self._alone("cumulative", self.release.cumulative_lcia)

    def list_extra_files(self, version: str) -> dict[str, object]:
        return {
            f"ecoinvent {version}_LCIA_implementation.7z": {},
            f"Database-Overview-for-ecoinvent-v{version}.xlsx": {},
        }

    def get_extra(self, version: str, filename: str) -> Path:
        if filename.endswith(".7z"):
            return self._alone("lcia", self.release.lcia)
        return self.release.overview


def test_prepare_builds_validates_and_reads_the_synthetic_release(tmp_path: Path) -> None:
    release = build_release(tmp_path / "release")
    profile = default_profile(release)
    reported: list[InstallProgress] = []

    prepared = prepare(
        release.version,
        release.system_model,
        FixtureClient(release, tmp_path / "client"),
        profile,
        tmp_path / "work",
        reported.append,
    )

    assert prepared.name == f"ecoinvent-{release.version}-cutoff"
    assert prepared.bundle == tmp_path / "work" / f"ecoinvent-{release.version}-cutoff.zip"
    assert prepared.bundle.is_file()
    assert prepared.validation.mismatches == []
    assert prepared.validation.counts["scores"] == 4
    assert (tmp_path / "work" / "validation" / "background.json").is_file()
    assert len(prepared.imported.datasets) == 4
    assert [progress.step for progress in reported] == STEPS
    assert reported[1].count is not None and reported[1].count > 0


def test_prepare_refuses_a_build_that_differs_from_the_release_s_results(tmp_path: Path) -> None:
    release = build_release(tmp_path / "release", cancelling_factor=True)
    offset_cumulative(release, ELEC, 1e-13)
    profile = default_profile(release)
    reported: list[InstallProgress] = []

    with pytest.raises(Invalid) as refused:
        prepare(
            release.version,
            release.system_model,
            FixtureClient(release, tmp_path / "client"),
            profile,
            tmp_path / "work",
            reported.append,
        )

    assert "reading" not in [progress.step for progress in reported]
    assert "electricity production" in str(refused.value)
