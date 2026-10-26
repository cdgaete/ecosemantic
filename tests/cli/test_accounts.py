from __future__ import annotations

import pytest

from ecosemantic.cli.accounts import account_for
from ecosemantic.compute.accounts import missing
from ecosemantic.errors import Unavailable
from ecosemantic.ports.types import Account

SECRETS = {
    "NEXUS_PASSWORD": "the-password",
    "NEXUS_TOKEN": "the-token",
    "EI_PASSWORD": "the-other-password",
}


def test_account_for_prompts_on_a_terminal_without_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []
    silent: list[str] = []

    def prompt(text: str) -> str:
        asked.append(text)
        return "someone@example.com"

    def no_echo(text: str) -> str:
        silent.append(text)
        for name, answer in SECRETS.items():
            if name in text:
                return answer
        raise AssertionError(text)

    monkeypatch.setattr("builtins.input", prompt)
    monkeypatch.setattr("ecosemantic.cli.accounts.getpass.getpass", no_echo)

    nexus = account_for("nexus", {}, True)
    ecoinvent = account_for("ecoinvent", {}, True)

    assert nexus == Account(
        username="someone@example.com", password="the-password", token="the-token"
    )
    assert ecoinvent.username == "someone@example.com" and ecoinvent.token is None
    assert ecoinvent.password.get_secret_value() == "the-other-password"
    assert "NEXUS_USERNAME" in asked[0] and "EI_USERNAME" in asked[1]
    assert "NEXUS_PASSWORD" in silent[0] and "NEXUS_TOKEN" in silent[1]
    assert "EI_PASSWORD" in silent[2]

    held = account_for("ecoinvent", {"EI_USERNAME": "u", "EI_PASSWORD": "p"}, False)

    assert held.password.get_secret_value() == "p"
    assert len(asked) == 2 and len(silent) == 3


def test_account_for_off_a_terminal_without_variables_is_unavailable() -> None:
    with pytest.raises(Unavailable) as raised:
        account_for("ecoinvent", {}, False)

    assert str(raised.value) == "ecoinvent needs an account"
    assert raised.value.hint == missing("ecoinvent")
    assert "EI_USERNAME and EI_PASSWORD" in (raised.value.hint or "")
    assert "Databases editor" in (raised.value.hint or "")
