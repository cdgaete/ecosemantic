from __future__ import annotations

from pydantic import SecretStr

from ecosemantic.compute.accounts import (
    PREFIXES,
    VARIABLES,
    account_from,
    held_accounts,
    missing,
    without_credentials,
)


def test_account_from_needs_both_username_and_password() -> None:
    assert account_from({}, "ecoinvent") is None
    assert account_from({"EI_USERNAME": "carlos"}, "ecoinvent") is None
    assert account_from({"EI_PASSWORD": "s3cret"}, "ecoinvent") is None
    whole = account_from({"EI_USERNAME": "carlos", "EI_PASSWORD": "s3cret"}, "ecoinvent")
    assert whole is not None and whole.username == "carlos"
    assert whole.password.get_secret_value() == "s3cret"
    assert whole.token is None


def test_the_nexus_token_is_optional() -> None:
    plain = account_from({"NEXUS_USERNAME": "carlos", "NEXUS_PASSWORD": "s3cret"}, "nexus")
    assert plain is not None and plain.token is None
    factored = account_from(
        {"NEXUS_USERNAME": "carlos", "NEXUS_PASSWORD": "s3cret", "NEXUS_TOKEN": "123456"},
        "nexus",
    )
    assert factored is not None and factored.token == SecretStr("123456")


def test_without_credentials_drops_every_ei_and_nexus_variable() -> None:
    environ = {
        "EI_USERNAME": "carlos",
        "EI_PASSWORD": "s3cret",
        "NEXUS_USERNAME": "carlos",
        "NEXUS_PASSWORD": "s3cret",
        "NEXUS_TOKEN": "123456",
        "PATH": "/usr/bin",
        "HOME": "/home/person",
    }
    assert without_credentials(environ) == {"PATH": "/usr/bin", "HOME": "/home/person"}
    assert without_credentials({}) == {}


def test_the_accounts_the_environment_holds_are_read_by_kind() -> None:
    held = held_accounts({"EI_USERNAME": "carlos", "EI_PASSWORD": "s3cret", "NEXUS_USERNAME": "x"})
    assert list(held) == ["ecoinvent"]
    assert held["ecoinvent"].username == "carlos"
    assert held_accounts({}) == {}


def test_a_missing_account_names_the_variables_and_the_page() -> None:
    assert missing("ecoinvent") == (
        "set EI_USERNAME and EI_PASSWORD, or enter the account on the page's Databases editor"
    )
    assert missing("nexus") == (
        "set NEXUS_USERNAME and NEXUS_PASSWORD, or enter the account on the page's Databases editor"
    )


def test_every_credential_variable_is_named_under_a_dropped_prefix() -> None:
    assert set(VARIABLES) == {"ecoinvent", "nexus"}
    for kind, names in VARIABLES.items():
        for name in names:
            if name is not None:
                assert name.startswith(PREFIXES), (kind, name)
