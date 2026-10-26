from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.installs import (
    FilesystemInstalls,
    install_dir,
    uploads_dir,
)
from ecosemantic.backends.filesystem.run_folder import HEARTBEAT_FILE, LOG_FILE, beat
from ecosemantic.databases.bafu.profile import versions as bafu_versions
from ecosemantic.databases.ecoinvent.profile import profiled
from ecosemantic.databases.uslci.profile import versions as uslci_versions
from ecosemantic.installs.handover import encoded
from ecosemantic.installs.supervisor import LocalInstaller
from ecosemantic.ports.types import STALE_SECONDS, Account, InstallDraft
from tests.openlca_fixture import NAME, build_package
from tests.package.conftest import AGENT


def test_sources_lists_the_four_sources_with_their_profiled_versions(tmp_path: Path) -> None:
    listed = LocalInstaller(tmp_path).sources()
    sources = {source.name: source for source in listed}
    releases = profiled()

    assert [source.name for source in listed] == ["openlca", "uslci", "bafu", "ecoinvent"]
    assert sources["openlca"].versions == []
    assert sources["openlca"].system_models == ["unit process"]
    assert sources["openlca"].credential is None and sources["openlca"].terms is False
    assert sources["uslci"].versions == list(uslci_versions())
    assert sources["uslci"].credential is None and sources["uslci"].terms is False
    assert sources["bafu"].versions == list(bafu_versions())
    assert sources["bafu"].credential == "nexus" and sources["bafu"].terms is True
    assert set(sources["ecoinvent"].versions) == {version for version, _ in releases}
    assert set(sources["ecoinvent"].system_models) == {model for _, model in releases}
    assert sources["ecoinvent"].credential == "ecoinvent"
    assert sources["ecoinvent"].terms is False


def test_the_install_process_starts_without_the_credential_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def start_detached(
        command: list[str],
        log: Path,
        stdin: bytes | None = None,
        environment: dict[str, str] | None = None,
    ) -> int:
        seen.update(command=command, log=log, stdin=stdin, environment=environment)
        return 4242

    monkeypatch.setattr("ecosemantic.installs.supervisor.start_detached", start_detached)
    monkeypatch.setenv("EI_PASSWORD", "hunter2-secret")
    monkeypatch.setenv("NEXUS_TOKEN", "654321")
    account = Account(username="someone", password="hunter2-secret")
    install_id = uuid.uuid4()

    pid = LocalInstaller(tmp_path).start(install_id, account)

    assert pid == 4242
    assert seen["command"] == [
        sys.executable,
        "-m",
        "ecosemantic.installs.worker",
        "--data-dir",
        str(tmp_path),
        "--install",
        str(install_id),
    ]
    assert seen["log"] == install_dir(tmp_path, install_id) / LOG_FILE
    assert seen["stdin"] == encoded(account)
    environment = seen["environment"]
    assert isinstance(environment, dict)
    assert "EI_PASSWORD" not in environment and "NEXUS_TOKEN" not in environment
    assert not [name for name in environment if name.startswith(("EI_", "NEXUS_"))]


def test_an_install_with_no_account_still_gets_a_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def start_detached(command: list[str], log: Path, **kwargs: object) -> int:
        seen.update(kwargs)
        return 4242

    monkeypatch.setattr("ecosemantic.installs.supervisor.start_detached", start_detached)

    LocalInstaller(tmp_path).start(uuid.uuid4(), None)

    assert seen["stdin"] == b""


def test_an_install_is_alive_while_its_heartbeat_is_fresh(tmp_path: Path) -> None:
    install_id = uuid.uuid4()
    installer = LocalInstaller(tmp_path)
    assert installer.alive(install_id) is False
    folder = install_dir(tmp_path, install_id)
    folder.mkdir(parents=True)
    beat(folder)
    assert installer.alive(install_id) is True
    stale = time.time() - STALE_SECONDS - 1
    os.utime(folder / HEARTBEAT_FILE, (stale, stale))
    assert installer.alive(install_id) is False


async def test_a_started_install_process_carries_the_install_in_the_data_directory(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    uploads_dir(data).mkdir(parents=True)
    installs = FilesystemInstalls(data)
    posted = await installs.post_install(
        InstallDraft(
            source="openlca",
            actor=AGENT,
            version="1",
            system_model="unit process",
            package=str(build_package(uploads_dir(data) / "fixture.zip")),
            name=NAME,
            drop_unlinked=True,
        )
    )
    account = Account(username="someone", password="hunter2-secret")

    pid = LocalInstaller(data).start(posted.id, account)

    assert pid > 0
    deadline = time.monotonic() + 120
    record = installs.read_record(posted.id)
    while record.open and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        record = installs.read_record(posted.id)
    assert record.status == "done" and record.summary is not None
    assert "hunter2-secret" not in (install_dir(data, posted.id) / LOG_FILE).read_text()
    assert list(uploads_dir(data).iterdir()) == []
