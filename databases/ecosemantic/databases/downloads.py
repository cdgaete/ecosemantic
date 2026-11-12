"""The rule two release sources apply to a download: the core's error for one the client raised,
and the file whose hash is the one the profile pins."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from lca_data_interface import Downloaded
from lca_data_interface.errors import (
    CacheUnwritable,
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

from ecosemantic.errors import Conflict, EcoSemanticError, Invalid, NotFound, Unavailable

TRANSLATIONS: Final[Mapping[type[LcaDataInterfaceError], type[EcoSemanticError]]] = {
    CredentialsMissing: Unavailable,
    LoginRefused: Unavailable,
    TokenRequired: Unavailable,
    ShortDownload: Unavailable,
    ServiceError: Unavailable,
    CacheUnwritable: Unavailable,
    NotInCatalog: NotFound,
    NotOnServer: NotFound,
    MissingField: Invalid,
    LicenceNotAccepted: Invalid,
    LcaDataInterfaceError: Unavailable,
}


def translated(error: LcaDataInterfaceError) -> EcoSemanticError:
    """The core's error for one the client raised: the kind `TRANSLATIONS` lists nearest in its
    lineage, carrying the client's message."""
    lineage = [kind for kind in type(error).__mro__ if issubclass(kind, LcaDataInterfaceError)]
    return TRANSLATIONS[next(kind for kind in lineage if kind in TRANSLATIONS)](str(error))


def checked(downloaded: Downloaded, sha256: str) -> Path:
    """The path of a file whose SHA-256 is the one the profile pins; a different hash is a conflict
    naming the file and both hashes."""
    if downloaded.sha256 != sha256:
        raise Conflict(
            f"{downloaded.path.name} hashes to {downloaded.sha256}, the profile pins {sha256}"
        )
    return downloaded.path
