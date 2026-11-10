from __future__ import annotations

import re
from typing import get_args

from ecosemantic.mcp.accounts import Advice, Reach, account_advice, entry_for
from ecosemantic.mcp.context import AccountStart, Start
from ecosemantic.ports.types import CredentialKind, DatabaseSource, SourceName

WHY = (
    "Database accounts are entered on the computer where EcoSemantic runs, so the password "
    "stays on that computer and never passes through the internet or a chat."
)
TRAY = (
    "On the computer where EcoSemantic runs, click the EcoSemantic icon beside the clock in the "
    "taskbar (it may sit under the ^ arrow) and choose Database accounts…"
)
SCREEN = "http://127.0.0.1:12266/accounts"


def source(name: SourceName, kind: CredentialKind) -> DatabaseSource:
    """A source as an install's list answers it, naming the credential its install needs."""
    return DatabaseSource(name=name, versions=[], system_models=[], credential=kind, terms=False)


def test_the_tray_start_names_the_tray_item() -> None:
    advice = account_advice(AccountStart(start="tray", screen=SCREEN))
    assert advice == Advice(why=WHY, steps=TRAY)


def test_a_bridged_reach_says_how_the_page_reached_the_engine() -> None:
    advice = account_advice(AccountStart(start="tray", screen=SCREEN), reach="bridge")
    assert advice.why == f"This page reaches EcoSemantic through the bridge. {WHY}"
    assert account_advice(AccountStart(), reach="network").why.startswith(
        "This page reaches EcoSemantic across the network. "
    )


def test_a_terminal_with_a_screen_names_its_address_and_setup() -> None:
    bafu = source("bafu", "nexus")
    steps = account_advice(AccountStart(start="terminal", screen=SCREEN), needed=[bafu]).steps
    assert SCREEN in steps and "`ecosemantic setup bafu`" in steps


def test_a_terminal_without_a_screen_gets_the_headless_steps() -> None:
    headless = account_advice(AccountStart(start="headless"))
    assert account_advice(AccountStart(start="terminal")).steps == headless.steps
    assert "ecosemantic setup" in headless.steps and "127.0.0.1" not in headless.steps


def test_the_headless_steps_name_the_variables_of_the_kinds_needed() -> None:
    ecoinvent = source("ecoinvent", "ecoinvent")
    steps = account_advice(AccountStart(), needed=[ecoinvent]).steps
    assert "`ecosemantic setup ecoinvent <version>`" in steps
    assert "EI_USERNAME and EI_PASSWORD" in steps and "NEXUS_" not in steps
    every = account_advice(AccountStart()).steps
    assert "EI_USERNAME" in every and "NEXUS_USERNAME" in every and "NEXUS_TOKEN" in every


def test_no_advice_uses_an_alarming_word() -> None:
    for start in get_args(Start):
        for reached in (None, *get_args(Reach)):
            advice = account_advice(AccountStart(start=start, screen=SCREEN), reached)
            assert advice.said() == f"{advice.why} {advice.steps}"
            words = set(re.findall(r"[a-z]+", advice.said().lower()))
            assert not {"risk", "attack", "danger", "insecure", "warning"} & words


def test_the_entry_on_this_computer_carries_no_advice() -> None:
    entry = entry_for(AccountStart(start="tray", screen=SCREEN), "here")
    assert entry.model_dump() == {
        "reach": "here",
        "why": None,
        "steps": None,
        "page": None,
        "here": True,
    }


def test_the_entry_elsewhere_carries_the_advice() -> None:
    start = AccountStart(start="terminal", screen=SCREEN, page="https://me.bridge.ecosemantic.com")
    for reached in get_args(Reach):
        if reached == "here":
            continue
        entry = entry_for(start, reached)
        advice = account_advice(start, reached)
        assert entry.reach == reached
        assert (entry.why, entry.steps) == (advice.why, advice.steps)
        assert entry.here is False
        assert entry.page == start.page
