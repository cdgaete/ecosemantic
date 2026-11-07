from __future__ import annotations

import pytest

from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.menu import MenuItem, StartAtLogin, menu_for, title

PAGE = "https://ana.bridge.example"
CONNECTOR = "https://bridge.example/mcp"


def state(
    kind: str,
    bridge: str,
    *,
    bridge_on: bool = True,
    handle: str | None = None,
    addresses: bool = True,
    pending: bool = False,
) -> EngineState:
    """An engine state of this kind and bridge, with the person's setting, whether a bridge command
    runs, and, when the test wants them, the addresses a bridged health carries."""
    return EngineState(
        kind=kind,
        bridge=bridge,
        bridge_on=bridge_on,
        pending=pending,
        handle=handle,
        page=PAGE if addresses else None,
        connector=CONNECTOR if addresses else None,
    )


CASES = {
    "starting": (
        state("starting", "connecting", addresses=False),
        [
            MenuItem("Starting…"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
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
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
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
            MenuItem("Connect to the bridge", "connect"),
            MenuItem("Sign in…", "sign-in"),
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Start the engine", "start-engine"),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "stopped with the bridge on": (
        state("stopped", "off", bridge_on=True, addresses=False),
        [
            MenuItem("Stopped"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
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
            MenuItem("Start at login", "start-at-login", checked=False),
            MenuItem("Open the logs", "open-logs"),
            MenuItem("Quit", "quit"),
        ],
    ),
    "failed with the bridge on": (
        state("failed", "off", bridge_on=True, addresses=False),
        [
            MenuItem("Failed — see the logs"),
            MenuItem("Open my page", "open-page", enabled=False),
            MenuItem("Copy the connector address", "copy-connector", enabled=False),
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


def test_start_at_login_shows_windows_own_switch() -> None:
    given, _ = CASES["connected"]
    plain = menu_for(given, StartAtLogin(enabled=True))
    assert plain[5] == MenuItem("Start at login", "start-at-login", checked=True)
    turned_off = menu_for(given, StartAtLogin(enabled=True, turned_off_by_windows=True))
    assert turned_off[5] == MenuItem(
        "Start at login (turned off in Windows settings)",
        "start-at-login",
        checked=False,
        enabled=False,
    )


def test_the_title_names_the_product_and_the_first_line() -> None:
    connected, _ = CASES["connected"]
    assert title(connected) == "EcoSemantic Engine — Connected as ana"
    stopped, _ = CASES["stopped"]
    assert title(stopped) == "EcoSemantic Engine — Stopped"
