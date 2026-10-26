from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import JsonValue

from ecosemantic.backends.filesystem.installs import (
    INSTALL_FILE,
    FilesystemInstalls,
    install_dir,
    uploads_dir,
)
from ecosemantic.backends.filesystem.run_folder import (
    HEARTBEAT_FILE,
    LOG_FILE,
    beating,
    heartbeat_age,
)
from ecosemantic.databases.bafu import profile as bafu_profile
from ecosemantic.databases.bafu import setup as bafu_setup
from ecosemantic.errors import Unavailable, failure_payload
from ecosemantic.installs import worker
from ecosemantic.installs.handover import encoded
from ecosemantic.installs.worker import carry
from ecosemantic.ports.types import (
    Account,
    InstallDraft,
    InstallPatch,
    InstallTerms,
    Reporter,
)
from tests.databases.bafu.test_download import CITATION as BAFU_CITATION
from tests.databases.bafu.test_download import LICENCE_FILE as BAFU_LICENCE_FILE
from tests.databases.bafu.test_setup import fixture_release
from tests.databases.bafu.test_setup import session_for as bafu_session
from tests.openlca_fixture import NAME, build_package
from tests.package.conftest import AGENT


def _openlca(package: Path) -> InstallDraft:
    """The fixture package as an install of it from openLCA."""
    return InstallDraft(
        source="openlca",
        actor=AGENT,
        version="1",
        system_model="unit process",
        package=str(package),
        name=NAME,
        drop_unlinked=True,
    )


async def test_an_install_carried_to_done_writes_its_summary_and_beats(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "done"
    assert record.summary is not None and record.summary["database"] == NAME
    assert record.started_at is not None and record.finished_at is not None
    assert (install_dir(data, posted.id) / HEARTBEAT_FILE).is_file()


async def test_a_finished_install_counts_its_unlinked_inputs_and_keeps_their_rows_beside_the_record(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.summary is not None
    assert record.summary["unlinked"] == 1
    path = install_dir(data, posted.id) / "unlinked.json"
    assert record.summary["unlinked_file"] == str(path)
    rows = json.loads(path.read_text())
    assert isinstance(rows, list) and len(rows) == 1
    assert rows[0]["process"] == "widget production"


async def test_an_install_with_no_unlinked_inputs_counts_none_and_keeps_an_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    def install_source(*_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        return {"database": NAME, "unlinked": []}

    monkeypatch.setattr(worker, "install_source", install_source)

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "done" and record.summary is not None
    assert record.summary["unlinked"] == 0
    path = install_dir(data, posted.id) / "unlinked.json"
    assert record.summary["unlinked_file"] == str(path)
    assert json.loads(path.read_text()) == []


async def test_a_record_holds_no_list_of_its_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))
    unlinked = [{"process": "widget production", "reason": "names no uuid"}]
    notices = [{"text": "first", "datasets": 2}, {"text": "second", "datasets": 1}]
    sources = [{"name": "uslci", "version": "1.0"}]

    def install_source(*_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        return {
            "database": NAME,
            "unlinked": unlinked,
            "notices": notices,
            "sources": sources,
        }

    monkeypatch.setattr(worker, "install_source", install_source)

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "done" and record.summary is not None
    summary = record.summary
    assert not any(isinstance(value, list) for value in summary.values())
    assert summary["database"] == NAME
    folder = install_dir(data, posted.id)
    for name, rows in (("unlinked", unlinked), ("notices", notices), ("sources", sources)):
        path = folder / f"{name}.json"
        assert summary[name] == len(rows)
        assert summary[f"{name}_file"] == str(path)
        assert json.loads(path.read_text()) == rows


async def test_a_summary_without_a_list_writes_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    def install_source(*_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        return {"database": NAME}

    monkeypatch.setattr(worker, "install_source", install_source)

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "done"
    assert record.summary == {"database": NAME}
    folder = install_dir(data, posted.id)
    assert [path.name for path in folder.glob("*.json")] == [INSTALL_FILE]


async def test_a_cancel_asked_before_installing_ends_cancelled_and_installs_nothing(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))
    await installs.cancel_install(posted.id)

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "cancelled"
    assert record.summary is None and record.terms is None and record.error is None
    assert [path.name for path in data.iterdir()] == ["installs"]
    assert (install_dir(data, posted.id) / HEARTBEAT_FILE).is_file()


async def test_a_bafu_draft_without_its_terms_ends_terms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _profile, recorded = fixture_release(tmp_path)
    monkeypatch.setattr(bafu_profile, "RELEASES", recorded)
    monkeypatch.setattr(bafu_setup, "NexusSession", bafu_session(server))
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(InstallDraft(source="bafu", actor=AGENT))

    carry(data, posted.id, Account(username="u", password="p"))

    record = installs.read_record(posted.id)
    assert record.status == "terms"
    assert record.terms == InstallTerms(
        licence=str(tmp_path / "downloads" / BAFU_LICENCE_FILE), citation=BAFU_CITATION
    )
    assert record.summary is None


async def test_a_refused_login_leaves_the_password_in_no_record_and_no_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(InstallDraft(source="bafu", actor=AGENT))
    account = Account(username="someone", password="hunter2-secret")

    def refuse(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise Unavailable("login refused")

    monkeypatch.setattr(worker, "install_source", refuse)
    folder = install_dir(data, posted.id)
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / LOG_FILE
    with log.open("w") as written, redirect_stdout(written), redirect_stderr(written):
        carry(data, posted.id, account)

    record = installs.read_record(posted.id)
    assert record.status == "failed"
    assert record.error is not None and record.error.message == "login refused"
    assert "hunter2-secret" not in (folder / INSTALL_FILE).read_text()
    assert "hunter2-secret" not in log.read_text()


async def test_a_failure_that_is_no_typed_error_is_recorded_and_raised_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    def crash(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("the process fell over")

    monkeypatch.setattr(worker, "install_source", crash)

    with pytest.raises(RuntimeError, match="the process fell over"):
        carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "failed"
    assert record.error == failure_payload("the process fell over")


async def test_an_uploaded_package_is_deleted_when_the_install_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    uploads_dir(data).mkdir(parents=True)
    installs = FilesystemInstalls(data)
    finished = await installs.post_install(_openlca(build_package(uploads_dir(data) / "one.zip")))

    carry(data, finished.id, None)

    assert installs.read_record(finished.id).status == "done"
    assert list(uploads_dir(data).iterdir()) == []

    def refuse(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise Unavailable("login refused")

    monkeypatch.setattr(worker, "install_source", refuse)
    failed = await installs.post_install(_openlca(build_package(uploads_dir(data) / "two.zip")))

    carry(data, failed.id, None)

    assert installs.read_record(failed.id).status == "failed"
    assert list(uploads_dir(data).iterdir()) == []


def test_the_module_runs_as_a_subprocess() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "ecosemantic.installs.worker", "--help"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0 and "--install" in out.stdout


def test_main_refuses_without_its_arguments() -> None:
    try:
        worker.main([])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("main accepted no arguments")


async def test_main_carries_the_install_named_and_reads_the_account_from_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))
    account = Account(username="someone", password="hunter2-secret")
    seen: dict[str, object] = {}

    def install_source(
        data_dir: Path,
        draft: InstallDraft,
        given: Account | None,
        report: Reporter,
    ) -> dict[str, JsonValue]:
        seen.update(data_dir=data_dir, draft=draft, account=given)
        return {"database": NAME, "unlinked": []}

    monkeypatch.setattr(worker, "install_source", install_source)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(encoded(account))))

    assert worker.main(["--data-dir", str(data), "--install", str(posted.id)]) == 0

    assert seen["data_dir"] == data and seen["account"] == account
    record = installs.read_record(posted.id)
    assert record.status == "done"
    assert record.summary == {
        "database": NAME,
        "unlinked": 0,
        "unlinked_file": str(install_dir(data, posted.id) / "unlinked.json"),
    }


def test_beating_keeps_the_heartbeat_fresh_while_the_block_runs(tmp_path: Path) -> None:
    folder = tmp_path / "install"
    folder.mkdir()
    before = set(threading.enumerate())

    # a beat every 0.05 s keeps the age far below the 0.6 s the block lasts
    with beating(folder, 0.05):
        time.sleep(0.6)
        fresh = heartbeat_age(folder)
        assert fresh is not None and fresh < 0.3

    assert not set(threading.enumerate()) - before


async def test_an_install_whose_step_reports_nothing_past_the_stale_time_stays_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))
    folder = install_dir(data, posted.id)
    period = 0.05
    ages: list[float] = []
    reading = threading.Event()

    def install_source(*_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        reading.set()
        time.sleep(period * 20)
        return {"database": NAME}

    def read() -> None:
        reading.wait()
        while reading.is_set():
            age = heartbeat_age(folder)
            if age is not None:
                ages.append(age)
            time.sleep(period / 4)

    monkeypatch.setattr(worker, "BEAT_SECONDS", period)
    monkeypatch.setattr(worker, "install_source", install_source)
    reader = threading.Thread(target=read)
    reader.start()
    try:
        carry(data, posted.id, None)
    finally:
        reading.clear()
        reader.join()

    # without the beat the age reaches the silent step's 1 s; with it, a few beats at most
    assert ages and max(ages) < period * 6
    assert installs.read_record(posted.id).status == "done"


async def test_a_finished_install_carries_no_error_a_reaper_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(_openlca(build_package(tmp_path / "fixture.zip")))

    def install_source(data_dir: Path, *_args: object, **_kwargs: object) -> dict[str, JsonValue]:
        FilesystemInstalls(data_dir).apply_patch(
            posted.id,
            InstallPatch(
                status="failed",
                error=failure_payload(f"the process for install {posted.id} did not finish"),
                finished_at=datetime.now(UTC),
            ),
        )
        return {"database": NAME}

    monkeypatch.setattr(worker, "install_source", install_source)

    carry(data, posted.id, None)

    record = installs.read_record(posted.id)
    assert record.status == "done"
    assert record.error is None
