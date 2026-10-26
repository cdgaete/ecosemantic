"""BAFU's bundle: the export of a zolca, read back by the core under the release's name."""

from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import pytest

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.bafu import build as build_module
from ecosemantic.databases.bafu import cli as bafu_cli
from ecosemantic.databases.bafu.build import build
from ecosemantic.databases.bafu.profile import Profile
from ecosemantic.databases.zolca.export import write
from ecosemantic.errors import Conflict, NotSupported
from ecosemantic.package.background import Import, read_background
from tests.databases.bafu.test_download import (
    INVENTORY_UUID,
    StubNexus,
    pinned_profile,
)
from tests.databases.zolca.fixture import FIXTURES

ZOLCA = FIXTURES / "openlca.zip"


def _session(server: StubNexus) -> type:
    """A stand-in for `NexusSession` whose `from_environment` answers a session over the stub, so no
    command in a test logs in."""

    class Session:
        @classmethod
        def from_environment(cls, *, base: str) -> contextlib.nullcontext[StubNexus]:
            return contextlib.nullcontext(server)

    return Session


def _profile_pinning_the_fixture() -> Profile:
    """A release whose inventory pack pins the hash of the fixture's own bytes."""
    digest = hashlib.sha256(ZOLCA.read_bytes()).hexdigest()
    pinned = pinned_profile()
    return pinned.model_copy(
        update={"inventory": pinned.inventory.model_copy(update={"sha256": digest})}
    )


def test_a_build_writes_the_bundle_its_export_writes(tmp_path: Path) -> None:
    found = build(ZOLCA, version="probe", out_dir=tmp_path)
    direct = write.export(ZOLCA, tmp_path / "direct.zip")

    assert found.bundle == tmp_path / "bafu-probe.zip"
    assert found.bundle.exists()
    assert not (tmp_path / ".bafu-probe.staging.zip").exists()
    assert found.records == direct.records
    assert found.not_carried == direct.not_carried
    assert found.records["processes"] == 2


def test_the_build_reads_its_bundle_back_under_the_releases_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read: list[tuple[Path, str, frozenset[str]]] = []

    def recorded(path: Path, name: str, *, foreground: frozenset[str]) -> Import:
        read.append((path, name, foreground))
        return read_background(path, name, foreground=foreground)

    monkeypatch.setattr(build_module, "read_background", recorded)
    found = build(ZOLCA, version="2026-v1", out_dir=tmp_path)

    assert [(path.name, name, foreground) for path, name, foreground in read] == [
        (".bafu-2026-v1.staging.zip", "bafu-2026-v1", frozenset())
    ]
    assert found.bundle == tmp_path / "bafu-2026-v1.zip"


def test_a_second_build_into_the_same_directory_is_a_conflict(tmp_path: Path) -> None:
    built = build(ZOLCA, version="probe", out_dir=tmp_path)

    with pytest.raises(Conflict):
        build(ZOLCA, version="probe", out_dir=tmp_path)

    assert built.bundle.exists()


def test_a_bundle_the_core_refuses_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuses(path: Path, name: str, *, foreground: frozenset[str]) -> Import:
        raise NotSupported(f"{path.name}: the core refuses this bundle")

    monkeypatch.setattr(build_module, "read_background", refuses)
    with pytest.raises(NotSupported):
        build(ZOLCA, version="probe", out_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_the_command_builds_from_the_zolca_it_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        databases_cli.main(
            ["bafu", "build", "2026-v1", "--out", str(tmp_path), "--zolca", str(ZOLCA)]
        )
        == 0
    )
    answer = json.loads(capsys.readouterr().out)

    assert answer["bundle"] == str(tmp_path / "bafu-2026-v1.zip")
    assert answer["records"]["processes"] == 2
    assert answer["not_carried"][0] == {
        "table": "OPENLCA_VERSION",
        "rows": 1,
        "reason": "no openLCA JSON-LD record holds this table's rows",
    }


def test_without_a_zolca_the_command_builds_the_pack_its_profile_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubNexus(tmp_path)
    server.contents[INVENTORY_UUID] = ZOLCA.read_bytes()
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: _profile_pinning_the_fixture())
    monkeypatch.setattr(bafu_cli, "NexusSession", _session(server))
    assert databases_cli.main(["bafu", "build", "2026-v1", "--out", str(tmp_path / "out")]) == 0
    answer = json.loads(capsys.readouterr().out)

    assert answer["bundle"] == str(tmp_path / "out" / "bafu-2026-v1.zip")
    assert [call[0] for call in server.calls] == ["pack", "licence", "download"]
    assert Path(answer["bundle"]).exists()
