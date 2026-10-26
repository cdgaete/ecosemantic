"""The account a source's install needs: the environment's, or a prompt, or a refusal."""

from __future__ import annotations

import getpass
from collections.abc import Mapping

from ecosemantic.compute.accounts import VARIABLES, account_from, missing
from ecosemantic.errors import Unavailable
from ecosemantic.ports.types import Account, CredentialKind


def account_for(kind: CredentialKind, environ: Mapping[str, str], terminal: bool) -> Account:
    """The account a kind of credential is held by in `environ`; otherwise the answers to a prompt,
    the password and a Nexus token read without echo, when `terminal`; and otherwise `Unavailable`
    naming the variables and the page that supply it."""
    held = account_from(environ, kind)
    if held is not None:
        return held
    if not terminal:
        raise Unavailable(f"{kind} needs an account", hint=missing(kind))
    username, password, token = VARIABLES[kind]
    held_username = input(f"{username}: ")
    held_password = getpass.getpass(f"{password}: ")
    held_token = getpass.getpass(f"{token} (empty for none): ") if token is not None else None
    return Account(username=held_username, password=held_password, token=held_token or None)
