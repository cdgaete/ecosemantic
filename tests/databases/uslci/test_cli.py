"""The USLCI command answers one JSON document, and a typed error as its envelope on stderr."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from lca_data_interface.errors import ServiceError

from ecosemantic.databases import cli as databases_cli
from ecosemantic.databases.uslci import cli as uslci_cli
from ecosemantic.databases.uslci.download import Downloads
from ecosemantic.databases.uslci.profile import Pin
from tests.databases.uslci.test_download import (
    BRIDGED,
    BRIDGED_COMMIT,
    BRIDGED_CONTENT,
    CONTENTS,
    INVENTORY_COMMIT,
    METHOD_COMMIT,
    StubCommons,
    pinned_profile,
)
from tests.databases.uslci_fixture import (
    BRIDGED_NAME,
    EXPECTED,
    INVENTORY_NAME,
    METHOD_NAME,
    write_bridged,
    write_inventory,
    write_method,
)


def test_the_command_prints_one_json_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    monkeypatch.setattr(uslci_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(uslci_cli, "CommonsServer", lambda base: server)
    assert databases_cli.main(["uslci", "download", "1.2026-09.0"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer == {
        "inventory": {
            "path": str(tmp_path / f"{INVENTORY_COMMIT}.zip"),
            "sha256": hashlib.sha256(CONTENTS[INVENTORY_COMMIT]).hexdigest(),
        },
        "methods": [
            {
                "path": str(tmp_path / f"{METHOD_COMMIT}.zip"),
                "sha256": hashlib.sha256(CONTENTS[METHOD_COMMIT]).hexdigest(),
            }
        ],
        "bridged": [],
    }


def test_the_command_answers_the_bridged_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubCommons(tmp_path, {**CONTENTS, BRIDGED_COMMIT: BRIDGED_CONTENT})
    pin = Pin(
        repository=BRIDGED,
        release="1.2026-06.1",
        commit=BRIDGED_COMMIT,
        sha256=hashlib.sha256(BRIDGED_CONTENT).hexdigest(),
    )
    profile = pinned_profile().model_copy(update={"bridged": (pin,)})
    monkeypatch.setattr(uslci_cli, "read_profile", lambda version: profile)
    monkeypatch.setattr(uslci_cli, "CommonsServer", lambda base: server)
    assert databases_cli.main(["uslci", "download", "1.2026-09.0"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["bridged"] == [
        {"path": str(tmp_path / f"{BRIDGED_COMMIT}.zip"), "sha256": pin.sha256}
    ]


def test_a_refused_download_answers_its_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = ServiceError("GET /ws/public/download/json/prepare", 503, "the server is down")
    monkeypatch.setattr(uslci_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(uslci_cli, "CommonsServer", lambda base: server)
    assert databases_cli.main(["uslci", "download", "1.2026-09.0"]) == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "unavailable"
    assert "the server is down" in err["message"]


def test_the_probe_command_prints_one_json_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    assert databases_cli.main(["uslci", "probe", str(inventory), str(method)]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert set(answer) == {
        "schema_versions",
        "processes",
        "elementary_flows",
        "methods",
        "categories",
        "characterised",
        "unknown_units",
        "other_property",
        "refused",
        "unit_factors_differ",
        "unlinked_by_category",
        "bridges_linked",
        "bridges_unlinked",
        "build_refused",
    }
    assert answer["schema_versions"] == EXPECTED["schema_versions"]
    assert answer["processes"] == EXPECTED["processes"]
    assert answer["characterised"] == EXPECTED["characterised"]
    assert answer["unit_factors_differ"] == EXPECTED["unit_factors_differ"]
    assert answer["refused"] == EXPECTED["refused"]
    assert answer["unlinked_by_category"] == EXPECTED["unlinked_by_category"]
    assert answer["build_refused"] is None


def test_the_build_command_prints_one_json_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    out = tmp_path / "out"
    assert (
        databases_cli.main(
            [
                "uslci",
                "build",
                "1.2026-09.0",
                "--out",
                str(out),
                "--inventory",
                str(inventory),
                "--method",
                str(method),
            ]
        )
        == 0
    )
    answer = json.loads(capsys.readouterr().out)
    assert answer["bundle"] == str(out / "uslci-1.2026-09.0.zip")
    assert Path(answer["bundle"]).is_file()
    assert answer["converted"] == EXPECTED["bundle"]["converted"]
    assert len(answer["left_out"]) == len(EXPECTED["left_out"])
    assert answer["processes"] == EXPECTED["processes"]


def test_the_build_command_builds_the_profile_s_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    monkeypatch.setattr(uslci_cli, "read_profile", lambda version: pinned_profile())
    monkeypatch.setattr(uslci_cli, "CommonsServer", lambda base: object())
    monkeypatch.setattr(
        uslci_cli,
        "download",
        lambda profile, server: Downloads(inventory=inventory, methods=(method,)),
    )
    out = tmp_path / "out"
    assert databases_cli.main(["uslci", "build", "1.2026-09.0", "--out", str(out)]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["bundle"] == str(out / "uslci-1.2026-09.0.zip")


def test_the_build_command_takes_the_bridged_repositories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inventory = write_inventory(tmp_path / INVENTORY_NAME)
    method = write_method(tmp_path / METHOD_NAME)
    out = tmp_path / "out"
    assert (
        databases_cli.main(
            [
                "uslci",
                "build",
                "1.2026-09.0",
                "--out",
                str(out),
                "--inventory",
                str(inventory),
                "--method",
                str(method),
                "--bridged",
                str(write_bridged(tmp_path / BRIDGED_NAME)),
            ]
        )
        == 0
    )
    answer = json.loads(capsys.readouterr().out)
    assert answer["bridges_linked"] == EXPECTED["bridged"]["bridges_linked"]
    assert answer["bridges_unlinked"] == EXPECTED["bridged"]["bridges_unlinked"]
    assert Path(answer["bundle"]).is_file()


def test_the_build_command_names_the_files_it_needs_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    method = write_method(tmp_path / METHOD_NAME)
    assert (
        databases_cli.main(
            [
                "uslci",
                "build",
                "1.2026-09.0",
                "--out",
                str(tmp_path / "out"),
                "--method",
                str(method),
            ]
        )
        == 1
    )
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "invalid"
    assert "--inventory" in err["message"]
