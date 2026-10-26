from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import cast

import pytest
from ecoinvent_interface import EcoinventRelease

from ecosemantic.compute.accounts import missing
from ecosemantic.databases.bafu import profile as bafu_profile
from ecosemantic.databases.bafu import setup as bafu_setup
from ecosemantic.databases.ecoinvent.download import ReleaseClient
from ecosemantic.databases.ecoinvent.profile import Profile, pinned
from ecosemantic.databases.ecoinvent.release import SystemModel
from ecosemantic.databases.ecoinvent.setup import Prepared
from ecosemantic.databases.ecoinvent.validate import Validation
from ecosemantic.errors import Unavailable
from ecosemantic.installs import sources
from ecosemantic.installs.sources import install_source
from ecosemantic.package.background import read_background
from ecosemantic.ports.types import (
    Account,
    InstallDraft,
    InstallProgress,
    InstallTerms,
    Reporter,
)
from tests.databases.bafu.test_download import CITATION as BAFU_CITATION
from tests.databases.bafu.test_download import INVENTORY_UUID as BAFU_INVENTORY_UUID
from tests.databases.bafu.test_setup import fixture_release
from tests.databases.bafu.test_setup import session_for as bafu_session
from tests.engine_fixture import served_build
from tests.openlca_fixture import NAME, build_package
from tests.package.conftest import AGENT


def _quiet(_progress: InstallProgress) -> None:
    return None


def _openlca(tmp_path: Path) -> InstallDraft:
    return InstallDraft(
        source="openlca",
        actor=AGENT,
        version="1",
        system_model="unit process",
        package=str(build_package(tmp_path / "fixture.zip")),
        name=NAME,
        drop_unlinked=True,
    )


def test_install_source_installs_the_fixture_package_and_answers_its_summary(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    data.mkdir()

    summary = install_source(data, _openlca(tmp_path), None, _quiet)

    assert isinstance(summary, dict)
    assert summary["database"] == NAME
    assert summary["datasets"] == 6
    assert summary["dropped"] == 1
    assert (served_build(Path(str(summary["directory"]))) / "catalog.duckdb").is_file()


def test_install_source_reports_installing_last(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    steps: list[InstallProgress] = []

    install_source(data, _openlca(tmp_path), None, steps.append)

    assert [progress.step for progress in steps][-1] == "installing"


def test_a_source_that_needs_an_account_without_one_is_refused_naming_the_variables_and_the_page(
    tmp_path: Path,
) -> None:
    draft = InstallDraft(source="ecoinvent", actor=AGENT, version="3.12", system_model="cutoff")

    with pytest.raises(Unavailable) as raised:
        install_source(tmp_path / "data", draft, None, _quiet)

    assert str(raised.value) == "ecoinvent needs an account"
    assert raised.value.hint == missing("ecoinvent")
    assert "EI_USERNAME and EI_PASSWORD" in (raised.value.hint or "")
    assert "Databases editor" in (raised.value.hint or "")
    assert not (tmp_path / "data").exists()


def test_bafu_without_accept_terms_answers_its_terms_and_installs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _profile, recorded = fixture_release(tmp_path)
    monkeypatch.setattr(bafu_profile, "RELEASES", recorded)
    monkeypatch.setattr(bafu_setup, "NexusSession", bafu_session(server))
    data = tmp_path / "data"
    draft = InstallDraft(source="bafu", actor=AGENT)

    answer = install_source(data, draft, Account(username="u", password="p"), _quiet)

    assert answer == InstallTerms(
        licence=str(tmp_path / "downloads" / f"{BAFU_INVENTORY_UUID}-licence.txt"),
        citation=BAFU_CITATION,
    )
    assert not data.exists()
    assert list((tmp_path / "downloads").glob("*.zip")) == []


def test_ecoinvent_installs_the_release_a_profile_pins_with_the_account_s_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_package(tmp_path / "fixture.zip")
    imported = dataclasses.replace(
        read_background(package, NAME, foreground=frozenset()), unlinked=[]
    )
    prepared = Prepared(
        bundle=package,
        imported=imported,
        name="ecoinvent-3.12-cutoff",
        validation=Validation(
            counts={},
            largest_rel_diff={},
            mismatches=[],
            unreferenced=[],
            seconds={},
            saved_bytes=0,
        ),
    )
    asked: dict[str, object] = {}

    def prepare(
        version: str,
        system_model: SystemModel,
        client: ReleaseClient,
        profile: Profile,
        work: Path,
        report: Reporter,
    ) -> Prepared:
        logged_in = cast(EcoinventRelease, client)
        asked.update(
            version=version,
            system_model=system_model,
            profile=profile,
            account=(logged_in.username, logged_in.password),
        )
        return prepared

    monkeypatch.setattr(sources, "prepare_ecoinvent", prepare)
    data = tmp_path / "data"
    data.mkdir()
    draft = InstallDraft(source="ecoinvent", actor=AGENT, version="3.12", system_model="cutoff")

    summary = install_source(data, draft, Account(username="someone", password="secret"), _quiet)

    assert asked == {
        "version": "3.12",
        "system_model": "cutoff",
        "profile": pinned("3.12", "cutoff"),
        "account": ("someone", "secret"),
    }
    assert isinstance(summary, dict) and summary["database"] == NAME
    assert (served_build(Path(str(summary["directory"]))) / "catalog.duckdb").is_file()
