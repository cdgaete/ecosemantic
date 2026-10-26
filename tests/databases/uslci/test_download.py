"""USLCI's download fetches the files its profile pins through the client, and refuses one whose
hash is not the pinned hash."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lca_data_interface import Downloaded, Release
from lca_data_interface.errors import (
    LcaDataInterfaceError,
    MissingField,
    NotOnServer,
    ServiceError,
    ShortDownload,
)

from ecosemantic.databases.uslci.download import Downloads, download
from ecosemantic.databases.uslci.profile import Pin, Profile
from ecosemantic.errors import Conflict, Invalid, NotFound, Unavailable

INVENTORY = "National_Renewable_Energy_Laboratory/USLCI_Database_Public"
METHOD = "Federal_LCA_Commons/IPCC_GWP"
BRIDGED = "Federal_LCA_Commons/US_electricity_baseline"
INVENTORY_COMMIT = "fddfc1a7a6c93e1a71f457446df7813245c828e6"
METHOD_COMMIT = "f0f90ef2f056be6e1686df0858a57b66ecfa2a62"
BRIDGED_COMMIT = "ac82eb31179a3a59196b8b30bd06e39e593b0261"
BRIDGED_CONTENT = b"us electricity baseline"
CONTENTS = {INVENTORY_COMMIT: b"uslci inventory", METHOD_COMMIT: b"ipcc gwp"}


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def pinned_profile() -> Profile:
    return Profile(
        version="1.2026-09.0",
        server="https://www.lcacommons.gov/lca-collaboration",
        inventory=Pin(
            repository=INVENTORY,
            commit=INVENTORY_COMMIT,
            sha256=_digest(CONTENTS[INVENTORY_COMMIT]),
        ),
        methods=(
            Pin(
                repository=METHOD,
                release="1.2026-09.2",
                commit=METHOD_COMMIT,
                sha256=_digest(CONTENTS[METHOD_COMMIT]),
            ),
        ),
        unlinked="unlinked-1.2026-09.0.csv",
        left_out="left-out-1.2026-09.0.csv",
    )


class StubCommons:
    """A Collaboration Server over a temporary directory: it writes the bytes a test names for a
    commit, answers the history a test names, and raises what a test asks for."""

    def __init__(self, root: Path, contents: dict[str, bytes]) -> None:
        self.root = root
        self.contents = contents
        self.calls: list[tuple[str, ...]] = []
        self.released: list[Release] = []
        self.failed: LcaDataInterfaceError | None = None
        self.history_failed: LcaDataInterfaceError | None = None
        self.answered: str | None = None

    def releases(self, group: str, name: str) -> list[Release]:
        self.calls.append(("releases", group, name))
        if self.history_failed is not None:
            raise self.history_failed
        return self.released

    def download(self, group: str, name: str, commit: str) -> Downloaded:
        self.calls.append(("download", group, name, commit))
        if self.failed is not None:
            raise self.failed
        content = self.contents[commit]
        path = self.root / f"{commit}.zip"
        path.write_bytes(content)
        return Downloaded(path=path, size=len(content), sha256=self.answered or _digest(content))


def test_a_download_answers_each_pinned_file(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    files = download(pinned_profile(), server)
    assert files == Downloads(
        inventory=tmp_path / f"{INVENTORY_COMMIT}.zip",
        methods=(tmp_path / f"{METHOD_COMMIT}.zip",),
    )
    assert server.calls == [
        (
            "download",
            "National_Renewable_Energy_Laboratory",
            "USLCI_Database_Public",
            INVENTORY_COMMIT,
        ),
        ("download", "Federal_LCA_Commons", "IPCC_GWP", METHOD_COMMIT),
    ]


def test_download_fetches_the_bridged_repositories(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, {**CONTENTS, BRIDGED_COMMIT: BRIDGED_CONTENT})
    pin = Pin(
        repository=BRIDGED,
        release="1.2026-06.1",
        commit=BRIDGED_COMMIT,
        sha256=_digest(BRIDGED_CONTENT),
    )
    profile = pinned_profile().model_copy(update={"bridged": (pin,)})
    files = download(profile, server)
    assert files.bridged == (tmp_path / f"{BRIDGED_COMMIT}.zip",)
    assert server.calls == [
        (
            "download",
            "National_Renewable_Energy_Laboratory",
            "USLCI_Database_Public",
            INVENTORY_COMMIT,
        ),
        ("download", "Federal_LCA_Commons", "US_electricity_baseline", BRIDGED_COMMIT),
        ("download", "Federal_LCA_Commons", "IPCC_GWP", METHOD_COMMIT),
    ]
    # the profile pins a hash the file it serves does not have
    refused = profile.model_copy(update={"bridged": (pin.model_copy(update={"sha256": "0" * 64}),)})
    with pytest.raises(Conflict) as conflict:
        download(refused, server)
    assert f"{BRIDGED_COMMIT}.zip" in str(conflict.value)


def test_a_file_whose_hash_differs_is_a_conflict(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    # the bytes the client wrote hash to the pinned value; the digest it answers does not
    server.answered = "0" * 64
    with pytest.raises(Conflict) as refused:
        download(pinned_profile(), server)
    message = str(refused.value)
    assert f"{INVENTORY_COMMIT}.zip" in message
    assert "0" * 64 in message
    assert _digest(CONTENTS[INVENTORY_COMMIT]) in message


def test_a_commit_the_server_lacks_names_the_released_commits(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = NotOnServer(INVENTORY, INVENTORY_COMMIT, "no such commit")
    server.released = [
        Release(
            version="1.2026-09.0",
            commit="2f0f9a1b7c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f",
            released_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    ]
    with pytest.raises(NotFound) as missed:
        download(pinned_profile(), server)
    message = str(missed.value)
    assert INVENTORY in message
    assert INVENTORY_COMMIT in message
    assert "1.2026-09.0 at 2f0f9a1b7c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f" in message


def test_a_service_failure_asks_for_no_released_commits(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = ServiceError("GET /ws/public/download/json/prepare", 503, "the server is down")
    with pytest.raises(Unavailable):
        download(pinned_profile(), server)
    assert [call for call in server.calls if call[0] == "releases"] == []


def test_a_missing_commit_asks_once_for_the_released_commits(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = NotOnServer(INVENTORY, INVENTORY_COMMIT, "no such commit")
    server.released = [
        Release(
            version="1.2026-09.0",
            commit="2f0f9a1b7c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f",
            released_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    ]
    with pytest.raises(NotFound):
        download(pinned_profile(), server)
    assert [call for call in server.calls if call[0] == "releases"] == [
        ("releases", "National_Renewable_Energy_Laboratory", "USLCI_Database_Public")
    ]


def test_a_missing_repository_names_it_without_asking_for_its_commits(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = NotOnServer(INVENTORY, None, "no such repository")
    with pytest.raises(NotFound) as missed:
        download(pinned_profile(), server)
    assert INVENTORY in str(missed.value)
    assert [call for call in server.calls if call[0] == "releases"] == []


def test_a_history_the_server_cannot_answer_answers_its_own_error(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = NotOnServer(INVENTORY, INVENTORY_COMMIT, "no such commit")
    server.history_failed = ServiceError("GET /ws/public/history", 503, "the server is down")
    with pytest.raises(Unavailable) as refused:
        download(pinned_profile(), server)
    assert "the server is down" in str(refused.value)


@pytest.mark.parametrize(
    "failure",
    [
        ServiceError("GET /ws/public/download/json/prepare", 503, "the server is down"),
        ShortDownload("USLCI_Database_Public.zip", 32_056_606, 1_024),
    ],
    ids=["service", "short"],
)
def test_a_service_failure_is_unavailable(tmp_path: Path, failure: LcaDataInterfaceError) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = failure
    with pytest.raises(Unavailable) as refused:
        download(pinned_profile(), server)
    assert str(failure) in str(refused.value)


def test_a_response_missing_a_field_is_invalid(tmp_path: Path) -> None:
    server = StubCommons(tmp_path, CONTENTS)
    server.failed = MissingField("GET /ws/public/download/json", "Content-Disposition")
    with pytest.raises(Invalid, match="Content-Disposition"):
        download(pinned_profile(), server)
