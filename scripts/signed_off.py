"""The Developer Certificate of Origin check a pull request passes: every commit after BASE up to
HEAD, merges left out, carries a `Signed-off-by` trailer naming its author as git records them.
Prints each commit that does not and exits 1 when there is one.

    python scripts/signed_off.py BASE HEAD
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

RECORD = "\x1e"
FIELD = "\x1f"


def unsigned(repository: Path, base: str, head: str) -> list[str]:
    """The commits after base up to head, oldest first, that their author did not sign off."""
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on PATH")
    log = subprocess.run(
        [
            git,
            "-C",
            str(repository),
            "log",
            "--reverse",
            "--no-merges",
            f"--format=%H{FIELD}%an <%ae>{FIELD}%B{RECORD}",
            f"{base}..{head}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    lacking = []
    for record in filter(str.strip, log.split(RECORD)):
        sha, author, body = record.strip("\n").split(FIELD, 2)
        if f"Signed-off-by: {author}" not in body.splitlines():
            lacking.append(sha)
    return lacking


def main() -> int:
    lacking = unsigned(Path.cwd(), sys.argv[1], sys.argv[2])
    for sha in lacking:
        print(f"{sha} carries no Signed-off-by naming its author")
    return 1 if lacking else 0


if __name__ == "__main__":
    raise SystemExit(main())
