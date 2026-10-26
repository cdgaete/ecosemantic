"""The three in-chat panels: UI resources a host renders beside a tool's result."""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources

from fastmcp import FastMCP
from fastmcp.apps.config import AppConfig, ResourceCSP
from fastmcp.utilities.mime import UI_MIME_TYPE

PANELS: dict[str, str] = {
    "contribution": "ui://ecosemantic/contribution.html",
    "impact": "ui://ecosemantic/impact.html",
    "inventory": "ui://ecosemantic/inventory.html",
}


def panel(name: str) -> AppConfig:
    """The app configuration a tool carries: its resource and a policy that loads nothing."""
    return AppConfig(
        resource_uri=PANELS[name], csp=ResourceCSP(connect_domains=[], resource_domains=[])
    )


def html(name: str) -> str:
    """The panel's document, read from package data."""
    return (resources.files("ecosemantic.mcp") / "panels" / f"{name}.html").read_text(
        encoding="utf-8"
    )


def _reader(name: str) -> Callable[[], str]:
    def read() -> str:
        return html(name)

    read.__name__ = f"{name}_panel"
    return read


CARRIED_BY: dict[str, str] = {
    "contribution": "contribution_analysis",
    "impact": "calculate_impact",
    "inventory": "calculate_inventory",
}


def register(server: FastMCP) -> None:
    """Register the three resources, so a host can fetch what the tools name."""
    for name, uri in PANELS.items():
        server.resource(
            uri,
            name=f"{name}_panel",
            mime_type=UI_MIME_TYPE,
            description=(
                f"A figure that carries no data: the host fills it with the result of "
                f"{CARRIED_BY[name]}, the call beside it, and renders it in the chat."
            ),
        )(_reader(name))
