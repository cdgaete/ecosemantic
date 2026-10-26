"""What a BAFU release prepares for an install held to its profile, and what its bundle holds and
the core does not apply."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from ecosemantic.databases.bafu import profile as bafu_profile
from ecosemantic.databases.bafu import setup as bafu_setup
from ecosemantic.databases.bafu.build import build
from ecosemantic.databases.bafu.profile import Profile
from ecosemantic.databases.bafu.setup import NotApplied, not_applied, prepare
from ecosemantic.databases.lists import UnlinkedRow, write_unlinked
from ecosemantic.errors import Invalid
from ecosemantic.package.background import Import, Unlinked, read_background
from ecosemantic.ports.types import Account, InstallProgress
from tests.databases.bafu.test_download import (
    CITATION,
    INVENTORY_UUID,
    LICENCE_FILE,
    StubNexus,
    pinned_profile,
)
from tests.databases.zolca.fixture import FIXTURES

VERSION = "2026-v1"
ZOLCA = FIXTURES / "openlca.zip"
FLOW_ID = "an-input"
FLOW_NAME = "an input"
PROCESS_NAME = "a process"


def _pinned() -> Profile:
    """The fixture's profile, pinning the hash of the zolca the stub serves."""
    pinned = pinned_profile()
    return pinned.model_copy(
        update={
            "inventory": pinned.inventory.model_copy(
                update={"sha256": hashlib.sha256(ZOLCA.read_bytes()).hexdigest()}
            )
        }
    )


def fixture_release(
    tmp_path: Path, *, unlinked: tuple[UnlinkedRow, ...] = ()
) -> tuple[StubNexus, Profile, Path]:
    """A Nexus session serving the fixture's zolca, a profile pinning the hash it serves, and a
    profiles directory recording that profile and the unlinked list given."""
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    server = StubNexus(downloads)
    server.contents[INVENTORY_UUID] = ZOLCA.read_bytes()
    profile = _pinned()
    released = tmp_path / "releases"
    released.mkdir()
    (released / f"{profile.version}.yaml").write_text(
        yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    write_unlinked(released / profile.unlinked, unlinked)
    return server, profile, released


def session_for(server: StubNexus) -> type:
    """A stand-in for `NexusSession` that opens the stub whatever account it is given, so no
    command in a test logs in."""

    class Session:
        def __init__(
            self, account: str, password: str, *, token: str | None = None, base: str
        ) -> None:
            self.base = base

        def __enter__(self) -> StubNexus:
            return server

        def __exit__(self, *_exc_info: object) -> None:
            return None

    return Session


def a_process(tmp_path: Path) -> str:
    """The id of one process the fixture's bundle holds."""
    built = build(ZOLCA, version="probe", out_dir=tmp_path / "probe")
    imported = read_background(built.bundle, "bafu-probe", foreground=frozenset())
    _, code = next(iter(imported.datasets))
    return code.split("_", 1)[0]


def unlisted_input(process_id: str) -> Unlinked:
    """One input no dataset of the fixture's package provides, taken by `process_id`."""
    return Unlinked(
        process=PROCESS_NAME,
        process_id=process_id,
        flow=FLOW_NAME,
        flow_id=FLOW_ID,
        provider_id=None,
        reason="no dataset of the package provides it",
        dataset=f"{process_id}_{FLOW_ID}",
        position=1,
        is_input=True,
        amount=1.0,
        unit="kg",
    )


def importable(row: Unlinked | None = None):
    """A read of a bundle the core will compile: the fixture's factors name a product flow no
    elementary flow of it holds, which the engine refuses, so those factors are left out. `row`,
    when given, is the one input no dataset of the package provides."""

    def read(path: Path, name: str, *, foreground: frozenset[str]) -> Import:
        imported = read_background(path, name, foreground=foreground)
        flows = {code for _, code in imported.flows}
        methods = [
            replace(method, factors=[factor for factor in method.factors if factor[0][1] in flows])
            for method in imported.methods
        ]
        return replace(imported, methods=methods, unlinked=[] if row is None else [row])

    return read


def _release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, listed: bool
) -> tuple[StubNexus, Profile, UnlinkedRow]:
    """The fixture's release recorded in a temporary profiles directory, its unlinked list holding
    the input the doubled read answers, or holding nothing."""
    process_id = a_process(tmp_path)
    row = UnlinkedRow(
        process_id=process_id,
        process_name=PROCESS_NAME,
        flow_id=FLOW_ID,
        flow_name=FLOW_NAME,
        flow_category="",
        provider_id=None,
    )
    server, profile, released = fixture_release(tmp_path, unlinked=(row,) if listed else ())
    monkeypatch.setattr(bafu_profile, "RELEASES", released)
    monkeypatch.setattr(bafu_setup, "read_background", importable(unlisted_input(process_id)))
    return server, profile, row


def test_not_applied_counts_what_the_bundle_holds(tmp_path: Path) -> None:
    built = build(ZOLCA, version="probe", out_dir=tmp_path)
    assert not_applied(built.bundle) == NotApplied(
        nw_sets=1,
        dq_entries=1,
        parameters=2,
        factor_formulas=2,
    )


def test_prepare_answers_the_import_with_its_unlinked_inputs_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile, row = _release(tmp_path, monkeypatch, listed=True)
    prepared = prepare(profile, server, tmp_path / "work", lambda _: None)

    assert prepared.bundle == tmp_path / "work" / f"bafu-{VERSION}.zip"
    assert prepared.bundle.is_file()
    assert prepared.imported.unlinked == []
    assert len(prepared.imported.datasets) == 2
    assert [(record.flow, record.amount, record.reason) for record in prepared.dropped] == [
        (FLOW_NAME, 1.0, "no dataset of the package provides it")
    ]
    assert prepared.unlinked == (row,)
    assert prepared.licence == server.root / f"{INVENTORY_UUID}-licence.txt"
    assert prepared.citation == CITATION
    assert prepared.not_applied == NotApplied(
        nw_sets=1,
        dq_entries=1,
        parameters=2,
        factor_formulas=2,
    )


def test_prepare_reports_its_steps_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile, _row = _release(tmp_path, monkeypatch, listed=True)
    reported: list[InstallProgress] = []

    prepare(profile, server, tmp_path / "work", reported.append)

    assert [progress.step for progress in reported] == [
        "downloading",
        "downloaded",
        "building",
        "reading",
        "checking",
    ]
    fetched = ZOLCA.stat().st_size + (server.root / LICENCE_FILE).stat().st_size
    assert reported[1].count == fetched


def test_session_logs_in_with_the_account_it_is_given() -> None:
    account = Account(username="someone@example.com", password="secret", token="a-token")

    found = bafu_setup.session("https://nexus.openlca.org", account)

    assert found.base == "https://nexus.openlca.org"
    assert found._account == account.username
    assert account.token is not None and found._token == account.token.get_secret_value()


def test_an_unlinked_input_outside_the_list_stops_prepare_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, profile, _row = _release(tmp_path, monkeypatch, listed=False)

    with pytest.raises(Invalid) as refused:
        prepare(profile, server, tmp_path / "work", lambda _: None)

    assert "a process takes an input and the unlinked list lacks it" in str(refused.value)
