"""The core's distributions: the members the workspace lists, and the name each one states."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def member_directories() -> tuple[str, ...]:
    """Every directory `pyproject.toml` lists as a workspace member, in the order it lists them."""
    root = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    return tuple(root["tool"]["uv"]["workspace"]["members"])


def distributions() -> tuple[str, ...]:
    """The `[project] name` of every member, in the order `pyproject.toml` lists them."""
    return tuple(
        tomllib.loads((REPOSITORY / directory / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["name"]
        for directory in member_directories()
    )
