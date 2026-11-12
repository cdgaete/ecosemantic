from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.members import distributions

REPOSITORY = Path(__file__).resolve().parents[1]


def test_the_distributions_are_the_workspace_s_members() -> None:
    root = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    named = tuple(
        tomllib.loads((REPOSITORY / directory / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["name"]
        for directory in root["tool"]["uv"]["workspace"]["members"]
    )
    assert distributions() == named
    assert len(distributions()) == 7
    assert "ecosemantic-relay" in distributions()
