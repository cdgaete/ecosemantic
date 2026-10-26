from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ecosemantic.databases.ecoinvent import cli
from ecosemantic.databases.ecoinvent import profile as profiles
from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.cli import main
from ecosemantic.databases.ecoinvent.profile import default_profile, read_profile
from ecosemantic.databases.ecoinvent.release import Release, sha256
from tests.databases.spold_fixture import STEEL, build_release, tamper_cumulative
from tests.databases.test_download import FakeClient

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _release_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, release: Release) -> None:
    monkeypatch.setenv("EI_USERNAME", "someone@example.com")
    monkeypatch.setenv("EI_PASSWORD", "not-the-real-one")
    monkeypatch.setattr(cli, "EcoinventRelease", lambda settings: object())
    monkeypatch.setattr(cli, "download", lambda version, system_model, client: release)
    monkeypatch.setattr(profiles, "RELEASES", tmp_path / "releases")


def test_download_without_credentials_names_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EI_USERNAME", raising=False)
    monkeypatch.delenv("EI_PASSWORD", raising=False)
    assert main(["download", "3.10", "--system-model", "cutoff"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "unavailable" and "EI_USERNAME" in err["message"]


def test_download_prints_every_file_with_its_path_and_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EI_USERNAME", "someone@example.com")
    monkeypatch.setenv("EI_PASSWORD", "not-the-real-one")
    client = FakeClient(tmp_path)
    monkeypatch.setattr(cli, "EcoinventRelease", lambda settings: client)
    assert main(["download", "3.10", "--system-model", "cutoff"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert set(answer) == {"ecospold", "lcia", "matrix", "cumulative_lcia", "overview"}
    overview = tmp_path / "Database-Overview-for-ecoinvent-v3.10.xlsx"
    assert answer["overview"] == {"path": str(overview), "sha256": sha256(overview)}


@pytest.mark.parametrize("command", ["build", "validate"])
def test_a_build_or_a_validation_without_a_profile_refuses(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    release = build_release(tmp_path / "release")
    _release_ready(monkeypatch, tmp_path, release)
    arguments = [command, "3.10", "--system-model", "cutoff"]
    if command == "build":
        arguments += ["--out", str(tmp_path / "out")]
    else:
        arguments += [
            "--bundle",
            str(tmp_path / "a.zip"),
            "--compiled",
            str(tmp_path / "compiled"),
        ]
    assert main(arguments) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "not_found" and "--no-profile" in err["message"]


def test_the_build_command_writes_the_bundle_and_prints_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    _release_ready(monkeypatch, tmp_path, release)
    out = tmp_path / "out"
    assert (
        main(["build", "3.10", "--system-model", "cutoff", "--no-profile", "--out", str(out)]) == 0
    )
    answer = json.loads(capsys.readouterr().out)
    assert answer == {
        "bundle": str(out / "ecoinvent-3.10-cutoff.zip"),
        "processes": 4,
        "flows": 7,
        "methods": 1,
    }


def test_the_validate_command_prints_the_counts_of_a_clean_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    _release_ready(monkeypatch, tmp_path, release)
    assert (
        main(
            [
                "validate",
                "3.10",
                "--system-model",
                "cutoff",
                "--no-profile",
                "--bundle",
                str(written.bundle),
                "--compiled",
                str(tmp_path / "compiled"),
            ]
        )
        == 0
    )
    answer = json.loads(capsys.readouterr().out)
    assert answer["counts"]["scores"] == 4
    assert answer["mismatches"] == []


def test_the_validate_command_exits_one_when_a_score_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    written = build(release, default_profile(release), tmp_path / "out", NOW)
    tamper_cumulative(release, STEEL, factor=1.01)
    _release_ready(monkeypatch, tmp_path, release)
    assert (
        main(
            [
                "validate",
                "3.10",
                "--system-model",
                "cutoff",
                "--no-profile",
                "--bundle",
                str(written.bundle),
                "--compiled",
                str(tmp_path / "compiled"),
            ]
        )
        == 1
    )
    answer = json.loads(capsys.readouterr().out)
    assert any("steel" in mismatch for mismatch in answer["mismatches"])


def test_the_build_command_reads_the_profile_of_a_named_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    _release_ready(monkeypatch, tmp_path, release)
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "3.10-cutoff.yaml").write_text(
        yaml.safe_dump(default_profile(release).model_dump(mode="json"))
    )
    assert main(["build", "3.10", "--system-model", "cutoff", "--out", str(tmp_path / "out")]) == 0
    assert json.loads(capsys.readouterr().out)["processes"] == 4


def test_the_probe_command_ignores_the_profile_when_no_profile_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    _release_ready(monkeypatch, tmp_path, release)
    assert main(["probe", "3.10", "--system-model", "cutoff", "--no-profile"]) == 0
    assert json.loads(capsys.readouterr().out)["datasets"] == 4


def test_the_probe_command_pins_the_default_profile_when_the_release_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release")
    monkeypatch.setenv("EI_USERNAME", "someone@example.com")
    monkeypatch.setenv("EI_PASSWORD", "not-the-real-one")
    monkeypatch.setattr(cli, "EcoinventRelease", lambda settings: object())
    monkeypatch.setattr(cli, "download", lambda version, system_model, client: release)
    monkeypatch.setattr(profiles, "RELEASES", tmp_path / "releases")
    assert main(["probe", "3.10", "--system-model", "cutoff"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["datasets"] == 4
    assert answer["without_url"] == {"count": 0, "first": []}


def test_the_probe_command_reads_the_profile_named_for_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release = build_release(tmp_path / "release", extra_factor_row=True)
    releases = tmp_path / "releases"
    releases.mkdir()
    profile = default_profile(release).model_copy(update={"expected_unmatched_factors": 1})
    (releases / "3.10-cutoff.yaml").write_text(yaml.safe_dump(profile.model_dump(mode="json")))
    monkeypatch.setenv("EI_USERNAME", "someone@example.com")
    monkeypatch.setenv("EI_PASSWORD", "not-the-real-one")
    monkeypatch.setattr(cli, "EcoinventRelease", lambda settings: object())
    monkeypatch.setattr(cli, "download", lambda version, system_model, client: release)
    monkeypatch.setattr(profiles, "RELEASES", releases)
    read: list[Path] = []

    def record(path: Path):
        read.append(path)
        return read_profile(path)

    monkeypatch.setattr(profiles, "read_profile", record)
    assert main(["probe", "3.10", "--system-model", "cutoff"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert read == [releases / "3.10-cutoff.yaml"]
    assert answer["unmatched_factors"]["count"] == 1
