"""The states an engine's tunnel reports, which the page's health hands on and a tray shows."""

from __future__ import annotations

from typing import Literal

BridgeState = Literal["off", "connecting", "connected", "offline", "signed-out", "stopped"]
SIGNED_OUT_STATES: tuple[BridgeState, ...] = ("signed-out", "stopped")
