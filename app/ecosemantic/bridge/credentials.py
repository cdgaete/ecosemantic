"""The bridge's credential: the sign-in it carries, the stores that keep it, and the engine token an
unattended server reads instead."""

from __future__ import annotations

import contextlib
import os
import secrets
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol
from uuid import UUID

import keyring
from keyring.backends.fail import Keyring as FailKeyring
from keyring.errors import KeyringError, PasswordDeleteError
from pydantic import BaseModel, ConfigDict, ValidationError

from ecosemantic.errors import Invalid, Unavailable, field_error
from ecosemantic.files import replace
from ecosemantic.settings import workspace_digest

SERVICE = "ecosemantic-bridge"
OWNER_ONLY = 0o600
TOKEN_VARIABLES = ("ECOSEMANTIC_BRIDGE_TOKEN", "ECOSEMANTIC_BRIDGE_TOKEN_FILE")
NO_STORE = "this machine has no credential store for the bridge's sign-in"
NO_STORE_HINT = (
    "sign in with --credential-file PATH to keep it in a file only you can read, or give "
    "an unattended engine its engine token in ECOSEMANTIC_BRIDGE_TOKEN_FILE"
)


class Credential(BaseModel):
    """What a sign-in leaves: the bridge it was made at, the engine and account it names, and the
    refresh token a session renews the access token with."""

    model_config = ConfigDict(frozen=True)

    bridge_url: str
    client_id: str
    engine: UUID
    account: str
    handle: str
    page_url: str
    refresh_token: str


class BridgeStatus(BaseModel):
    """Whether this engine is signed in to the bridge: where its sign-in is kept, and the handle,
    page address and engine a credential names."""

    model_config = ConfigDict(frozen=True)

    signed_in: bool
    where: str | None = None
    hint: str | None = None
    handle: str | None = None
    page: str | None = None
    engine: str | None = None

    def printed(self) -> dict[str, object]:
        """The document `bridge status` prints: every field it names a value for, and the place a
        credential is kept named as none on a machine that has no store."""
        held = self.model_dump()
        return {name: value for name, value in held.items() if name == "where" or value is not None}


class CredentialStore(Protocol):
    """Where the credential is kept: the operating system's store, or a file the person names."""

    where: str

    def load(self) -> Credential | None: ...

    def save(self, credential: Credential) -> None: ...

    def delete(self) -> None: ...


def credential_key(bridge_url: str, systems_dir: Path) -> str:
    """What one bridge address and one systems directory keep their credential under."""
    return f"{bridge_url.rstrip('/')} {workspace_digest(systems_dir)}"


def store_for(bridge_url: str, systems_dir: Path, credential_file: Path | None) -> CredentialStore:
    """The file the person names, and otherwise the operating system's store under the bridge's
    address and this systems directory; a machine without one is refused naming the two ways that
    need no store."""
    if credential_file is not None:
        return FileStore(credential_file)
    if not has_credential_store():
        raise _no_store()
    return KeyringStore(credential_key(bridge_url, systems_dir))


def has_credential_store() -> bool:
    """Whether this machine has a credential store the bridge's sign-in can be kept in: the
    operating system's, unless keyring found none."""
    return not isinstance(keyring.get_keyring(), FailKeyring)


def token_variable(environ: Mapping[str, str]) -> str | None:
    """The variable an engine token is read from, the token's own before the file's, or None when
    the machine names neither."""
    for name in TOKEN_VARIABLES:
        if environ.get(name) is not None:
            return name
    return None


def engine_token(environ: Mapping[str, str]) -> str | None:
    """The token an unattended engine signs in with, from its variable or the file its other
    variable names, and never both."""
    named, filed = (environ.get(name) for name in TOKEN_VARIABLES)
    if named is not None and filed is not None:
        raise Invalid(
            "ECOSEMANTIC_BRIDGE_TOKEN and ECOSEMANTIC_BRIDGE_TOKEN_FILE both name an engine "
            "token; keep one"
        )
    if named is not None:
        if not named.strip():
            raise Invalid("ECOSEMANTIC_BRIDGE_TOKEN holds no engine token")
        return named
    if filed is None:
        return None
    return _token_file(Path(filed))


def _token_file(path: Path) -> str:
    """The engine token a file holds, refused naming the file when it is not there, cannot be read
    or holds none."""
    if not path.exists():
        raise Invalid(f"ECOSEMANTIC_BRIDGE_TOKEN_FILE names {path}, which is not there")
    _owner_only(path)
    try:
        held = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise Invalid(
            f"ECOSEMANTIC_BRIDGE_TOKEN_FILE names {path}, which cannot be read: {error.strerror}"
        ) from error
    if not held:
        raise Invalid(f"ECOSEMANTIC_BRIDGE_TOKEN_FILE names {path}, which holds no token")
    return held


def status(
    environ: Mapping[str, str],
    systems_dir: Path,
    bridge_url: str,
    credential_file: Path | None,
) -> BridgeStatus:
    """Whether this engine is signed in to the bridge, from the engine token's variables first and
    otherwise the store at `bridge_url` and `credential_file`: the handle, the page address and the
    engine it serves, and where the credential is kept; a machine with no credential store names
    that and the ways that need none."""
    if engine_token(environ) is not None:
        return BridgeStatus(signed_in=True, where=token_variable(environ))
    if credential_file is None and not has_credential_store():
        return BridgeStatus(signed_in=False, hint=NO_STORE_HINT)
    store = store_for(bridge_url, systems_dir, credential_file)
    credential = store.load()
    if credential is None:
        return BridgeStatus(signed_in=False, where=store.where)
    return BridgeStatus(
        signed_in=True,
        where=store.where,
        handle=credential.handle,
        page=credential.page_url,
        engine=str(credential.engine),
    )


class KeyringStore:
    """The credential in the operating system's store, under the service name and the key."""

    def __init__(self, key: str) -> None:
        if not has_credential_store():
            raise _no_store()
        backend = keyring.get_keyring()
        self.key = key
        self.where = f"the credential store ({backend.name})"
        self._backend = backend

    def load(self) -> Credential | None:
        held = self._guarded(self._backend.get_password, SERVICE, self.key)
        return None if held is None else _held(held, self.where)

    def save(self, credential: Credential) -> None:
        self._guarded(self._backend.set_password, SERVICE, self.key, credential.model_dump_json())

    def delete(self) -> None:
        """Forget the credential, an entry the store does not hold being nothing to delete."""
        self._guarded(
            self._backend.delete_password, SERVICE, self.key, tolerated=PasswordDeleteError
        )

    def _guarded(
        self,
        call: Callable[..., str | None],
        *args: str,
        tolerated: type[KeyringError] | None = None,
    ) -> str | None:
        """The backend's answer, with a store that cannot be reached now refusing as one that is not
        there, and an error of `tolerated`'s kind answering as the backend's own absence does."""
        try:
            return call(*args)
        except KeyringError as error:
            if tolerated is not None and isinstance(error, tolerated):
                return None
            raise _no_store() from error


class FileStore:
    """The credential in a file the person names, written readable by its owner alone."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.where = f"the file {path}"

    def load(self) -> Credential | None:
        """What the file holds, and None when it is not there; a file the group or others can
        reach is refused unread."""
        if not self.path.exists():
            return None
        _owner_only(self.path)
        try:
            held = self.path.read_text(encoding="utf-8")
        except OSError as error:
            raise Unavailable(f"cannot read {self.where}: {error.strerror}") from error
        return _held(held, self.where)

    def save(self, credential: Credential) -> None:
        """The credential through a temporary file only its owner can read, moved into place; a
        write or a move that fails leaves neither."""
        staged = self.path.parent / f".{self.path.name}.{secrets.token_hex(8)}"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY, OWNER_ONLY)
            with os.fdopen(handle, "w", encoding="utf-8") as opened:
                opened.write(credential.model_dump_json())
            replace(staged, self.path)
        except OSError as error:
            with contextlib.suppress(OSError):
                staged.unlink(missing_ok=True)
            raise Unavailable(f"cannot write {self.where}: {error.strerror}") from error

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


def _no_store() -> Unavailable:
    return Unavailable(NO_STORE, hint=NO_STORE_HINT)


def _owner_only(path: Path) -> None:
    """Refuse a file whose mode grants the group or others any bit; Windows carries ACLs, not mode
    bits."""
    if os.name != "posix":
        return
    if path.stat().st_mode & 0o077:
        raise Invalid(
            f"{path} is readable by more than its owner; keep it to yourself with chmod 600"
        )


def _held(serialized: str, where: str) -> Credential:
    try:
        return Credential.model_validate_json(serialized)
    except ValidationError as error:
        raise Invalid(
            f"{where} does not hold the bridge's credential: {field_error(error)}"
        ) from error
