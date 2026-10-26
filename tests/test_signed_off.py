from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts.signed_off import unsigned


def git(repo: Path, *args: str) -> str:
    command = [str(shutil.which("git")), "-C", str(repo), *args]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout.strip()


def commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def test_a_commit_without_its_author_s_sign_off_is_named(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Ada Lovelace")
    git(tmp_path, "config", "user.email", "ada@lab.example")
    base = commit(tmp_path, "a", "Start")
    signed = commit(tmp_path, "b", "Add b\n\nSigned-off-by: Ada Lovelace <ada@lab.example>")
    bare = commit(tmp_path, "c", "Add c")
    other = commit(tmp_path, "d", "Add d\n\nSigned-off-by: Someone Else <else@lab.example>")
    assert unsigned(tmp_path, base, other) == [bare, other]
    assert unsigned(tmp_path, base, signed) == []
