from __future__ import annotations

from ecosemantic.installs.handover import decoded, encoded
from ecosemantic.ports.types import Account


def test_handover_round_trips_an_account_and_none() -> None:
    account = Account(username="someone", password="hunter2-secret", token="654321")

    assert decoded(encoded(account)) == account
    assert encoded(None) == b""
    assert decoded(b"") is None
