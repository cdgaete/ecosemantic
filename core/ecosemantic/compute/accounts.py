"""Read the accounts a source's install needs from an environment, and strip them from an
environment an install process is started with."""

from __future__ import annotations

from collections.abc import Mapping

from ecosemantic.ports.types import Account, CredentialKind

VARIABLES: Mapping[CredentialKind, tuple[str, str, str | None]] = {
    "ecoinvent": ("EI_USERNAME", "EI_PASSWORD", None),
    "nexus": ("NEXUS_USERNAME", "NEXUS_PASSWORD", "NEXUS_TOKEN"),
}
PREFIXES = ("EI_", "NEXUS_")


def account_from(environ: Mapping[str, str], kind: CredentialKind) -> Account | None:
    """The account an environment holds for a kind, and none when it holds no username or no
    password for it. The token of a Nexus account with a second factor is optional."""
    username, password, token = VARIABLES[kind]
    held_user = environ.get(username)
    held_password = environ.get(password)
    if not held_user or not held_password:
        return None
    held_token = environ.get(token) if token is not None else None
    return Account(
        username=held_user,
        password=held_password,
        token=held_token or None,
    )


def held_accounts(environ: Mapping[str, str]) -> dict[CredentialKind, Account]:
    """Every account an environment holds, by the kind of credential it is."""
    held: dict[CredentialKind, Account] = {}
    for kind in VARIABLES:
        account = account_from(environ, kind)
        if account is not None:
            held[kind] = account
    return held


def without_credentials(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment with every variable a credential travels in removed, so an install
    process started on it holds none of them."""
    return {name: value for name, value in environ.items() if not name.startswith(PREFIXES)}


def missing(kind: CredentialKind) -> str:
    """What a person does to give a source the account it needs."""
    username, password, _token = VARIABLES[kind]
    return f"set {username} and {password}, or enter the account on the page's Databases editor"
