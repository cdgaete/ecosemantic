"""The rules that hold text as UTF-8 and line endings as LF on every platform."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))


def test_text_checks_out_with_lf() -> None:
    lines = (REPOSITORY / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "* text=auto eol=lf" in lines


def test_the_suite_raises_on_a_default_encoding() -> None:
    filterwarnings = PYPROJECT["tool"]["pytest"]["ini_options"]["filterwarnings"]
    assert "error::EncodingWarning" in filterwarnings
    check = (REPOSITORY / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert "PYTHONWARNDEFAULTENCODING=1" in check


def test_ruff_flags_an_unspecified_encoding() -> None:
    selected = PYPROJECT["tool"]["ruff"]["lint"]["select"]
    assert "PLW1514" in selected
