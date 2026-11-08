"""The tray's menu: the line it opens with, what a state offers, and what Windows' own
start-at-login switch shows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from ecosemantic.bridge.state import SIGNED_OUT_STATES
from ecosemantic.tray.engine import EngineState
from ecosemantic.tray.home import APP

Action = Literal[
    "open-page",
    "copy-connector",
    "connect",
    "disconnect",
    "sign-in",
    "sign-out",
    "start-at-login",
    "open-logs",
    "start-engine",
    "quit",
]
SIGNING = ("connected", "offline", "connecting")


@dataclass(frozen=True)
class MenuItem:
    """One line of the menu: what it reads, what it does, whether it is ticked, and whether it can
    be chosen. The first line does nothing and has no action."""

    text: str
    action: Action | None = None
    checked: bool | None = field(default=None, kw_only=True)
    enabled: bool = field(default=True, kw_only=True)


def checked_of(item: MenuItem) -> Callable[[object], bool | None] | None:
    """What pystray's `MenuItem` takes as `checked` for this line: a callable answering whether it
    is ticked, or None for a line pystray draws as one that cannot be. pystray reads a value in that
    argument as an error, so a line that is not ticked answers False from a callable."""
    if item.checked is None:
        return None
    value = item.checked
    return lambda _: value


def clickable(item: MenuItem) -> bool:
    """Whether pystray should let this line be chosen: an item with no action does nothing."""
    return item.enabled and item.action is not None


@dataclass(frozen=True)
class StartAtLogin:
    """Whether the person starts the tray at login, and whether Windows' own switch turned that
    off."""

    enabled: bool
    turned_off_by_windows: bool = field(default=False, kw_only=True)


def first_line(state: EngineState) -> str:
    """What the menu opens with: the engine and its tunnel in one line. A bridge that is connecting
    cannot be used yet, so it reads as offline; a bridge whose relay stopped was refused its
    credential, so it reads as signed out."""
    if state.kind == "starting":
        return "Starting…"
    if state.kind == "stopped":
        return "Stopped"
    if state.kind == "failed":
        return "Failed — see the logs"
    if state.bridge == "connected":
        return f"Connected as {state.handle}"
    if state.bridge in ("offline", "connecting"):
        return "Offline — reconnecting"
    if state.bridge in SIGNED_OUT_STATES:
        return "Signed out"
    return "The bridge is off"


def title(state: EngineState) -> str:
    """What the icon's tooltip reads: the product, then the line the menu opens with."""
    return f"{APP} — {first_line(state)}"


def menu_for(state: EngineState, login: StartAtLogin) -> list[MenuItem]:
    """The menu one state and Windows' switch offer: the state first, then the addresses while
    there are some, then the bridge's and the engine's actions, then the logs and quitting. The
    bridge's own actions follow the person's setting, and which way a credential stands when the
    engine's health reports one; a bridge command that runs is offered none of them."""
    connected = state.kind == "running" and state.bridge == "connected"
    items = [MenuItem(first_line(state))]
    items.append(
        MenuItem(
            "Open my page",
            "open-page",
            enabled=connected and state.page is not None,
        )
    )
    items.append(
        MenuItem(
            "Copy the connector address",
            "copy-connector",
            enabled=state.connector is not None,
        )
    )
    if not state.pending:
        if state.bridge_on:
            items.append(MenuItem("Disconnect from the bridge", "disconnect"))
        else:
            items.append(MenuItem("Connect to the bridge", "connect"))
        if _signed(state):
            items.append(MenuItem("Sign out", "sign-out"))
        else:
            items.append(MenuItem("Sign in…", "sign-in"))
    if login.turned_off_by_windows:
        items.append(
            MenuItem(
                "Start at login (turned off in Windows settings)",
                "start-at-login",
                checked=False,
                enabled=False,
            )
        )
    else:
        items.append(MenuItem("Start at login", "start-at-login", checked=login.enabled))
    if state.kind in ("stopped", "failed") and not state.pending:
        items.append(MenuItem("Start the engine", "start-engine"))
    items.append(MenuItem("Open the logs", "open-logs"))
    items.append(MenuItem("Quit", "quit"))
    return items


def _signed(state: EngineState) -> bool:
    """Whether the menu offers signing out: what the engine's health reports while it serves the
    bridge, and otherwise what this folder's credential store holds, since a bridge that is off, and
    starting, stopped and failed states, report none."""
    if state.kind == "running" and state.bridge != "off":
        return state.bridge in SIGNING
    return state.signed_in
