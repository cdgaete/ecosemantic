"""Scan a tree for a private key, a published service's token, a path under a person's home, words
this machine forbids and values given in a file. Prints each finding as path:line: rule, never the
matched text, and exits 1 when there is one.

    python scripts/secret_scan.py TREE [--forbid WORD ...] [--secret-file FILE ...]
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

SYNTHETIC_HOMES = frozenset({"person"})

PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")

TOKEN = re.compile(
    r"ghp_[A-Za-z0-9]{16,}"
    r"|gho_[A-Za-z0-9]{16,}"
    r"|ghs_[A-Za-z0-9]{16,}"
    r"|github_pat_[A-Za-z0-9_]{16,}"
    r"|sk-ant-[A-Za-z0-9_-]{16,}"
    r"|AKIA[A-Z0-9]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{16,}"
    r"|pypi-AgE[A-Za-z0-9_-]{16,}"
    r"|npm_[A-Za-z0-9]{36}"
)

HOME = re.compile(r"(?:/home/|/Users/|C:\\Users\\)(?P<name>[a-z][\w.-]*)")


@dataclass(frozen=True)
class Finding:
    """One line of one file that a rule matched."""

    path: Path
    line: int
    rule: str


def _files(tree: Path) -> Iterator[Path]:
    for directory, names, files in os.walk(tree):
        names[:] = sorted(name for name in names if name != ".git")
        for name in sorted(files):
            yield Path(directory) / name


def _whole(word: str, line: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", line) is not None


def _matched(line: str, forbidden: Sequence[str], secrets: Sequence[str]) -> Iterator[str]:
    if PRIVATE_KEY.search(line):
        yield "private key"
    if TOKEN.search(line):
        yield "token"
    home = HOME.search(line)
    if home is not None and home["name"] not in SYNTHETIC_HOMES:
        yield "home path"
    if any(_whole(word, line) for word in forbidden):
        yield "forbidden word"
    if any(secret in line for secret in secrets):
        yield "secret"


def findings(tree: Path, forbidden: Sequence[str], secrets: Sequence[str]) -> list[Finding]:
    """Every line of every text file under tree that a rule matches, in path and line order."""
    found: list[Finding] = []
    for path in _files(tree):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            found.extend(
                Finding(path=path, line=number, rule=rule)
                for rule in _matched(line, forbidden, secrets)
            )
    return found


def main(argv: list[str] | None = None) -> int:
    """Print each finding under a tree with its count, and return 1 when there is one."""
    parser = argparse.ArgumentParser(
        description="Scan a tree for secrets, personal paths and forbidden words."
    )
    parser.add_argument("tree", type=Path)
    parser.add_argument("--forbid", action="append", default=[], metavar="WORD")
    parser.add_argument("--secret-file", action="append", default=[], type=Path, metavar="FILE")
    arguments = parser.parse_args(argv)
    secrets = [
        line.strip()
        for path in arguments.secret_file
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    found = findings(arguments.tree, arguments.forbid, secrets)
    for finding in found:
        print(f"{finding.path.relative_to(arguments.tree)}:{finding.line}: {finding.rule}")
    print(f"{len(found)} finding{'' if len(found) == 1 else 's'}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
