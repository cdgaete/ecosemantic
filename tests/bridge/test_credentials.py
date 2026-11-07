"""How the bridge keeps its credential: the operating system's store, a file the person names,
and the engine token an unattended server reads instead."""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path

import keyring
import pytest
from keyring.backends.fail import Keyring as FailKeyring
from keyring.errors import KeyringError

from ecosemantic.bridge.credentials import (
    NO_STORE_HINT,
    SERVICE,
    Credential,
    FileStore,
    KeyringStore,
    credential_key,
    engine_token,
    has_credential_store,
    store_for,
)
from ecosemantic.errors import Invalid, Unavailable
from ecosemantic.settings import workspace_digest
from tests.memory_keyring import MemoryKeyring

BRIDGE = "https://bridge.ecosemantic.com"
OTHER_BRIDGE = "http://127.0.0.1:8000"
REFUSAL = "this machine has no credential store for the bridge's sign-in"
HINT = NO_STORE_HINT
CRED_MAX_CREDENTIAL_BLOB_SIZE = 2560
posix_only = pytest.mark.skipif(os.name != "posix", reason="only POSIX carries mode bits")
posix_non_root = pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="only POSIX carries mode bits, and root reads them all",
)


class LockedKeyring(MemoryKeyring):
    """A store that is installed and cannot be reached, as a locked Secret Service is."""

    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringError("the store is locked")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringError("the store is locked")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringError("the store is locked")


def a_credential(**given: object) -> Credential:
    """A credential the bridge hands a signed-in engine."""
    fields: dict[str, object] = {
        "bridge_url": BRIDGE,
        "client_id": "the engine's client",
        "engine": uuid.UUID("3f0b9a0e-6a1c-4d5f-9a2b-7c1d0e8f4a63"),
        "account": "account-1",
        "handle": "carlos",
        "page_url": "https://carlos.ecosemantic.com",
        "refresh_token": "rt_" + "0" * 40,
    }
    fields.update(given)
    return Credential.model_validate(fields)


def test_a_credential_round_trips_through_the_credential_store(tmp_path: Path) -> None:
    store = store_for(BRIDGE, tmp_path, None)
    assert store.load() is None
    credential = a_credential()
    store.save(credential)
    assert store.load() == credential
    assert store.where == f"the credential store ({keyring.get_keyring().name})"
    store.delete()
    assert store.load() is None


def test_each_bridge_and_systems_directory_keeps_its_own_credential(tmp_path: Path) -> None:
    here = tmp_path / "here"
    elsewhere = tmp_path / "elsewhere"
    assert credential_key(BRIDGE, here) == f"{BRIDGE} {workspace_digest(here)}"
    assert credential_key(BRIDGE + "/", here) == f"{BRIDGE} {workspace_digest(here)}"
    assert credential_key(BRIDGE, here) != credential_key(BRIDGE, elsewhere)
    assert credential_key(BRIDGE, here) != credential_key(OTHER_BRIDGE, here)
    first = a_credential()
    second = a_credential(account="account-2", refresh_token="rt_" + "1" * 40)
    third = a_credential(bridge_url=OTHER_BRIDGE, account="account-3")
    store_for(BRIDGE, here, None).save(first)
    store_for(BRIDGE, elsewhere, None).save(second)
    store_for(OTHER_BRIDGE, here, None).save(third)
    assert store_for(BRIDGE, here, None).load() == first
    assert store_for(BRIDGE, elsewhere, None).load() == second
    assert store_for(OTHER_BRIDGE, here, None).load() == third


def test_a_machine_without_a_credential_store_is_refused_naming_both_other_ways(
    tmp_path: Path,
) -> None:
    keyring.set_keyring(FailKeyring())
    with pytest.raises(Unavailable) as refused:
        store_for(BRIDGE, tmp_path, None)
    assert str(refused.value) == REFUSAL
    assert refused.value.hint == HINT


def test_the_machine_answers_whether_it_has_a_credential_store(tmp_path: Path) -> None:
    assert has_credential_store()
    keyring.set_keyring(FailKeyring())
    assert not has_credential_store()
    credential_file = tmp_path / "credential.json"
    assert store_for(BRIDGE, tmp_path, credential_file).where == f"the file {credential_file}"


def test_a_credential_store_that_fails_at_use_names_both_other_ways(tmp_path: Path) -> None:
    keyring.set_keyring(LockedKeyring())
    store = store_for(BRIDGE, tmp_path, None)
    for call in (store.load, lambda: store.save(a_credential()), store.delete):
        with pytest.raises(Unavailable) as refused:
            call()
        assert str(refused.value) == REFUSAL
        assert refused.value.hint == HINT


@posix_only
def test_a_credential_file_is_written_readable_by_its_owner_alone(tmp_path: Path) -> None:
    path = tmp_path / "credential.json"
    store = store_for(BRIDGE, tmp_path, path)
    assert store.load() is None
    credential = a_credential()
    store.save(credential)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.load() == credential
    assert store.where == f"the file {path}"
    store.delete()
    assert store.load() is None
    assert sorted(path.parent.iterdir()) == []


@posix_only
def test_a_credential_file_others_can_read_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "credential.json"
    path.write_text(a_credential().model_dump_json(), encoding="utf-8")
    os.chmod(path, 0o644)
    with pytest.raises(Invalid) as refused:
        FileStore(path).load()
    assert str(path) in str(refused.value)
    os.chmod(path, 0o640)
    with pytest.raises(Invalid):
        FileStore(path).load()


@posix_only
def test_a_credential_file_that_cannot_be_read_names_it(tmp_path: Path) -> None:
    path = tmp_path / "credential.json"
    path.mkdir()
    os.chmod(path, 0o600)
    with pytest.raises(Unavailable) as refused:
        FileStore(path).load()
    assert str(path) in str(refused.value)


@posix_only
def test_a_credential_file_that_cannot_be_written_names_it(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("", encoding="utf-8")
    path = blocked / "credential.json"
    with pytest.raises(Unavailable) as refused:
        FileStore(path).save(a_credential())
    assert str(path) in str(refused.value)


@posix_only
def test_a_credential_file_whose_move_fails_leaves_no_staged_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "credential.json"

    def refuses(source: object, target: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("ecosemantic.bridge.credentials.os.replace", refuses)
    with pytest.raises(Unavailable) as refused:
        FileStore(path).save(a_credential())
    assert str(path) in str(refused.value)
    assert sorted(path.parent.iterdir()) == []


def test_a_stored_file_that_is_not_a_credential_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "credential.json"
    path.write_text(json.dumps({"bridge_url": BRIDGE}), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(Invalid) as refused:
        FileStore(path).load()
    assert str(path) in str(refused.value)


def test_a_stored_password_that_is_not_a_credential_is_refused(tmp_path: Path) -> None:
    store = KeyringStore(credential_key(BRIDGE, tmp_path))
    keyring.set_password(SERVICE, credential_key(BRIDGE, tmp_path), "not a credential")
    with pytest.raises(Invalid) as refused:
        store.load()
    assert str(store.where) in str(refused.value)


def test_a_stored_credential_fits_the_windows_credential_manager() -> None:
    credential = a_credential(refresh_token="r" * 43)
    blob = credential.model_dump_json().encode("utf-16-le")
    assert len(blob) < CRED_MAX_CREDENTIAL_BLOB_SIZE


def test_an_engine_token_is_read_from_its_variable_or_its_file_and_never_both(
    tmp_path: Path,
) -> None:
    assert engine_token({}) is None
    assert engine_token({"ECOSEMANTIC_BRIDGE_TOKEN": "from-the-variable"}) == "from-the-variable"
    path = tmp_path / "token"
    path.write_text("from-the-file\n", encoding="utf-8")
    os.chmod(path, 0o600)
    assert engine_token({"ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(path)}) == "from-the-file"
    with pytest.raises(Invalid) as refused:
        engine_token(
            {
                "ECOSEMANTIC_BRIDGE_TOKEN": "from-the-variable",
                "ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(path),
            }
        )
    assert "ECOSEMANTIC_BRIDGE_TOKEN" in str(refused.value)
    assert "ECOSEMANTIC_BRIDGE_TOKEN_FILE" in str(refused.value)


def test_an_engine_token_file_that_is_missing_or_empty_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(Invalid) as refused:
        engine_token({"ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(missing)})
    assert str(missing) in str(refused.value)
    empty = tmp_path / "empty"
    empty.write_text("\n", encoding="utf-8")
    os.chmod(empty, 0o600)
    with pytest.raises(Invalid) as hollow:
        engine_token({"ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(empty)})
    assert str(empty) in str(hollow.value)


@posix_only
def test_an_engine_token_file_others_can_read_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("from-the-file\n", encoding="utf-8")
    os.chmod(path, 0o644)
    with pytest.raises(Invalid) as refused:
        engine_token({"ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(path)})
    assert str(path) in str(refused.value)


@posix_non_root
def test_an_engine_token_file_that_cannot_be_read_names_it(tmp_path: Path) -> None:
    path = tmp_path / "token"
    path.write_text("from-the-file\n", encoding="utf-8")
    os.chmod(path, 0o000)
    with pytest.raises(Invalid) as refused:
        engine_token({"ECOSEMANTIC_BRIDGE_TOKEN_FILE": str(path)})
    assert str(path) in str(refused.value)


def test_forgetting_a_credential_the_store_does_not_hold_does_nothing(tmp_path: Path) -> None:
    store = KeyringStore(credential_key(BRIDGE, tmp_path))
    store.delete()
    store.save(a_credential())
    store.delete()
    store.delete()
    assert store.load() is None


def test_an_engine_token_from_a_blank_variable_is_refused() -> None:
    for blank in ("", " ", "\n "):
        with pytest.raises(Invalid) as refused:
            engine_token({"ECOSEMANTIC_BRIDGE_TOKEN": blank})
        assert "ECOSEMANTIC_BRIDGE_TOKEN" in str(refused.value)
