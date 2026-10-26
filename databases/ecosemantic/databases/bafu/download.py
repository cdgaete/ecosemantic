"""Fetch BAFU's openLCA pack and its LCIA results pack from Nexus, refusing a file whose hash is not
the one its profile pins."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from lca_data_interface import Downloaded
from lca_data_interface import Pack as NexusPack
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

from ecosemantic.databases.bafu.profile import Pack, Profile
from ecosemantic.errors import Conflict, EcoSemanticError, Invalid, NotFound, Unavailable

_TRANSLATIONS: Final[dict[type[LcaDataInterfaceError], type[EcoSemanticError]]] = {
    CredentialsMissing: Unavailable,
    LoginRefused: Unavailable,
    TokenRequired: Unavailable,
    ShortDownload: Unavailable,
    ServiceError: Unavailable,
    NotInCatalog: NotFound,
    NotOnServer: NotFound,
    MissingField: Invalid,
    LicenceNotAccepted: Invalid,
}


class Nexus(Protocol):
    """The three calls a download makes on a Nexus session; `NexusSession` satisfies it and a test
    doubles it."""

    def pack(self, uuid: str) -> NexusPack: ...

    def licence(self, pack: NexusPack) -> Path: ...

    def download(
        self,
        pack: NexusPack,
        *,
        version: int,
        file_format: str,
        accept_licence: bool,
    ) -> Downloaded: ...


@dataclass(frozen=True)
class Terms:
    """What a download answers while a pack's terms are not accepted: the licence file to read and
    the citation to carry."""

    licence: Path
    citation: str


@dataclass(frozen=True)
class Downloads:
    """The files a download fetched, the pack's licence file, and the release's citation."""

    inventory: Path
    results: Path | None
    licence: Path
    citation: str


@contextmanager
def translating() -> Iterator[None]:
    """A client call whose errors leave as the core's, of the kind and with the names the spec's
    *Errors* table gives them."""
    try:
        yield
    except LcaDataInterfaceError as error:
        raise _translated(error) from error


def download(
    profile: Profile, session: Nexus, *, accept_terms: bool, results: bool
) -> Downloads | Terms:
    """Fetch a release's packs through Nexus, each file's SHA-256 compared with the profile's.

    Without `accept_terms` the pack's licence file is fetched and nothing is downloaded: the answer
    is the file a person reads to accept the terms. `results` also fetches the LCIA results pack,
    which only a validation reads.
    """
    with translating():
        inventory_pack = session.pack(profile.inventory.pack)
        licence = session.licence(inventory_pack)
        if not accept_terms:
            return Terms(licence=licence, citation=profile.citation)
        inventory = session.download(
            inventory_pack,
            version=profile.inventory.version,
            file_format=profile.inventory.format,
            accept_licence=True,
        )
        results_file = _fetched(profile.results, session) if results else None
    return Downloads(
        inventory=_checked(profile.inventory, inventory),
        results=None if results_file is None else _checked(profile.results, results_file),
        licence=licence,
        citation=profile.citation,
    )


def _fetched(pinned: Pack, session: Nexus) -> Downloaded:
    """One pack's file at the version and the format the profile pins, its terms accepted."""
    return session.download(
        session.pack(pinned.pack),
        version=pinned.version,
        file_format=pinned.format,
        accept_licence=True,
    )


def _checked(pinned: Pack, downloaded: Downloaded) -> Path:
    """The path of a file whose SHA-256 is the one the profile pins; a different hash is a conflict
    naming the file and both hashes."""
    if downloaded.sha256 != pinned.sha256:
        raise Conflict(
            f"{downloaded.path.name} hashes to {downloaded.sha256}, the profile pins "
            f"{pinned.sha256}"
        )
    return downloaded.path


def _translated(error: LcaDataInterfaceError) -> EcoSemanticError:
    """The core's error for one the client raised."""
    return _TRANSLATIONS[type(error)](str(error))
