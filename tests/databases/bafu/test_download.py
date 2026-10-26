"""BAFU's download fetches its two packs through Nexus, refusing a file whose hash is not the one
its profile pins."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lca_data_interface import Downloaded, PackFile, PackVersion
from lca_data_interface import Pack as ClientPack
from lca_data_interface.errors import (
    CredentialsMissing,
    LcaDataInterfaceError,
    LicenceNotAccepted,
    LoginRefused,
    MissingField,
    NotInCatalog,
    NotOnServer,
    ServiceError,
    ShortDownload,
    TokenRequired,
)

from ecosemantic.databases.bafu.download import Downloads, Terms, download
from ecosemantic.databases.bafu.profile import Column, Pack, Profile, Total
from ecosemantic.errors import Conflict, EcoSemanticError, Invalid, NotFound, Unavailable

INVENTORY_UUID = "c31fbb3c-ff98-4f50-8ceb-737ef690ce90"
RESULTS_UUID = "86aa5c2b-3334-4cc2-96f7-aaa6fd2494cb"
CITATION = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026"
INVENTORY_FILE = f"{INVENTORY_UUID}-2-openLCA zolca.zip"
RESULTS_FILE = f"{RESULTS_UUID}-2-excel.zip"
LICENCE_FILE = f"{INVENTORY_UUID}-licence.txt"
CONTENTS = {INVENTORY_UUID: b"the openLCA pack", RESULTS_UUID: b"the LCIA results"}


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def pinned_profile() -> Profile:
    """A release whose two packs pin the hashes of the bytes the double serves."""
    return Profile(
        version="2026-v1",
        server="https://nexus.openlca.org",
        citation=CITATION,
        inventory=Pack(
            pack=INVENTORY_UUID,
            version=2,
            format="openLCA zolca",
            sha256=_digest(CONTENTS[INVENTORY_UUID]),
        ),
        results=Pack(
            pack=RESULTS_UUID,
            version=2,
            format="excel",
            sha256=_digest(CONTENTS[RESULTS_UUID]),
        ),
        columns=(
            Column(header="GWP 100 [kg CO2-eq]", method="IPCC 2021", category="IPCC 2021 GWP 100"),
        ),
        total=Total(header="Total [UBP]", method="Ecological Scarcity 2021"),
        unlinked="unlinked-2026-v1.csv",
        differences="differences-2026-v1.csv",
        tolerance=1e-4,
    )


class StubNexus:
    """A Nexus session over a temporary directory: it answers each pack's record, writes the bytes a
    test names for that pack, and records its calls. Every call raises the error a test sets."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.contents = dict(CONTENTS)
        self.calls: list[tuple[str, ...]] = []
        self.failed: LcaDataInterfaceError | None = None

    def _raised(self) -> None:
        if self.failed is not None:
            raise self.failed

    def pack(self, uuid: str) -> ClientPack:
        self.calls.append(("pack", uuid))
        self._raised()
        return ClientPack(
            uuid=uuid,
            name=uuid,
            licence_file=7,
            versions=(
                PackVersion(
                    number=2,
                    release_note=None,
                    files=(PackFile(datafile_id=1, file_format="openLCA zolca"),),
                ),
            ),
        )

    def licence(self, pack: ClientPack) -> Path:
        self.calls.append(("licence", pack.uuid))
        self._raised()
        path = self.root / f"{pack.uuid}-licence.txt"
        path.write_text("the pack's terms")
        return path

    def download(
        self, pack: ClientPack, *, version: int, file_format: str, accept_licence: bool = False
    ) -> Downloaded:
        self.calls.append(("download", pack.uuid, str(version), file_format, str(accept_licence)))
        self._raised()
        content = self.contents[pack.uuid]
        path = self.root / f"{pack.uuid}-{version}-{file_format}.zip"
        path.write_bytes(content)
        return Downloaded(path=path, size=len(content), sha256=_digest(content))


@pytest.mark.parametrize("uuid", [INVENTORY_UUID, RESULTS_UUID], ids=["inventory", "results"])
def test_download_checks_each_hash(tmp_path: Path, uuid: str) -> None:
    server = StubNexus(tmp_path)
    server.contents[uuid] = CONTENTS[uuid] + b"!"
    with pytest.raises(Conflict) as refused:
        download(pinned_profile(), server, accept_terms=True, results=True)
    message = str(refused.value)
    assert (tmp_path / (INVENTORY_FILE if uuid == INVENTORY_UUID else RESULTS_FILE)).name in message
    assert _digest(server.contents[uuid]) in message
    assert _digest(CONTENTS[uuid]) in message


def test_without_accept_terms_nothing_is_downloaded(tmp_path: Path) -> None:
    server = StubNexus(tmp_path)
    answer = download(pinned_profile(), server, accept_terms=False, results=True)
    assert answer == Terms(licence=tmp_path / LICENCE_FILE, citation=CITATION)
    assert [call[0] for call in server.calls] == ["pack", "licence"]


def test_results_only_with_the_flag(tmp_path: Path) -> None:
    without = StubNexus(tmp_path)
    assert download(pinned_profile(), without, accept_terms=True, results=False) == Downloads(
        inventory=tmp_path / INVENTORY_FILE,
        results=None,
        licence=tmp_path / LICENCE_FILE,
        citation=CITATION,
    )
    assert [call[:2] for call in without.calls] == [
        ("pack", INVENTORY_UUID),
        ("licence", INVENTORY_UUID),
        ("download", INVENTORY_UUID),
    ]

    with_results = StubNexus(tmp_path)
    assert download(pinned_profile(), with_results, accept_terms=True, results=True) == Downloads(
        inventory=tmp_path / INVENTORY_FILE,
        results=tmp_path / RESULTS_FILE,
        licence=tmp_path / LICENCE_FILE,
        citation=CITATION,
    )
    assert [call[:2] for call in with_results.calls] == [
        ("pack", INVENTORY_UUID),
        ("licence", INVENTORY_UUID),
        ("download", INVENTORY_UUID),
        ("pack", RESULTS_UUID),
        ("download", RESULTS_UUID),
    ]


@pytest.mark.parametrize(
    ("failure", "expected", "named"),
    [
        (CredentialsMissing(("NEXUS_USERNAME", "NEXUS_PASSWORD")), Unavailable, "NEXUS_PASSWORD"),
        (LoginRefused("carlos", 401), Unavailable, "the login of carlos with status 401"),
        (TokenRequired(), Unavailable, "set NEXUS_TOKEN"),
        (
            NotInCatalog(INVENTORY_UUID, "version 2, format excel", ("version 2: openLCA zolca",)),
            NotFound,
            "version 2: openLCA zolca",
        ),
        (LicenceNotAccepted(INVENTORY_UUID, 7), Invalid, f"pack {INVENTORY_UUID} carries terms"),
        (NotOnServer("Federal_LCA_Commons/BAFU", "17df3fa", "no such commit"), NotFound, "17df3fa"),
        (MissingField("GET /ws/files/7", "Content-Disposition"), Invalid, "Content-Disposition"),
        (ShortDownload("pack.zip", 100, 10), Unavailable, "ended after 10 of 100 bytes"),
        (
            ServiceError("GET /ws/user/downloads", 503, "the server is down"),
            Unavailable,
            "the server is down",
        ),
    ],
    ids=[
        "credentials",
        "login",
        "token",
        "catalog",
        "licence",
        "server",
        "field",
        "short",
        "service",
    ],
)
def test_a_client_error_is_translated(
    tmp_path: Path, failure: LcaDataInterfaceError, expected: type[EcoSemanticError], named: str
) -> None:
    server = StubNexus(tmp_path)
    server.failed = failure
    with pytest.raises(expected) as refused:
        download(pinned_profile(), server, accept_terms=True, results=True)
    assert named in str(refused.value)


def test_a_refused_login_names_no_password(tmp_path: Path) -> None:
    server = StubNexus(tmp_path)
    server.failed = LoginRefused("carlos", 403)
    with pytest.raises(Unavailable) as refused:
        download(pinned_profile(), server, accept_terms=True, results=False)
    assert "password" not in str(refused.value).lower()
