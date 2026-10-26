from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path

import duckdb
import pytest
import yaml

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.cli import main
from ecosemantic.cli.clients import SERVER
from ecosemantic.compute.edits import add_scenario
from ecosemantic.databases.bafu import profile as bafu_profile
from ecosemantic.databases.bafu import setup as bafu_setup
from ecosemantic.databases.uslci import profile as uslci_profile
from ecosemantic.databases.uslci import setup as uslci_setup
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import (
    Case,
    Parameter,
    ParameterOverride,
    ProductSystem,
    method_id,
)
from ecosemantic.model.refs import BackgroundRef
from ecosemantic.package.log import read_log
from ecosemantic.package.manifest import read_manifest
from ecosemantic.tables.folder import write_folder
from tests.database_fixture import BASE, backgrounds, casing_system, flows
from tests.databases.bafu.test_download import CITATION as BAFU_CITATION
from tests.databases.bafu.test_download import INVENTORY_UUID as BAFU_INVENTORY_UUID
from tests.databases.bafu.test_setup import VERSION as BAFU_VERSION
from tests.databases.bafu.test_setup import a_process, importable, unlisted_input
from tests.databases.bafu.test_setup import fixture_release as bafu_release
from tests.databases.bafu.test_setup import session_for as bafu_session
from tests.databases.uslci.install_fixture import fixture_release
from tests.databases.uslci_fixture import EXPECTED as USLCI_EXPECTED
from tests.dict_resolver import DictResolver
from tests.fixture_data import CODES, FIXTURE_DB, GWP
from tests.openlca_fixture import METHOD, NAME, build_package
from tests.openlca_fixture import PROCESSES as OPENLCA_PROCESSES
from tests.package.conftest import AGENT

GWP_ID = method_id(" > ".join(GWP))


def test_no_subcommand_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "serve" in capsys.readouterr().err


def test_a_missing_data_directory_names_itself(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="absent"):
        main(["serve", "--data-dir", str(tmp_path / "absent"), "--systems-dir", str(tmp_path)])


def test_export_then_import_round_trips(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    systems_dir: Path,
    tmp_path: Path,
) -> None:
    zipped = tmp_path / "widget.zip"
    assert (
        main(
            [
                "export",
                "--data-dir",
                str(bundle_dir),
                "--systems-dir",
                str(systems_dir),
                "--id",
                str(fixture_system_stored.id),
                "--to",
                str(zipped),
            ]
        )
        == 0
    )
    assert zipfile.ZipFile(zipped).namelist()

    other = tmp_path / "other-systems"
    other.mkdir()
    assert (
        main(
            [
                "import",
                "--data-dir",
                str(bundle_dir),
                "--systems-dir",
                str(other),
                "--from",
                str(zipped),
            ]
        )
        == 0
    )
    assert (other / str(fixture_system_stored.id)).is_dir()
    assert [e.source for e in read_log(other / str(fixture_system_stored.id))] == ["import"]


def test_export_of_an_unknown_id_returns_one(
    bundle_dir: Path, systems_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "export",
            "--data-dir",
            str(bundle_dir),
            "--systems-dir",
            str(systems_dir),
            "--id",
            str(uuid.uuid4()),
            "--to",
            str(tmp_path / "x.zip"),
            "--json",
        ]
    )
    assert code == 1 and "not_found" in capsys.readouterr().err


def _setup(
    args: list[str], capsys: pytest.CaptureFixture[str], as_json: bool = True
) -> tuple[int, str, str]:
    """Exit code, stdout whole, and stderr's last line, where the CLI's error line goes;
    every caller but the one that reads the answer as text passes --json."""
    code = main(["setup", *args, *(["--json"] if as_json else [])])
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.strip()]
    return code, captured.out, lines[-1] if lines else ""


def test_setup_openlca_refuses_drops_conflicts_and_replaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "data"
    data.mkdir()
    base = [
        "openlca",
        "--data-dir",
        str(data),
        "--package",
        str(package),
        "--name",
        NAME,
        "--version",
        "1",
    ]

    code, out, err = _setup(base, capsys)
    assert code == 1 and json.loads(err)["error"] == "invalid" and "imported part" in err

    code, out, err = _setup([*base, "--drop-unlinked"], capsys)
    summary = json.loads(out)
    assert code == 0 and summary["datasets"] == 6 and summary["methods"] == 2
    assert summary["dropped"] == 1 and summary["unlinked"][0]["flow"] == "imported part"
    assert (Path(summary["directory"]) / "catalog.duckdb").is_file()

    code, out, err = _setup([*base, "--drop-unlinked"], capsys)
    assert code == 1 and json.loads(err)["error"] == "conflict"

    code, out, err = _setup([*base, "--drop-unlinked", "--replace", "--version", "2"], capsys)
    assert code == 0 and json.loads(out)["database"] == NAME


def _uslci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: bool) -> Path:
    """The fixture's packages served through the command's client, and a data directory for it."""
    server, _profile, recorded = fixture_release(tmp_path, **overrides)
    monkeypatch.setattr(uslci_profile, "RELEASES", recorded)
    monkeypatch.setattr(uslci_setup, "CommonsServer", lambda base: server)
    return tmp_path / "data"


def _cut_offs(directory: str) -> list[tuple[object, ...]]:
    """Every cut-off row of an installed catalog, by dataset and position."""
    catalog = duckdb.connect(Path(directory) / "catalog.duckdb", read_only=True)
    rows = catalog.execute(
        "SELECT flow, amount, unit, cut_off FROM exchanges WHERE cut_off IS NOT NULL"
        " ORDER BY process, position"
    ).fetchall()
    catalog.close()
    return rows


def test_a_dropped_input_is_listed_as_cut_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "openlca"
    data.mkdir()
    code, out, err = _setup(
        [
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(build_package(tmp_path / "fixture.zip")),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
        ],
        capsys,
    )
    assert code == 0, err
    assert _cut_offs(json.loads(out)["directory"]) == [
        ("imported part", 1.0, "kilogram", "its provider is not in the package")
    ]

    uslci = _uslci(tmp_path, monkeypatch)
    code, out, err = _setup(["uslci", "--data-dir", str(uslci)], capsys)
    assert code == 0, err
    assert sorted(_cut_offs(json.loads(out)["directory"])) == sorted(
        [("electricity", 1.0, "megajoule", "several processes produce it")] * 2
        + [("imported part", 1.0, "kilogram", "no process produces it")] * 3
    )


def test_setup_openlca_names_the_factors_set_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "regional.zip", regional=True)
    data = tmp_path / "data"
    data.mkdir()
    code, out, err = _setup(
        [
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(package),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
        ],
        capsys,
    )
    summary = json.loads(out)
    assert code == 0, err
    assert summary["set_apart"] == [{"method": METHOD, "category": "climate change", "factors": 1}]


def test_setup_prints_its_steps_on_stderr_and_its_answer_alone_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "data"
    data.mkdir()

    code = main(
        [
            "setup",
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(package),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out)["database"] == NAME
    assert "installing" in captured.err
    assert captured.out.endswith("}\n") and "installing" not in captured.out


def test_setup_ecoinvent_without_a_terminal_or_account_is_refused_naming_the_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EI_USERNAME", raising=False)
    monkeypatch.delenv("EI_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    data = tmp_path / "data"

    code = main(["setup", "ecoinvent", "3.12", "--data-dir", str(data), "--json"])
    captured = capsys.readouterr()

    assert code == 1
    assert json.loads(captured.err)["error"] == "unavailable"
    assert "EI_USERNAME" in captured.err
    assert not data.exists()


def test_setup_summaries_share_their_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "openlca"
    data.mkdir()
    code, out, err = _setup(
        [
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(package),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
        ],
        capsys,
    )
    openlca = json.loads(out)
    assert code == 0, err

    code, out, err = _setup(["uslci", "--data-dir", str(_uslci(tmp_path, monkeypatch))], capsys)
    uslci = json.loads(out)
    assert code == 0, err

    shared = (
        "database",
        "elementary_flows",
        "processes",
        "datasets",
        "flows",
        "methods",
        "unlinked",
        "dropped",
        "directory",
        "set_apart",
    )
    assert tuple(openlca) == shared
    assert tuple(uslci) == (*shared, "sources", "notices")
    assert openlca["set_apart"] == [] and uslci["set_apart"] == []


def test_setup_uslci_installs_the_newest_profile_and_prints_one_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _uslci(tmp_path, monkeypatch)
    code, out, err = _setup(["uslci", "--data-dir", str(data)], capsys)
    summary = json.loads(out)
    assert code == 0, err
    assert summary["database"] == "uslci-1.2026-09.0"
    assert summary["datasets"] == USLCI_EXPECTED["bundle"]["datasets"]
    assert summary["methods"] == USLCI_EXPECTED["categories"]
    assert summary["processes"] == USLCI_EXPECTED["processes"]
    assert summary["dropped"] == len(USLCI_EXPECTED["unlinked"]) == len(summary["unlinked"])
    assert sorted(row["flow_name"] for row in summary["unlinked"]) == [
        "electricity",
        "electricity",
        "imported part",
        "imported part",
    ]
    assert summary["sources"] == [
        {
            "repository": "National_Renewable_Energy_Laboratory/USLCI_Database_Public",
            "release": None,
            "commit": "a" * 40,
        },
        {
            "repository": "Federal_LCA_Commons/IPCC_GWP",
            "release": "1.2026-09.2",
            "commit": "b" * 40,
        },
    ]
    assert summary["notices"] == [
        {"text": text, "datasets": count} for text, count in USLCI_EXPECTED["notices"]
    ]
    assert (Path(summary["directory"]) / "catalog.duckdb").is_file()


def test_setup_uslci_takes_the_version_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _uslci(tmp_path, monkeypatch)
    code, out, err = _setup(["uslci", "--data-dir", str(data), "--version", "1.2026-09.0"], capsys)
    assert code == 0, err
    assert json.loads(out)["database"] == "uslci-1.2026-09.0"


def test_setup_uslci_refuses_a_version_it_carries_no_profile_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _uslci(tmp_path, monkeypatch)
    code, out, err = _setup(["uslci", "--data-dir", str(data), "--version", "9.9"], capsys)
    assert code == 1 and json.loads(err)["error"] == "not_found"
    assert "9.9" in err and "1.2026-09.0" in err


def test_setup_uslci_refuses_the_same_name_twice_without_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _uslci(tmp_path, monkeypatch)
    code, out, _err = _setup(["uslci", "--data-dir", str(data)], capsys)
    assert code == 0
    directory = Path(json.loads(out)["directory"])
    code, out, err = _setup(["uslci", "--data-dir", str(data)], capsys)
    assert code == 1 and json.loads(err)["error"] == "conflict"
    assert (directory / "catalog.duckdb").is_file()
    code, out, err = _setup(["uslci", "--data-dir", str(data), "--replace"], capsys)
    assert code == 0, err
    assert json.loads(out)["directory"] == str(directory)


def test_setup_uslci_writes_nothing_when_an_input_is_outside_its_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _uslci(tmp_path, monkeypatch, drop_unlinked=True)
    code, _out, err = _setup(["uslci", "--data-dir", str(data)], capsys)
    assert code == 1 and json.loads(err)["error"] == "invalid"
    assert "the unlinked list lacks it" in err
    assert not data.exists()
    assert list(tmp_path.rglob("*.partial")) == []


def _bafu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fixture's zolca served through the command's Nexus session, its profile recorded in a
    temporary profiles directory, the account the command logs in with, and a data directory for
    it."""
    server, _profile, recorded = bafu_release(tmp_path)
    monkeypatch.setenv("NEXUS_USERNAME", "someone@example.com")
    monkeypatch.setenv("NEXUS_PASSWORD", os.environ.get("NEXUS_PASSWORD") or "the-password")
    monkeypatch.setattr(bafu_profile, "RELEASES", recorded)
    monkeypatch.setattr(bafu_setup, "NexusSession", bafu_session(server))
    monkeypatch.setattr(bafu_setup, "read_background", importable())
    return tmp_path / "data"


def test_setup_bafu_installs_and_names_what_it_does_not_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _bafu(tmp_path, monkeypatch)
    code, out, err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)
    summary = json.loads(out)
    assert code == 0, err
    assert summary["database"] == f"bafu-{BAFU_VERSION}"
    assert summary["processes"] == 2
    assert summary["unlinked"] == [] and summary["dropped"] == 0
    assert summary["licence"] == str(tmp_path / "downloads" / f"{BAFU_INVENTORY_UUID}-licence.txt")
    assert summary["citation"] == BAFU_CITATION
    assert summary["not_applied"] == {
        "nw_sets": 1,
        "dq_entries": 1,
        "parameters": 2,
        "factor_formulas": 2,
    }
    assert (Path(summary["directory"]) / "catalog.duckdb").is_file()


def test_setup_bafu_without_accept_terms_exits_2_and_installs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _bafu(tmp_path, monkeypatch)
    code, out, err = _setup(["bafu", "--data-dir", str(data)], capsys)

    assert code == 2
    assert json.loads(out) == {
        "licence": str(tmp_path / "downloads" / f"{BAFU_INVENTORY_UUID}-licence.txt"),
        "citation": BAFU_CITATION,
    }
    assert err == ""
    assert not data.exists()
    assert list((tmp_path / "downloads").glob("*.zip")) == []


def test_setup_bafu_without_an_account_names_the_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NEXUS_USERNAME", raising=False)
    monkeypatch.delenv("NEXUS_PASSWORD", raising=False)
    data = tmp_path / "data"

    code, _out, err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)

    refused = json.loads(err)
    assert code == 1 and refused["error"] == "unavailable"
    assert "nexus needs an account" in refused["message"]
    assert "NEXUS_USERNAME and NEXUS_PASSWORD" in refused["details"]["hint"]
    assert not data.exists()


def test_setup_bafu_without_accept_terms_answers_in_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _bafu(tmp_path, monkeypatch)
    code, out, _err = _setup(["bafu", "--data-dir", str(data)], capsys, as_json=False)

    assert code == 2
    licence = str(tmp_path / "downloads" / f"{BAFU_INVENTORY_UUID}-licence.txt")
    assert licence in out and BAFU_CITATION in out
    assert "Run the command again with --accept-terms to accept them." in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert not data.exists()


def test_setup_bafu_refuses_an_unlisted_unlinked_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _bafu(tmp_path, monkeypatch)
    monkeypatch.setattr(
        bafu_setup, "read_background", importable(unlisted_input(a_process(tmp_path)))
    )
    code, _out, err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)

    assert code == 1 and json.loads(err)["error"] == "invalid"
    assert "a process takes an input and the unlinked list lacks it" in err
    assert not data.exists()


def test_a_second_setup_bafu_without_replace_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _bafu(tmp_path, monkeypatch)
    code, out, _err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)
    assert code == 0
    directory = Path(json.loads(out)["directory"])

    code, _out, err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)
    assert code == 1 and json.loads(err)["error"] == "conflict"
    assert (directory / "catalog.duckdb").is_file()

    code, out, err = _setup(
        ["bafu", "--data-dir", str(data), "--accept-terms", "--replace"], capsys
    )
    assert code == 0, err
    assert json.loads(out)["directory"] == str(directory)


def test_the_summary_names_no_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    credential = "a-value-the-summary-never-names"
    monkeypatch.setenv("NEXUS_PASSWORD", credential)
    data = _bafu(tmp_path, monkeypatch)
    code, out, err = _setup(["bafu", "--data-dir", str(data), "--accept-terms"], capsys)

    assert code == 0, err
    assert credential not in out and credential not in err


@pytest.mark.parametrize(
    "argv",
    [
        ["setup", "index", "--database", FIXTURE_DB],
        ["database", "export", "--database", FIXTURE_DB],
    ],
)
def test_index_and_export_are_not_commands(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 2


def test_setup_creates_a_data_directory_that_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "not" / "yet" / "data"
    code, out, _ = _setup(
        [
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(package),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
        ],
        capsys,
    )
    assert code == 0
    directory = Path(json.loads(out)["directory"])
    assert directory.is_dir() and directory.parent.parent == data


def test_setup_given_no_data_directory_installs_into_this_platform_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("ECOSEMANTIC_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    package = build_package(tmp_path / "fixture.zip")
    code, out, _ = _setup(
        ["openlca", "--package", str(package), "--name", NAME, "--version", "1", "--drop-unlinked"],
        capsys,
    )
    assert code == 0
    directory = Path(json.loads(out)["directory"])
    assert directory.parent.parent == tmp_path / "share" / "ecosemantic" / "data"


def test_serve_given_no_directories_serves_this_platform_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosemantic import cli as cli_module

    calls: list[object] = []

    async def fake_run(
        context: object, settings: object, systems_dir: object, meter_provider: object = None
    ) -> None:
        calls.append(systems_dir)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("ECOSEMANTIC_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(cli_module, "run", fake_run)
    assert main(["serve"]) == 0
    assert calls == [tmp_path / "share" / "ecosemantic" / "systems"]
    assert (tmp_path / "share" / "ecosemantic" / "data").is_dir()


def test_serve_no_open_turns_the_browser_off(
    bundle_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosemantic import cli as cli_module
    from ecosemantic.serve import ViewSettings, derived_port

    calls: list[object] = []

    async def fake_run(
        context: object, settings: object, systems_dir: object, meter_provider: object = None
    ) -> None:
        calls.append(settings)

    monkeypatch.setattr(cli_module, "run", fake_run)
    code = main(
        [
            "serve",
            "--data-dir",
            str(bundle_dir),
            "--systems-dir",
            str(tmp_path),
            "--no-open",
        ]
    )
    assert code == 0
    assert calls == [ViewSettings(port=derived_port(tmp_path), open=False)]


def test_serve_runs_the_stdio_server_off_the_network(
    bundle_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fastmcp

    from ecosemantic import cli as cli_module
    from ecosemantic.serve import ViewSettings, derived_port

    calls: list[tuple[object, object, object]] = []

    async def fake_run(
        context: object, settings: object, systems_dir: object, meter_provider: object = None
    ) -> None:
        calls.append((context, settings, systems_dir))

    monkeypatch.setattr(cli_module, "run", fake_run)
    monkeypatch.setattr(fastmcp.settings, "check_for_updates", "stable")
    monkeypatch.setattr(fastmcp.settings, "telemetry_mode", "native")
    assert main(["serve", "--data-dir", str(bundle_dir), "--systems-dir", str(tmp_path)]) == 0
    assert len(calls) == 1 and calls[0][1] == ViewSettings(port=derived_port(tmp_path))
    assert calls[0][2] == tmp_path
    assert fastmcp.settings.check_for_updates == "off"
    assert fastmcp.settings.telemetry_mode == "off"


def test_http_transport_without_a_view_is_refused(
    bundle_dir: Path, systems_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "serve",
            "--data-dir",
            str(bundle_dir),
            "--systems-dir",
            str(systems_dir),
            "--no-view",
            "--transport",
            "http",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "it needs the view on" in err


def test_serve_keeps_stdout_clear_while_it_opens_the_data(
    bundle_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ecosemantic import cli as cli_module

    opened = cli_module.build_context

    def noisy(data_dir: Path, systems_dir: Path, **named: object) -> object:
        print("opening the data")
        return opened(data_dir, systems_dir, **named)

    async def fake_run(
        context: object, settings: object, systems_dir: object, meter_provider: object = None
    ) -> None:
        print("the wire")

    monkeypatch.setattr(cli_module, "build_context", noisy)
    monkeypatch.setattr(cli_module, "run", fake_run)
    assert main(["serve", "--data-dir", str(bundle_dir), "--systems-dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    # the serving phase still owns stdout
    assert captured.out == "the wire\n"
    assert "opening the data" in captured.err


def test_serve_reports_data_it_will_not_open_as_a_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ecosemantic import cli as cli_module
    from ecosemantic.errors import Unavailable

    def refused(data_dir: Path, systems_dir: Path, **named: object) -> object:
        raise Unavailable("'fixture' is installed in entry format 2; this store reads format 1")

    monkeypatch.setattr(cli_module, "build_context", refused)
    assert main(["serve", "--data-dir", str(tmp_path), "--systems-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "'fixture' is installed in entry format 2; this store reads format 1" in err


def test_compute_writes_a_run_folder_from_a_folder_with_no_store(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = write_folder(tmp_path, fixture_system_stored)
    argv = [
        "compute",
        "--data-dir",
        str(bundle_dir),
        "--folder",
        str(folder),
        "--method",
        GWP_ID,
        "--json",
    ]
    assert main(argv) == 0
    answered = json.loads(capsys.readouterr().out)
    run = Path(answered["folder"])
    assert run.parent.name == "results"
    assert run.parent.parent == folder
    assert (run / "scores.csv").is_file()
    assert (run / "schema.yaml").is_file()
    assert answered["hash"] == content_hash(fixture_system_stored)


def test_compute_writes_the_other_two_tables_when_asked(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = write_folder(tmp_path, fixture_system_stored)
    argv = [
        "compute",
        "--data-dir",
        str(bundle_dir),
        "--folder",
        str(folder),
        "--method",
        GWP_ID,
        "--json",
        "--contributions",
        "--inventory",
    ]
    assert main(argv) == 0
    answered = json.loads(capsys.readouterr().out)
    assert len(answered["written"]) == 3
    assert any((Path(p) / "contributions.csv").is_file() for p in answered["written"])
    assert any((Path(p) / "inventory.csv").is_file() for p in answered["written"])


def test_compute_names_a_positive_input_to_a_treatment_in_every_table_it_writes(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def steel_treats(*_: object) -> frozenset[BackgroundRef]:
        # the fixture background holds no treatment, so steel stands for one
        return frozenset({BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])})

    monkeypatch.setattr("ecosemantic.cli.treatments_in", steel_treats)
    folder = write_folder(tmp_path, fixture_system_stored)
    argv = [
        "compute",
        "--data-dir",
        str(bundle_dir),
        "--folder",
        str(folder),
        "--method",
        GWP_ID,
        "--json",
    ]
    assert main([*argv, "--contributions", "--inventory"]) == 0
    written = json.loads(capsys.readouterr().out)["written"]
    named = ["frame · steel at 2.4", "widget · steel at 0.5"]
    for run in written:
        schema = yaml.safe_load((Path(run) / "schema.yaml").read_text())
        # the folder's document lists its processes in its own order
        assert sorted(schema["treatments_run_backwards"]) == named


def test_compute_scores_a_case_against_the_base(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    system = fixture_system_stored.model_copy(deep=True)
    system.process("widget").exchanges[2].formula = "elec_kwh"
    system.parameters = [Parameter(name="elec_kwh", value=1.0)]
    system.cases = [Case(name="half", values={"elec_kwh": 0.5})]
    folder = write_folder(tmp_path, system)
    argv = ["compute", "--data-dir", str(bundle_dir), "--folder", str(folder), "--json"]
    assert main([*argv, "--method", GWP_ID, "--variants", "half", "--json"]) == 0
    run = Path(json.loads(capsys.readouterr().out)["folder"])
    rows = (run / "scores.csv").read_text().splitlines()[1:]
    scores = {row.split(",")[0]: float(row.split(",")[5]) for row in rows}
    # electricity 1 kWh at 1.0 kg CO2-Eq, halved by the case
    assert scores[""] == pytest.approx(4.158)
    assert scores["half"] == pytest.approx(3.658)


def test_compute_names_every_refused_cell_in_the_error_it_prints(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    system = fixture_system_stored.model_copy(deep=True)
    system.process("widget").exchanges[2].formula = "elec_kwh"
    system.parameters = [Parameter(name="elec_kwh", value=1.0)]
    folder = write_folder(tmp_path, system)
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(path.read_text().replace("elec_kwh,1.0,", "elec_kwh,plenty,"), encoding="utf-8")
    argv = [
        "compute",
        "--data-dir",
        str(bundle_dir),
        "--folder",
        str(folder),
        "--method",
        GWP_ID,
        "--json",
    ]
    assert main(argv) == 1
    printed = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert printed["error"] == "invalid"
    assert [r["column"] for r in printed["details"]["refusals"]] == ["value"]


def test_compute_applies_a_scenario_while_the_folder_is_the_state_it_is_pinned_to(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    system = fixture_system_stored.model_copy(deep=True)
    system.process("widget").exchanges[2].formula = "elec_kwh"
    system.parameters = [Parameter(name="elec_kwh", value=1.0)]
    system, _ = add_scenario(
        system,
        name="half",
        description="half the electricity",
        overrides=[ParameterOverride(name="elec_kwh", value=0.5)],
    )
    folder = write_folder(tmp_path, system)
    argv = ["compute", "--data-dir", str(bundle_dir), "--folder", str(folder), "--json"]
    assert main([*argv, "--method", GWP_ID, "--variants", "half", "--json"]) == 0
    run = Path(json.loads(capsys.readouterr().out)["folder"])
    rows = (run / "scores.csv").read_text().splitlines()[1:]
    scores = {row.split(",")[0]: float(row.split(",")[5]) for row in rows}
    assert scores[""] == pytest.approx(4.158)
    assert scores["half"] == pytest.approx(3.658)
    # an edited input is another state, and the pin refuses it as the store does
    path = folder / "inputs" / "input_parameters.csv"
    path.write_text(path.read_text().replace("elec_kwh,1.0,", "elec_kwh,2.0,"), encoding="utf-8")
    assert main([*argv, "--method", GWP_ID, "--variants", "half", "--json"]) == 1
    printed = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "is pinned to" in printed["message"]
    # the remedy is a folder's, not the rebase_scenario tool a folder has no use for
    assert "export the folder again" in printed["message"]
    assert "run rebase_scenario first" not in printed["message"]
    assert printed["details"]["scenario"] == "half"


def test_save_release_and_load_through_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = build_package(tmp_path / "base.zip")
    data, systems = tmp_path / "bw", tmp_path / "systems"
    data.mkdir()
    assert (
        main(
            [
                "setup",
                "openlca",
                "--data-dir",
                str(data),
                "--package",
                str(base),
                "--name",
                BASE,
                "--version",
                "1",
                "--drop-unlinked",
            ]
        )
        == 0
    )
    storage = FilesystemStorage(systems, DictResolver(backgrounds(), flows()))
    casing = casing_system()
    asyncio.run(storage.put_product_system(casing, AGENT, "created"))
    capsys.readouterr()
    common = [
        "--data-dir",
        str(data),
        "--systems-dir",
        str(systems),
        "--base",
        BASE,
        "--version",
        "1",
        "--json",
    ]
    assert (
        main(["database", "release", *common, "--name", "rel", "--to", str(tmp_path / "rel.zip")])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["datasets"] == 4
    assert (
        main(["database", "save", *common, "--name", "work", "--to", str(tmp_path / "work.zip")])
        == 0
    )
    capsys.readouterr()
    other = tmp_path / "other"
    assert (
        main(
            [
                "database",
                "load",
                "--data-dir",
                str(data),
                "--systems-dir",
                str(other),
                "--from",
                str(tmp_path / "work.zip"),
                "--json",
            ]
        )
        == 0
    )
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["base"] == "kept" and loaded["systems"] == {str(casing.id): "added"}
    assert (
        main(
            [
                "database",
                "load",
                "--data-dir",
                str(data),
                "--systems-dir",
                str(tmp_path / "third"),
                "--from",
                str(tmp_path / "rel.zip"),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["database"] == "rel"


def test_a_workspace_loaded_empty_saves_its_systems_whole_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = build_package(tmp_path / "base.zip")
    data, systems = tmp_path / "bw", tmp_path / "systems"
    data.mkdir()
    setup = ["setup", "openlca", "--data-dir", str(data), "--package", str(base)]
    assert main([*setup, "--name", BASE, "--version", "1", "--drop-unlinked"]) == 0
    storage = FilesystemStorage(systems, DictResolver(backgrounds(), flows()))
    casing = casing_system()
    asyncio.run(storage.put_product_system(casing, AGENT, "created"))
    first = tmp_path / "first.zip"
    common = ["--base", BASE, "--version", "1", "--name", "work"]
    assert (
        main(
            [
                "database",
                "save",
                "--data-dir",
                str(data),
                "--systems-dir",
                str(systems),
                *common,
                "--to",
                str(first),
            ]
        )
        == 0
    )
    fresh, elsewhere = tmp_path / "fresh", tmp_path / "elsewhere"
    fresh.mkdir()
    assert (
        main(
            [
                "database",
                "load",
                "--data-dir",
                str(fresh),
                "--systems-dir",
                str(elsewhere),
                "--from",
                str(first),
            ]
        )
        == 0
    )
    capsys.readouterr()
    second = tmp_path / "second.zip"
    assert (
        main(
            [
                "database",
                "save",
                "--data-dir",
                str(fresh),
                "--systems-dir",
                str(elsewhere),
                *common,
                "--to",
                str(second),
            ]
        )
        == 0
    )
    owned = {f"processes/{p.id}.json" for p in casing.processes} | {
        f"product_systems/{casing.id}.json"
    }
    with zipfile.ZipFile(second) as zipped:
        assert owned <= set(zipped.namelist())


def _working(tmp_path: Path) -> Path:
    base = build_package(tmp_path / "base.zip")
    data, systems = tmp_path / "bw", tmp_path / "systems"
    data.mkdir()
    setup = ["setup", "openlca", "--data-dir", str(data), "--package", str(base)]
    assert main([*setup, "--name", BASE, "--version", "1", "--drop-unlinked"]) == 0
    storage = FilesystemStorage(systems, DictResolver(backgrounds(), flows()))
    asyncio.run(storage.put_product_system(casing_system(), AGENT, "created"))
    bundle = tmp_path / "work.zip"
    common = ["--base", BASE, "--version", "1", "--name", "work", "--to", str(bundle)]
    assert (
        main(["database", "save", "--data-dir", str(data), "--systems-dir", str(systems), *common])
        == 0
    )
    return bundle


def _held(tmp_path: Path, package: Path, version: str) -> Path:
    data = tmp_path / f"held-{version}"
    data.mkdir()
    setup = ["setup", "openlca", "--data-dir", str(data), "--package", str(package)]
    assert main([*setup, "--name", BASE, "--version", version, "--drop-unlinked"]) == 0
    return data


def _load(data: Path, bundle: Path, tmp_path: Path) -> int:
    systems = tmp_path / f"systems-{data.name}"
    return main(
        [
            "database",
            "load",
            "--data-dir",
            str(data),
            "--systems-dir",
            str(systems),
            "--from",
            str(bundle),
            "--json",
        ]
    )


def test_a_held_base_of_another_version_refuses_the_load(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _working(tmp_path)
    data = _held(tmp_path, tmp_path / "base.zip", "2")
    capsys.readouterr()
    assert _load(data, bundle, tmp_path) == 1
    refused = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert (
        refused["error"] == "conflict"
        and "'1'" in refused["message"]
        and "'2'" in refused["message"]
    )


def test_a_held_base_lacking_processes_refuses_the_load(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _working(tmp_path)
    partial = tmp_path / "partial.zip"
    with zipfile.ZipFile(tmp_path / "base.zip") as src, zipfile.ZipFile(partial, "w") as dst:
        for member in src.namelist():
            if member != f"processes/{OPENLCA_PROCESSES['elec']}.json":
                dst.writestr(member, src.read(member))
    data = _held(tmp_path, partial, "1")
    capsys.readouterr()
    assert _load(data, bundle, tmp_path) == 1
    refused = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert refused["error"] == "conflict" and "lacks 1 processes" in refused["message"]


def test_a_held_base_of_another_build_refuses_the_load(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _working(tmp_path)
    store = NativeStore(tmp_path / "bw")
    built_on = store.registered(BASE).database.fingerprint
    store.close()
    assert built_on is not None and read_manifest(bundle).base.fingerprint == built_on
    other = tmp_path / "other.zip"
    steel = f"processes/{OPENLCA_PROCESSES['steel']}.json"
    with zipfile.ZipFile(tmp_path / "base.zip") as src, zipfile.ZipFile(other, "w") as dst:
        for member in src.namelist():
            data = src.read(member)
            if member == steel:
                doc = json.loads(data)
                used = next(e for e in doc["exchanges"] if not e.get("isQuantitativeReference"))
                # one amount doubled is another build of the same version
                used["amount"] *= 2
                data = json.dumps(doc).encode()
            dst.writestr(member, data)
    data = _held(tmp_path, other, "1")
    capsys.readouterr()
    assert _load(data, bundle, tmp_path) == 1
    refused = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert refused["error"] == "conflict"
    assert f"the bundle was built on build {built_on[:12]}" in refused["message"]


def test_setup_answers_in_text_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "data"
    data.mkdir()
    code, out, _err = _setup(
        [
            "openlca",
            "--data-dir",
            str(data),
            "--package",
            str(package),
            "--name",
            NAME,
            "--version",
            "1",
            "--drop-unlinked",
        ],
        capsys,
        as_json=False,
    )
    assert code == 0
    assert "Ask your chatbot for a model on" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


@pytest.mark.parametrize(
    "argv",
    [
        ["serve"],
        ["export"],
        ["import"],
        ["compute"],
        ["setup", "openlca"],
        ["setup", "uslci"],
        ["setup", "bafu"],
        ["database", "save"],
        ["database", "release"],
        ["database", "load"],
        ["connect"],
        ["doctor"],
        ["init"],
    ],
)
def test_every_command_but_serve_takes_json(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main([*argv, "--help"])
    assert raised.value.code == 0
    helped = capsys.readouterr().out
    assert ("--json" in helped) is (argv[0] != "serve")


def test_a_refusal_is_text_on_stderr_and_json_under_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    data = tmp_path / "data"
    data.mkdir()
    argv = [
        "setup",
        "openlca",
        "--data-dir",
        str(data),
        "--package",
        str(package),
        "--name",
        NAME,
        "--version",
        "1",
        "--drop-unlinked",
    ]
    assert main(argv) == 0
    capsys.readouterr()
    assert main(argv) == 1
    err = capsys.readouterr().err.strip().splitlines()[-1]
    assert err.startswith("error: ") and "conflict" not in err
    assert main([*argv, "--json"]) == 1
    refused = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert refused["error"] == "conflict"


def test_compute_answers_in_text_by_default(
    fixture_system_stored: ProductSystem,
    bundle_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder = write_folder(tmp_path, fixture_system_stored)
    argv = ["compute", "--data-dir", str(bundle_dir), "--folder", str(folder), "--method", GWP_ID]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert out.startswith("wrote ") and GWP_ID in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def _macos_writing_into(command: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read this machine as macOS, where both chatbots document a folder, and write the command at
    hand instead of the installed one."""
    monkeypatch.setattr("ecosemantic.cli.clients.sys.platform", "darwin")
    monkeypatch.setattr("ecosemantic.cli.clients.installed_command", lambda: command)


def _chatbots(home: Path) -> None:
    """The folders Claude Desktop and Cursor keep on macOS."""
    (home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
    (home / ".cursor").mkdir()


def test_init_connects_each_chatbot_found_and_ends_with_the_next_step(
    home: Path, command: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _macos_writing_into(command, monkeypatch)
    claude = home / "Library" / "Application Support" / "Claude"
    claude.mkdir(parents=True)
    code = main(["init", "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    answer = json.loads(captured.out)
    config = claude / "claude_desktop_config.json"
    assert answer["connected"] == [
        {
            "client": "claude-desktop",
            "path": str(config),
            "server": SERVER,
            "command": str(command),
            "replaced": False,
        }
    ]
    assert answer["next"] == "Restart your chatbot; the EcoSemantic page opens in your browser."
    assert answer["doctor"]["clients"]["claude-desktop"]["present"] is True
    assert json.loads(config.read_text())["mcpServers"][SERVER]["command"] == str(command)
    assert not (home / ".cursor" / "mcp.json").exists()


def test_init_with_no_chatbot_names_claude_desktop_s_download_and_exits_1(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("ecosemantic.cli.clients.sys.platform", "darwin")
    assert main(["init", "--json"]) == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"] == "unavailable"
    assert payload["message"] == "no chatbot is installed"
    assert payload["details"]["hint"] == (
        "install Claude Desktop from https://claude.ai/download, then run: ecosemantic init"
    )


def test_init_asks_which_to_connect_when_several_are_found_on_a_terminal(
    home: Path, command: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _macos_writing_into(command, monkeypatch)
    _chatbots(home)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    # an answer outside the choices asks again; the second names Claude Desktop
    answers = iter(["9", "1"])
    monkeypatch.setattr("builtins.input", lambda *_args: next(answers))
    code = main(["init", "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    answer = json.loads(captured.out)
    assert [item["client"] for item in answer["connected"]] == ["claude-desktop"]
    assert "1. claude-desktop" in captured.err and "all" in captured.err
    assert not (home / ".cursor" / "mcp.json").exists()


def test_init_connects_every_one_found_off_a_terminal(
    home: Path, command: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _macos_writing_into(command, monkeypatch)
    _chatbots(home)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    code = main(["init", "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    answer = json.loads(captured.out)
    assert [item["client"] for item in answer["connected"]] == ["claude-desktop", "cursor"]
    assert (home / ".cursor" / "mcp.json").is_file()


def test_init_connects_every_chatbot_when_the_person_answers_all(
    home: Path, command: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _macos_writing_into(command, monkeypatch)
    _chatbots(home)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_args: "all")
    code = main(["init", "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    answer = json.loads(captured.out)
    assert [item["client"] for item in answer["connected"]] == ["claude-desktop", "cursor"]


def served_with_telemetry(
    bundle_dir: Path, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, list[object], list[object]]:
    from ecosemantic import cli as cli_module
    from ecosemantic import telemetry

    given: list[object] = []
    ended: list[object] = []

    async def fake_run(
        context: object, settings: object, systems_dir: object, meter_provider: object = None
    ) -> None:
        given.append(meter_provider)
        assert not ended

    def stop(provider: object) -> None:
        ended.append(provider)

    monkeypatch.setattr(cli_module, "run", fake_run)
    monkeypatch.setattr(telemetry, "end", stop)
    code = main(["serve", "--data-dir", str(bundle_dir), "--systems-dir", str(folder)])
    return code, given, ended


def test_serve_with_telemetry_off_hands_no_provider(
    bundle_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, given, ended = served_with_telemetry(bundle_dir, tmp_path, monkeypatch)
    assert code == 0
    assert given == [None] and ended == []
    assert not (bundle_dir / "telemetry.json").exists()


def test_serve_with_telemetry_on_counts_a_start_and_shuts_down(
    bundle_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    from ecosemantic import cli as cli_module
    from ecosemantic.telemetry import STARTS, begin

    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY", "on")
    reader = InMemoryMetricReader()
    monkeypatch.setattr(
        cli_module,
        "begin",
        lambda environ, data_dir, transport, stream: begin(
            environ, data_dir, transport, stream, reader
        ),
    )
    data = copied_data(bundle_dir, tmp_path)
    code, given, ended = served_with_telemetry(data, tmp_path, monkeypatch)
    assert code == 0
    assert len(given) == 1 and given[0] is not None
    assert ended == given
    names = [
        metric.name
        for resource in reader.get_metrics_data().resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    ]
    assert names == [STARTS]


def copied_data(bundle_dir: Path, tmp_path: Path) -> Path:
    import shutil

    return shutil.copytree(bundle_dir, tmp_path / "data")


def test_serve_with_telemetry_on_writes_nothing_to_stdout(
    bundle_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ecosemantic.telemetry import NOTICE

    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY", "on")
    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY_ENDPOINT", "http://127.0.0.1:9/v1/metrics")
    data = copied_data(bundle_dir, tmp_path)
    code, given, _ = served_with_telemetry(data, tmp_path, monkeypatch)
    for provider in given:
        provider.shutdown()
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert NOTICE in captured.err


def test_the_command_records_and_reads_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    assert main(["telemetry", "off", "--data-dir", str(tmp_path), "--json"]) == 0
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["on"] is False and recorded["reason"] == "telemetry.json"
    assert main(["telemetry", "--data-dir", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == recorded
    assert recorded["install_id"] is None
    assert json.loads((tmp_path / "telemetry.json").read_text()) == {"choice": "off"}


def test_the_command_says_the_choice_applies_at_the_next_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["telemetry", "off", "--data-dir", str(tmp_path)]) == 0
    assert "servers started after it" in capsys.readouterr().out


def test_doctor_reports_telemetry(tmp_path: Path) -> None:
    from ecosemantic.cli.doctor import report
    from ecosemantic.cli.text import doctor_text

    made = report(tmp_path, tmp_path, [])
    assert made["telemetry"]["on"] is False
    assert "ECOSEMANTIC_TELEMETRY" in doctor_text(made)


def test_doctor_and_init_say_what_is_counted_and_how_to_stop_it_when_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosemantic.cli.doctor import report
    from ecosemantic.cli.text import doctor_text, init_text
    from ecosemantic.telemetry import NOTICE

    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    made = report(tmp_path, tmp_path, [])
    assert made["telemetry"]["on"] is True
    assert NOTICE in doctor_text(made)
    assert NOTICE in init_text({"connected": [], "doctor": made, "next": "next"})
    assert "ecosemantic telemetry off" in NOTICE
    assert "https://github.com/cdgaete/ecosemantic/blob/main/TELEMETRY.md" in NOTICE


def test_doctor_does_not_tell_what_is_counted_when_off(tmp_path: Path) -> None:
    from ecosemantic.cli.doctor import report
    from ecosemantic.cli.text import doctor_text
    from ecosemantic.telemetry import NOTICE

    assert NOTICE not in doctor_text(report(tmp_path, tmp_path, []))


def test_doctor_names_a_broken_telemetry_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosemantic.cli.doctor import report
    from ecosemantic.cli.text import doctor_text

    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    (tmp_path / "telemetry.json").write_text("{")
    made = report(tmp_path, tmp_path, [])
    assert "error" in made["telemetry"]
    assert "telemetry.json" in doctor_text(made)


def test_the_command_refuses_a_mistyped_switch_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ECOSEMANTIC_TELEMETRY", "no")
    assert main(["telemetry", "off", "--data-dir", str(tmp_path)]) == 1
    assert "ECOSEMANTIC_TELEMETRY" in capsys.readouterr().err
    assert not (tmp_path / "telemetry.json").exists()


@pytest.mark.parametrize(
    ("variable", "value"), [("ECOSEMANTIC_TELEMETRY", "off"), ("DO_NOT_TRACK", "1")]
)
def test_a_variable_that_decides_is_said_to_reach_only_this_environment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    monkeypatch.setenv(variable, value)
    assert main(["telemetry", "--data-dir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert f"off ({variable})" in printed
    assert "servers started with this environment" in printed
    assert "`ecosemantic telemetry off`" in printed
    assert "every server on this machine" in printed


def test_the_recorded_choice_is_not_said_to_reach_only_this_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    assert main(["telemetry", "off", "--data-dir", str(tmp_path)]) == 0
    assert "this environment" not in capsys.readouterr().out


def test_doctor_names_a_telemetry_file_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosemantic.cli.doctor import report

    monkeypatch.delenv("ECOSEMANTIC_TELEMETRY")
    (tmp_path / "telemetry.json").mkdir()
    made = report(tmp_path, tmp_path, [])
    assert "telemetry.json" in made["telemetry"]["error"]
