from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from scripts.release_tree import build, main

GIT = str(shutil.which("git"))
AUTHOR = "Ada Example <ada@example.org>"


def git(tree: Path, *arguments: str) -> str:
    """Run git in tree as a fixed identity, answering its standard output."""
    completed = subprocess.run(
        [
            GIT,
            "-C",
            str(tree),
            "-c",
            "user.name=Ada Example",
            "-c",
            "user.email=ada@example.org",
            "-c",
            "commit.gpgsign=false",
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def source_tree(tmp_path: Path) -> Path:
    """A repository of two commits holding a version and one file per commit."""
    root = tmp_path / "source"
    (root / "app").mkdir(parents=True)
    git(root, "init", "-q")
    (root / "app" / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    (root / "README.md").write_text("# Example\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "first")
    (root / "notes").mkdir()
    (root / "notes" / "one.md").write_text("one\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "second")
    return root


def test_the_tree_is_one_commit_of_head_s_files(tmp_path: Path) -> None:
    source = source_tree(tmp_path)
    out = tmp_path / "out"
    commit = build(source=source, out=out, author=AUTHOR, forbidden=[], secrets=[])
    assert commit == git(out, "rev-parse", "HEAD").strip()
    assert len(git(out, "log", "--oneline").splitlines()) == 1
    assert sorted(git(out, "ls-files").split()) == sorted(git(source, "ls-files").split())
    assert git(out, "log", "-1", "--format=%an <%ae>%n%cn <%ce>").splitlines() == [AUTHOR, AUTHOR]
    assert git(out, "log", "-1", "--format=%s").strip() == "EcoSemantic 1.2.3"
    assert git(out, "log", "-1", "--format=%b").strip() == ""
    assert git(out, "remote").strip() == ""


def test_the_tree_is_head_s_not_the_working_tree_s(tmp_path: Path) -> None:
    source = source_tree(tmp_path)
    (source / "notes" / "one.md").unlink()
    (source / "draft.md").write_text("uncommitted\n", encoding="utf-8")
    out = tmp_path / "out"
    build(source=source, out=out, author=AUTHOR, forbidden=[], secrets=[])
    assert (out / "notes" / "one.md").read_text(encoding="utf-8") == "one\n"
    assert not (out / "draft.md").exists()


def test_a_directory_that_holds_files_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = source_tree(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "kept.md").write_text("kept\n", encoding="utf-8")
    with pytest.raises(SystemExit) as ending:
        build(source=source, out=out, author=AUTHOR, forbidden=[], secrets=[])
    assert ending.value.code == 1
    assert [path.name for path in out.iterdir()] == ["kept.md"]
    assert (out / "kept.md").read_text(encoding="utf-8") == "kept\n"
    assert "holds files" in capsys.readouterr().err


def test_a_tree_the_scan_refuses_ends_the_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = source_tree(tmp_path)
    (source / "notes" / "two.md").write_text("a northwind file\n", encoding="utf-8")
    git(source, "add", "--all")
    git(source, "commit", "-q", "-m", "third")
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ending:
        build(source=source, out=out, author=AUTHOR, forbidden=["northwind"], secrets=[])
    assert ending.value.code == 1
    assert not (out / ".git").exists()
    assert "notes/two.md:1: forbidden word" in capsys.readouterr().out


def test_main_prints_the_commit_and_the_file_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    # a word made now, which no committed file can hold
    absent = uuid.uuid4().hex
    assert main([str(out), "--author", AUTHOR, "--forbid", absent]) == 0
    printed = capsys.readouterr().out
    assert git(out, "rev-parse", "HEAD").strip() in printed
    assert f"{len(git(out, 'ls-files').splitlines())} files" in printed
