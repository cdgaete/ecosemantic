"""The three task guides: Markdown resources an agent reads before the task each names, each a
short checklist with a worked example on the fixture database."""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources

from fastmcp import FastMCP

GUIDES: dict[str, str] = {
    "building-a-model": "guide://ecosemantic/building-a-model",
    "interpreting-a-result": "guide://ecosemantic/interpreting-a-result",
    "sensitivity-study": "guide://ecosemantic/sensitivity-study",
}

DESCRIPTIONS: dict[str, str] = {
    "building-a-model": "How to build a product system through the tools, in order.",
    "interpreting-a-result": (
        "How to read a score through contribution analysis and the inventory."
    ),
    "sensitivity-study": (
        "How to vary a model through parameters, cases and scenarios, and under Monte Carlo."
    ),
}


def text(name: str) -> str:
    """The guide's Markdown, read from package data."""
    return (resources.files("ecosemantic.mcp") / "guides" / f"{name}.md").read_text(
        encoding="utf-8"
    )


def _reader(name: str) -> Callable[[], str]:
    def read() -> str:
        return text(name)

    read.__name__ = f"{name.replace('-', '_')}_guide"
    return read


def register(server: FastMCP) -> None:
    """Register the three guides as resources."""
    for name, uri in GUIDES.items():
        server.resource(
            uri,
            name=f"{name.replace('-', '_')}_guide",
            mime_type="text/markdown",
            description=DESCRIPTIONS[name],
        )(_reader(name))
