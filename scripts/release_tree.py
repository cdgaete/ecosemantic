"""Write the package repository's committed tree into a new repository as one commit, refusing a
directory that already holds files and a tree the secret scan names.

    python scripts/release_tree.py OUT --author "NAME <EMAIL>" [--forbid WORD ...]
        [--secret-file FILE ...] [--onto URL --branch NAME]
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from collections.abc import Sequence
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPOSITORY))

GIT = str(shutil.which("git"))

NAMED = re.compile(r"(?P<name>[^<>]*)<(?P<email>[^<>]+)>")
RELEASE_MESSAGE = re.compile(r"EcoSemantic \d+\.\d+\.\d+")


def _git_anywhere(*arguments: str, identity: tuple[str, str] | None = None) -> bytes:
    """Run git with no global or system configuration, carrying identity when given; a failed
    call ends the build naming the command and git's stderr."""
    environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    if identity is not None:
        name, email = identity
        environment |= {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
    try:
        return subprocess.run(
            [GIT, *arguments], capture_output=True, env=environment, check=True
        ).stdout
    except subprocess.CalledProcessError as error:
        command = " ".join([GIT, *arguments])
        raise SystemExit(f"{command}: {error.stderr.decode().strip()}") from error


def _git(tree: Path, *arguments: str, identity: tuple[str, str] | None = None) -> bytes:
    """Run git in tree with no global or system configuration, carrying identity when given."""
    return _git_anywhere("-C", str(tree), *arguments, identity=identity)


def _output(tree: Path, *arguments: str) -> str:
    """Standard output of git in tree, stripped."""
    return _git(tree, *arguments).decode().strip()


def _holds_a_file(out: Path) -> bool:
    """Whether out exists and holds a file anywhere under it."""
    if out.is_file():
        return True
    return out.is_dir() and any(path.is_file() for path in out.rglob("*"))


def _named(author: str) -> tuple[str, str]:
    """The name and the e-mail address of an author written as NAME <EMAIL>."""
    found = NAMED.search(author)
    if found is None:
        raise SystemExit(f"{author!r} is not written as NAME <EMAIL>")
    return found["name"].strip(), found["email"].strip()


def _version(source: Path) -> str:
    """The version app/pyproject.toml states."""
    stated = tomllib.loads((source / "app" / "pyproject.toml").read_text(encoding="utf-8"))
    return str(stated["project"]["version"])


def _write_head(source: Path, out: Path) -> None:
    """Extract git archive HEAD of source into out."""
    with tarfile.open(fileobj=io.BytesIO(_git(source, "archive", "--format=tar", "HEAD"))) as tree:
        tree.extractall(out, filter="data")


def _remote_has_branch(url: str, name: str) -> bool:
    """Whether url holds a branch named name."""
    return bool(_git_anywhere("ls-remote", "--heads", url, f"refs/heads/{name}"))


def _clone(url: str, branch: str, out: Path) -> None:
    """Clone url's branch into out, creating branch from main when it does not exist."""
    if _remote_has_branch(url, branch):
        _git_anywhere("clone", "--quiet", "--branch", branch, url, str(out))
    else:
        _git_anywhere("clone", "--quiet", "--branch", "main", url, str(out))
        _git(out, "checkout", "--quiet", "-b", branch)


def _replace_tree(source: Path, out: Path) -> None:
    """Remove out's tracked files, keeping .git, and extract source's HEAD into out."""
    _git(out, "rm", "-r", "-q", "--cached", ".")
    for path in out.iterdir():
        if path.name == ".git":
            continue
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    _write_head(source, out)


def _refuse_unwritten_tip(out: Path, branch: str, tip: str, person: tuple[str, str]) -> None:
    """End the build when tip is not a release commit authored by person."""
    name, email = person
    author_name = _output(out, "log", "-1", "--format=%an", tip)
    author_email = _output(out, "log", "-1", "--format=%ae", tip)
    message = _output(out, "log", "-1", "--format=%B", tip)
    if author_name == name and author_email == email and RELEASE_MESSAGE.fullmatch(message):
        return
    tip_author = _output(out, "log", "-1", "--format=%an <%ae>", tip)
    tip_subject = _output(out, "log", "-1", "--format=%s", tip)
    print(
        f"{branch} tips at {tip} by {tip_author} as {tip_subject!r}; "
        "it is not a commit this script wrote; bring the change into the package repository first",
        file=sys.stderr,
    )
    raise SystemExit(1)


def build(
    source: Path,
    out: Path,
    author: str,
    forbidden: Sequence[str],
    secrets: Sequence[str],
    *,
    onto: str | None = None,
    branch: str | None = None,
) -> str:
    """Write source's HEAD into out as one commit made by author, answering its hash; with onto
    and branch, write it on a clone of onto's branch and refuse a tip author did not write; ends
    the build when out holds files or the scan names something in the tree it wrote."""
    from scripts.secret_scan import findings

    if _holds_a_file(out):
        print(f"{out} holds files; the release tree is written where none are", file=sys.stderr)
        raise SystemExit(1)
    person = _named(author)
    if onto is None:
        out.mkdir(parents=True, exist_ok=True)
        _write_head(source, out)
        found = findings(out, forbidden, secrets)
        if found:
            for finding in found:
                print(f"{finding.path.relative_to(out).as_posix()}:{finding.line}: {finding.rule}")
            raise SystemExit(1)
        _git(out, "init", "--quiet", "--initial-branch=main")
        _git(out, "add", "--all")
        _git(out, "commit", "--quiet", "-m", f"EcoSemantic {_version(source)}", identity=person)
        return _output(out, "rev-parse", "HEAD")
    if branch is None:
        raise SystemExit("--onto and --branch are given together")
    out.mkdir(parents=True, exist_ok=True)
    _clone(onto, branch, out)
    tip = _output(out, "rev-parse", "HEAD")
    _refuse_unwritten_tip(out, branch, tip, person)
    _replace_tree(source, out)
    found = findings(out, forbidden, secrets)
    if found:
        for finding in found:
            print(f"{finding.path.relative_to(out).as_posix()}:{finding.line}: {finding.rule}")
        raise SystemExit(1)
    _git(out, "add", "--all")
    if not _git(out, "status", "--porcelain").strip():
        print(f"{branch} already holds HEAD's tree; nothing to commit")
        return tip
    _git(out, "commit", "--quiet", "-m", f"EcoSemantic {_version(source)}", identity=person)
    return _output(out, "rev-parse", "HEAD")


def main(argv: list[str] | None = None) -> int:
    """Write the package repository's committed tree into OUT, printing its commit and count."""
    parser = argparse.ArgumentParser(
        description="Write the package repository's committed tree into a new repository."
    )
    parser.add_argument("out", type=Path)
    parser.add_argument("--author", required=True, metavar="'NAME <EMAIL>'")
    parser.add_argument("--forbid", action="append", default=[], metavar="WORD")
    parser.add_argument("--secret-file", action="append", default=[], type=Path, metavar="FILE")
    parser.add_argument("--onto", metavar="URL")
    parser.add_argument("--branch", metavar="NAME")
    arguments = parser.parse_args(argv)
    if (arguments.onto is None) != (arguments.branch is None):
        parser.error("--onto and --branch are given together")
    secrets = [
        line.strip()
        for path in arguments.secret_file
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    commit = build(
        source=REPOSITORY,
        out=arguments.out,
        author=arguments.author,
        forbidden=arguments.forbid,
        secrets=secrets,
        onto=arguments.onto,
        branch=arguments.branch,
    )
    files = len(_output(arguments.out, "ls-files").splitlines())
    print(f"{commit} {files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
