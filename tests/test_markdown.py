"""No Markdown document of the repository wraps a paragraph or a list item across two lines."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
GIT = str(shutil.which("git"))
FENCES = ("```", "~~~")
LIST_ITEM = re.compile(r"\s*(?:[-*+]|\d+[.)])\s+")
DEFINITION = re.compile(r"\s*\[[^]]+\]:\s")


def hard_wraps(text: str) -> list[int]:
    """Answer the number of each line whose paragraph or list item runs on to the next line."""
    lines = text.splitlines()
    found: list[int] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(FENCES):
            in_fence = not in_fence
            continue
        if in_fence or not carries_prose(line):
            continue
        following = lines[number] if number < len(lines) else ""
        if not opens_block(following):
            found.append(number)
    return found


def carries_prose(line: str) -> bool:
    """Answer whether the line carries a paragraph's or a list item's text."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(FENCES) or stripped[0] in "#><|":
        return False
    return DEFINITION.match(line) is None


def opens_block(line: str) -> bool:
    """Answer whether the line is blank, opens a block of its own, or starts a list item."""
    if not line.strip() or not carries_prose(line):
        return True
    return LIST_ITEM.match(line) is not None


def tracked_markdown() -> list[str]:
    """Answer the repository's tracked Markdown files, relative to its root."""
    completed = subprocess.run(
        [GIT, "ls-files", "*.md"], cwd=REPOSITORY, capture_output=True, text=True, check=True
    )
    return completed.stdout.split()


def test_a_paragraph_on_two_lines_is_a_hard_wrap() -> None:
    text = "A heading\n\nOne sentence, and\nits second line.\n\nAnother.\n"
    assert hard_wraps(text) == [3]


def test_a_list_item_continued_on_the_next_line_is_a_hard_wrap() -> None:
    text = "1. **Install it.** One line,\n   and its second.\n\n2. Another.\n"
    assert hard_wraps(text) == [1]


def test_code_blocks_and_tables_keep_their_lines() -> None:
    text = (
        "```\n"
        "first line\n"
        "second line\n"
        "```\n"
        "\n"
        "| Row | Long |\n"
        "| --- | ---- |\n"
        "| 1   | 2    |\n"
        "\n"
        "<details>\n"
        "<summary>More</summary>\n"
        "</details>\n"
    )
    assert hard_wraps(text) == []


def test_a_link_reference_definition_keeps_its_line() -> None:
    text = "See the [FAQ].\n\n[FAQ]: https://example.org/faq\n[homepage]: https://example.org\n"
    assert hard_wraps(text) == []


def test_a_nested_list_item_starts_a_new_block() -> None:
    text = "- First item.\n  - Nested item.\n"
    assert hard_wraps(text) == []


@pytest.mark.parametrize("name", tracked_markdown())
def test_no_markdown_is_hard_wrapped(name: str) -> None:
    text = (REPOSITORY / name).read_text(encoding="utf-8")
    wraps = hard_wraps(text)
    assert not wraps, f"{name} continues on the next line at {wraps}"
