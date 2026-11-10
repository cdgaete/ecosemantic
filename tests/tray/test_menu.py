from __future__ import annotations

import pytest

from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.menu import (
    MenuItem,
    StartAtLogin,
    checked_of,
    clickable,
    menu_for,
    title,
)
from tests.tray.fakes import SCREEN

PAGE = "https://ana.bridge.example"
CONNECTOR = "https://bridge.example/mcp"


def state(
    kind: str,
    bridge: str,
    *,
    bridge_on: bool = True,
    signed_in: bool = False,
    handle: str | None = None,
    addresses: bool = True,
    pending: bool = False,
    accounts: str | None = SCREEN,
) -> EngineState:
    """An engine state of this kind and bridge, with the person's setting, whether this folder holds
    a credential, whether a bridge command runs, the addresses a bridged health carries when the
    test wants them, and the accounts screen its health names."""
    return EngineState(
        kind=kind,
        bridge=bridge,
        bridge_on=bridge_on,
        signed_in=signed_in,
        pending=pending,
        handle=handle,
        page=PAGE if addresses else None,
        connector=CONNECTOR if addresses else None,
        accounts=accounts,
    )


CASES = {
    "starting": (
        state("starting", "connecting", signed_in=True, addresses=False),
        [
            MenuItem("Starting…"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "starting without the bridge": (
        state("starting", "off", bridge_on=False, addresses=False),
        [
            MenuItem("Starting…"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "connected": (
        state("running", "connected", handle="ana"),
        [
            MenuItem("Connected as ana"),
            MenuItem("Open my page", "open-page"),
            MenuItem("Copy the connector address", "copy-connector"),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "offline": (
        state("running", "offline"),
        [
            MenuItem("Offline — reconnecting"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector"),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "connecting": (
        state("running", "connecting"),
        [
            MenuItem("Offline — reconnecting"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector"),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "signed out": (
        state("running", "signed-out"),
        [
            MenuItem("Signed out"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector"),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "relay stopped": (
        state("running", "stopped"),
        [
            MenuItem("Signed out"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector"),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "bridge off": (
        state("running", "off", bridge_on=False, addresses=False),
        [
            MenuItem("The bridge is off"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "bridge off with a credential": (
        state("running", "off", bridge_on=False, signed_in=True, addresses=False),
        [
            MenuItem("The bridge is off"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "stopped": (
        state("stopped", "off", bridge_on=False, addresses=False),
        [
            MenuItem("Stopped"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Start the engine", "start-engine"),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "stopped with the bridge on": (
        state("stopped", "off", bridge_on=True, signed_in=True, addresses=False),
        [
            MenuItem("Stopped"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Start the engine", "start-engine"),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "failed": (
        state("failed", "off", bridge_on=False, addresses=False),
        [
            MenuItem("Failed — see the logs"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Start the engine", "start-engine"),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "a bridge command runs": (
        state("running", "off", bridge_on=False, addresses=False, pending=True),
        [
            MenuItem("The bridge is off"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "a bridge command runs while the engine is stopped": (
        state("stopped", "off", bridge_on=False, addresses=False, pending=True),
        [
            MenuItem("Stopped"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "failed with the bridge on": (
        state("failed", "off", bridge_on=True, signed_in=True, addresses=False),
        [
            MenuItem("Failed — see the logs"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
            MenuItem("Database accounts…", "accounts", enabled=False),
            MenuItem("Disconnect from the bridge", "disconnect"),
            MenuItem("Sign out", "sign-out"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Start the engine", "start-engine"),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_each_state_s_first_line_and_items(name: str) -> None:
    given, expected = CASES[name]
    assert menu_for(given, StartAtLogin(enabled=False)) == expected


@pytest.mark.parametrize(
    "no_credential",
    [
        state("starting", "connecting", addresses=False),
        state("stopped", "off", bridge_on=True, addresses=False),
        state("failed", "off", bridge_on=True, addresses=False),
    ],
)
def test_a_state_with_no_credential_offers_signing_in(no_credential: EngineState) -> None:
    offered = [
        item
        for item in menu_for(no_credential, StartAtLogin(enabled=False))
        if item.action in ("sign-in", "sign-out")
    ]
    assert offered == [MenuItem("Sign in…", "sign-in")]


@pytest.mark.parametrize(
    ("signed_in", "offered"),
    [(True, MenuItem("Sign out", "sign-out")), (False, MenuItem("Sign in…", "sign-in"))],
)
def test_a_bridge_that_is_off_offers_what_the_credential_store_holds(
    signed_in: bool, offered: MenuItem
) -> None:
    running = state("running", "off", bridge_on=False, signed_in=signed_in, addresses=False)
    assert [
        item
        for item in menu_for(running, StartAtLogin(enabled=False))
        if item.action in ("sign-in", "sign-out")
    ] == [offered]


@pytest.mark.parametrize(
    ("kind", "bridge"),
    [
        ("running", "connected"),
        ("running", "off"),
        ("running", "signed-out"),
        ("starting", "connecting"),
        ("stopped", "off"),
        ("failed", "off"),
    ],
)
def test_database_accounts_follows_the_connector_and_needs_a_running_engine(
    kind: str, bridge: str
) -> None:
    given = state(kind, bridge)
    items = menu_for(given, StartAtLogin(enabled=False))
    connector = next(number for number, item in enumerate(items) if item.action == "copy-connector")
    assert items[connector + 1] == MenuItem(
        "Database accounts…", "accounts", enabled=kind == "running"
    )


def test_a_health_without_accounts_disables_the_item() -> None:
    given = state("running", "off", accounts=None)
    items = menu_for(given, StartAtLogin(enabled=False))
    connector = next(number for number, item in enumerate(items) if item.action == "copy-connector")
    assert items[connector + 1] == MenuItem("Database accounts…", "accounts", enabled=False)


def test_start_at_login_shows_windows_own_switch() -> None:
    given, _ = CASES["connected"]
    plain = menu_for(given, StartAtLogin(enabled=True))
    assert plain[6] == MenuItem("Start at login", "start-at-login", checked=True)
    turned_off = menu_for(given, StartAtLogin(enabled=True, turned_off_by_windows=True))
    assert turned_off[6] == MenuItem(
        "Start at login (turned off in Windows settings)",
        "start-at-login",
        checked=False,
        enabled=False,
    )


def test_pystray_is_told_which_lines_are_ticked_by_a_callable() -> None:
    """pystray 0.19.5 reads `checked` through `_assert_callable`: None passes and is replaced by a
    callable answering None, a callable passes, and anything else raises `ValueError`. A line
    that is not ticked therefore answers False from a callable, and a line that cannot be ticked
    passes None."""
    unticked = checked_of(MenuItem("Start at login", "start-at-login", checked=False))
    assert callable(unticked) and unticked(None) is False
    ticked = checked_of(MenuItem("Start at login", "start-at-login", checked=True))
    assert callable(ticked) and ticked(None) is True
    assert checked_of(MenuItem("Quit", "quit")) is None


def test_every_line_of_every_state_is_what_pystray_accepts() -> None:
    """Each line's `checked` and `enabled` obey the rule pystray's own `MenuItem.__init__` applies:
    `checked` is a callable or None — anything else is a ValueError — and `enabled` is a value or a
    callable, which `_wrap` returns as the callable it makes. That rule is stated here rather than
    imported: importing pystray on Linux starts Xlib, and a machine with no display raises
    `DisplayNameError` before `pystray._base` is reached, which is why the tray's Linux tests reach
    `menu.py` alone."""
    for name, (given, _) in CASES.items():
        for item in menu_for(given, StartAtLogin(enabled=False)):
            checked = checked_of(item)
            assert checked is None or callable(checked), (name, item, checked)
            enabled = clickable(item)
            assert callable(enabled) or isinstance(enabled, bool), (name, item, enabled)


def test_the_title_names_the_product_and_the_first_line() -> None:
    connected, _ = CASES["connected"]
    assert title(connected) == "EcoSemantic Engine — Connected as ana"
    stopped, _ = CASES["stopped"]
    assert title(stopped) == "EcoSemantic Engine — Stopped"
