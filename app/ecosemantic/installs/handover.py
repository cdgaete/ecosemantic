"""The account a server hands an install process on that process's standard input, as bytes."""

from __future__ import annotations

import json

from ecosemantic.ports.types import Account


def encoded(account: Account | None) -> bytes:
    """The bytes a server writes to an install process's standard input, empty when it hands no
    account over."""
    if account is None:
        return b""
    return json.dumps(
        {
            "username": account.username,
            "password": account.password.get_secret_value(),
            "token": None if account.token is None else account.token.get_secret_value(),
        }
    ).encode("utf-8")


def decoded(data: bytes) -> Account | None:
    """The account an install process read from its standard input, and none when it read
    nothing."""
    if not data:
        return None
    held = json.loads(data)
    return Account(username=held["username"], password=held["password"], token=held["token"])
