from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.profile import default_profile
from ecosemantic.errors import NotSupported
from ecosemantic.package.background import read_background
from tests.databases.spold_fixture import build_release

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_a_build_refuses_a_release_the_probe_is_not_clean_on(tmp_path: Path) -> None:
    release = build_release(tmp_path, steel_unit="furlong")
    with pytest.raises(NotSupported, match="furlong"):
        build(release, default_profile(release), tmp_path / "out", NOW)


def test_a_build_refuses_a_factor_row_the_release_cannot_answer(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_factor_row=True)
    with pytest.raises(NotSupported, match="Unobtainium"):
        build(release, default_profile(release), tmp_path / "out", NOW)


def test_the_built_bundle_installs_whole_with_its_links(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    assert written.bundle.name == "ecoinvent-3.10-cutoff.zip"
    imported = read_background(written.bundle, "ecoinvent-3.10-cutoff", foreground=frozenset())
    assert imported.unlinked == []
    assert sum(1 for d in imported.datasets.values() if "url" in d) == 4


def test_the_built_bundle_counts_its_processes_flows_and_categories(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    assert (written.processes, written.flows, written.methods) == (4, 7, 1)
    assert [path.name for path in written.bundle.parent.iterdir()] == ["ecoinvent-3.10-cutoff.zip"]
