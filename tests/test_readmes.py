"""Every command a README shows is one the installed commands hold, subcommands and flags."""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
READMES = (
    "README.md",
    "app/README.md",
    "core/README.md",
    "databases/README.md",
    "engine/README.md",
    "mcp/README.md",
    "view/README.md",
)
COMMANDS = ("ecosemantic", "ecosemantic-databases")
FENCES = ("```", "~~~")
SPAN = re.compile(r"`([^`]+)`")
COMMENT = re.compile(r"\s#.*$")
POSITIONALS = re.compile(r"^positional arguments:\n(.*?)(?=^\S|\Z)", re.MULTILINE | re.DOTALL)
SUBCOMMANDS = re.compile(r"\{([^{}]*)\}")
OPTION = re.compile(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)")


def shown(document: str) -> list[str]:
    """Answer every line of a document a command can be written on: a code block's line, or a
    code span's text."""
    lines: list[str] = []
    fenced = False
    for line in document.splitlines():
        if line.lstrip().startswith(FENCES):
            fenced = not fenced
            continue
        if fenced:
            lines.append(line)
        else:
            lines.extend(SPAN.findall(line))
    return lines


def words_of(line: str) -> list[str] | None:
    """Answer the words of a line that shows one of the commands, its comment and its prompt
    dropped, and nothing for any other line."""
    words = COMMENT.sub("", line).split()
    if words[:1] == ["$"]:
        words = words[1:]
    if not words or words[0] not in COMMANDS:
        return None
    return words


@functools.cache
def invocation(program: str) -> tuple[str, ...]:
    """Answer the words that run a command: its installed script, or the interpreter over the
    module behind it."""
    executable = shutil.which(program)
    if executable is not None:
        return (executable,)
    module = "ecosemantic.console" if program == "ecosemantic" else "ecosemantic.databases.cli"
    return (sys.executable, "-c", f"import sys; from {module} import main; sys.exit(main())")


@functools.cache
def help_text(path: tuple[str, ...]) -> str:
    """Answer what a command path answers `--help`, as the installed command prints it."""
    completed = subprocess.run(
        [*invocation(path[0]), *path[1:], "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, f"{' '.join(path)} --help fails: {completed.stderr}"
    return completed.stdout


def subcommands(path: tuple[str, ...]) -> set[str]:
    """Answer the subcommands a command path holds, as its help lists them as its arguments."""
    section = POSITIONALS.search(help_text(path))
    if section is None:
        return set()
    found = SUBCOMMANDS.search(section.group(1))
    if found is None:
        return set()
    return {name.strip() for name in found.group(1).split(",")}


def resolved(words: list[str]) -> tuple[tuple[str, ...], list[str], list[str]]:
    """Answer the command path the words name, the flags they use, and the words the path holds
    no subcommand for."""
    path = (words[0],)
    flags: list[str] = []
    unknown: list[str] = []
    rest = words[1:]
    while rest:
        word = rest.pop(0)
        if word.startswith("-"):
            flags.extend(OPTION.findall(word))
            if "=" not in word and rest and not rest[0].startswith("-"):
                rest.pop(0)
        elif word in subcommands(path):
            path += (word,)
        elif subcommands(path):
            unknown.append(word)
    return path, flags, unknown


def command_lines() -> list[tuple[str, str]]:
    """Answer each README and the line of it that shows one of the commands."""
    found: list[tuple[str, str]] = []
    for name in READMES:
        document = (REPOSITORY / name).read_text(encoding="utf-8")
        found.extend((name, line.strip()) for line in shown(document) if words_of(line))
    return found


def refusals() -> list[str]:
    """Answer each command path a README shows that refutes its own `--help`: a subcommand or a
    flag it names and the command does not hold."""
    found: list[str] = []
    for name, line in command_lines():
        path, flags, unknown = resolved(words_of(line) or [])
        held = help_text(path)
        named = " ".join(path)
        found.extend(f"{name}: `{named}` holds no subcommand {word} — {line}" for word in unknown)
        found.extend(
            f"{name}: `{named}` holds no {flag} — {line}" for flag in flags if flag not in held
        )
    return found


def test_every_command_a_readme_shows_exists() -> None:
    """Run each command path a README shows with `--help`, and find there every subcommand and
    flag the line names."""
    assert command_lines(), "no README shows a command"
    refused = refusals()
    assert not refused, "\n".join(refused)


def test_no_document_says_a_database_waits_for_a_restart() -> None:
    # every running server serves a finished install at once
    stale = [
        path
        for path in REPOSITORY.rglob("*.md")
        if ".venv" not in path.parts
        and "node_modules" not in path.parts
        and "next start" in path.read_text(encoding="utf-8")
    ]
    assert stale == []
