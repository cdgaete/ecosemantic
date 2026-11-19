from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.databases.ecoinvent import build as build_module
from ecosemantic.databases.ecoinvent import probe as probe_module
from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.profile import default_profile
from ecosemantic.errors import NotSupported
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.package.background import read_background
from ecosemantic.package.manifest import read_manifest
from tests.databases.spold_fixture import (
    STEEL_CLASSIFICATIONS,
    STEEL_COMMENT,
    build_release,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_a_build_refuses_a_release_the_probe_is_not_clean_on(tmp_path: Path) -> None:
    release = build_release(tmp_path, steel_unit="furlong")
    with pytest.raises(NotSupported, match="furlong"):
        build(release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=())


def test_a_build_refuses_a_factor_row_the_release_cannot_answer(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_factor_row=True)
    with pytest.raises(NotSupported, match="Unobtainium"):
        build(release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=())


def test_the_built_bundle_installs_whole_with_its_links(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    written = build(
        release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=()
    )
    assert written.bundle.name == "ecoinvent-3.10-cutoff.zip"
    assert read_manifest(written.bundle).revision == default_profile(release).revision
    imported = read_background(written.bundle, "ecoinvent-3.10-cutoff", foreground=frozenset())
    assert imported.unlinked == []
    assert sum(1 for d in imported.datasets.values() if "url" in d) == 4


def test_the_built_bundle_counts_its_processes_flows_and_categories(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    written = build(
        release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=()
    )
    assert (written.processes, written.flows, written.methods) == (4, 7, 1)
    assert [path.name for path in written.bundle.parent.iterdir()] == ["ecoinvent-3.10-cutoff.zip"]


def test_a_build_reads_the_release_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = build_release(tmp_path)
    calls: list[int] = []
    original = probe_module.read_datasets

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(probe_module, "read_datasets", counted)
    monkeypatch.setattr(build_module, "read_datasets", counted, raising=False)
    build(release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=())
    assert len(calls) == 1


async def test_the_built_steel_dataset_answers_its_comment_and_classifications(
    tmp_path: Path,
) -> None:
    release = build_release(tmp_path)
    written = build(
        release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=()
    )
    imported = read_background(written.bundle, "ecoinvent-3.10-cutoff", foreground=frozenset())
    key = next(k for k, d in imported.datasets.items() if d["name"] == "steel production")
    install(
        tmp_path / "data",
        imported,
        written.bundle,
        version=release.version,
        system_model=release.system_model,
    )
    store = NativeStore(tmp_path / "data")
    read = await NativeInventory(store).get_process(BackgroundRef(database=key[0], id=key[1]))
    store.close()
    assert read.comment == STEEL_COMMENT
    assert read.classifications == [f"{system}: {value}" for system, value in STEEL_CLASSIFICATIONS]


def test_the_built_bundle_names_each_datasets_location(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    written = build(
        release, default_profile(release), tmp_path / "out", NOW, revision=1, corrections=()
    )
    imported = read_background(written.bundle, "ecoinvent-3.10-cutoff", foreground=frozenset())
    assert {dataset["location"] for dataset in imported.datasets.values()} == {"NA", "GLO"}
    assert imported.locations == {"GLO": "Global", "NA": "North America"}
