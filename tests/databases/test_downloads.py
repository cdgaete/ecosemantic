"""The rule a release download applies to an error the client raised and to the hash of the file it
fetched."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from lca_data_interface import Downloaded
from lca_data_interface import errors as client_errors
from lca_data_interface.errors import CacheUnwritable, LcaDataInterfaceError, ServiceError

from ecosemantic.databases.bafu.download import download as bafu_download
from ecosemantic.databases.downloads import TRANSLATIONS, checked, translated
from ecosemantic.errors import Conflict, Unavailable
from tests.databases.bafu.test_download import StubNexus, pinned_profile


class Refused(ServiceError):
    """A refusal the client names more narrowly than the class the table lists."""


def test_every_client_error_has_a_translation() -> None:
    defined = {
        error
        for _, error in inspect.getmembers(client_errors, inspect.isclass)
        if issubclass(error, LcaDataInterfaceError) and error.__module__ == client_errors.__name__
    }
    assert defined
    assert defined <= set(TRANSLATIONS)


def test_a_subclass_translates_as_its_listed_ancestor() -> None:
    refused = Refused("GET /ws/files", 503, "the server is down")
    assert type(translated(refused)) is Unavailable
    assert str(translated(refused)) == str(refused)


def test_an_unwritable_cache_is_unavailable_from_bafu(tmp_path: Path) -> None:
    server = StubNexus(tmp_path)
    server.failed = CacheUnwritable("/cache", 3, "read-only")
    with pytest.raises(Unavailable) as refused:
        bafu_download(pinned_profile(), server, accept_terms=True, results=False)
    assert "read-only" in str(refused.value)


def test_a_pin_mismatch_is_a_conflict_naming_both_hashes(tmp_path: Path) -> None:
    path = tmp_path / "pack.zip"
    path.write_bytes(b"the openLCA pack")
    downloaded = Downloaded(path=path, size=path.stat().st_size, sha256="0" * 64)
    with pytest.raises(Conflict) as refused:
        checked(downloaded, "1" * 64)
    assert str(refused.value) == (f"pack.zip hashes to {'0' * 64}, the profile pins {'1' * 64}")
    assert checked(downloaded, "0" * 64) == path
