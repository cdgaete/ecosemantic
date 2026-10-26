"""The BAFU command answers one JSON document, and a typed error as its envelope on stderr."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
from lca_data_interface.errors import CredentialsMissing

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.bafu import cli as bafu_cli
from tests.databases.bafu.test_download import (
    CITATION,
    INVENTORY_FILE,
    LICENCE_FILE,
    RESULTS_FILE,
    RESULTS_UUID,
    StubNexus,
    pinned_profile,
)


def _opened(server: StubNexus) -> type:
    """A stand-in for `NexusSession` whose `from_environment` answers a session over the stub, so
    no command in a test logs in."""

    class Session:
        @classmethod
        def from_environment(cls, *, base: str) -> contextlib.nullcontext[StubNexus]:
            return contextlib.nullcontext(server)

    return Session


def test_a_download_answers_the_paths_the_hashes_the_licence_and_the_citation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubNexus(tmp_path)
    profile = pinned_profile()
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: profile)
    monkeypatch.setattr(bafu_cli, "NexusSession", _opened(server))
    assert databases_cli.main(["bafu", "download", "2026-v1", "--accept-terms", "--results"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer == {
        "inventory": {"path": str(tmp_path / INVENTORY_FILE), "sha256": profile.inventory.sha256},
        "results": {"path": str(tmp_path / RESULTS_FILE), "sha256": profile.results.sha256},
        "licence": str(tmp_path / LICENCE_FILE),
        "citation": CITATION,
    }


def test_without_accept_terms_the_command_exits_2_with_the_licence_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubNexus(tmp_path)
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(bafu_cli, "NexusSession", _opened(server))
    assert databases_cli.main(["bafu", "download", "2026-v1", "--results"]) == 2
    answer = json.loads(capsys.readouterr().out)
    assert answer == {"licence": str(tmp_path / LICENCE_FILE), "citation": CITATION}
    assert [call[0] for call in server.calls] == ["pack", "licence"]


def test_a_pack_whose_hash_differs_answers_its_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubNexus(tmp_path)
    server.contents[RESULTS_UUID] = b"the LCIA results, one byte changed"
    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(bafu_cli, "NexusSession", _opened(server))
    assert databases_cli.main(["bafu", "download", "2026-v1", "--accept-terms", "--results"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "conflict"
    assert RESULTS_UUID in err["message"]


def test_credentials_absent_are_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Absent:
        @classmethod
        def from_environment(cls, *, base: str) -> Absent:
            raise CredentialsMissing(("NEXUS_USERNAME", "NEXUS_PASSWORD"))

    monkeypatch.setattr(bafu_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(bafu_cli, "NexusSession", Absent)
    assert databases_cli.main(["bafu", "download", "2026-v1", "--accept-terms"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "unavailable"
    assert "NEXUS_USERNAME and NEXUS_PASSWORD" in err["message"]
