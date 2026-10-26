from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath

import pytest

from scripts.release_tree import _git, _remote_has_branch, build, main
from scripts.secret_scan import main as scan

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
        encoding="utf-8",
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


def commit_as(tree: Path, message: str, name: str, email: str) -> None:
    """Commit tree's index as name <email>."""
    subprocess.run(
        [
            GIT,
            "-C",
            str(tree),
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-q",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def public_repo(
    tmp_path: Path,
    name: str = "Ada Example",
    email: str = "ada@example.org",
    message: str = "EcoSemantic 0.1.6",
) -> Path:
    """A bare repository whose main holds one commit by name <email> with message."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "README.md").write_text("public\n", encoding="utf-8")
    git(seed, "add", "--all")
    commit_as(seed, message, name, email)
    bare = tmp_path / "public.git"
    git(seed, "clone", "--bare", "--quiet", str(seed), str(bare))
    return bare


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


def test_a_scan_reports_posix_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "tree"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "two.md").write_text("a northwind file\n", encoding="utf-8")
    assert scan([str(root), "--forbid", "northwind"]) == 1
    assert f"{PurePosixPath('notes', 'two.md')}:1: forbidden word" in capsys.readouterr().out


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


def test_onto_writes_one_commit_on_top_of_the_branch(tmp_path: Path) -> None:
    source = source_tree(tmp_path)
    url = public_repo(tmp_path)
    old_tip = git(url, "rev-parse", "main").strip()
    out = tmp_path / "out"
    commit = build(
        source=source,
        out=out,
        author=AUTHOR,
        forbidden=[],
        secrets=[],
        onto=str(url),
        branch="main",
    )
    assert commit == git(out, "rev-parse", "HEAD").strip()
    assert git(out, "log", "-1", "--format=%P", "HEAD").strip() == old_tip
    assert sorted(git(out, "ls-files").split()) == sorted(git(source, "ls-files").split())
    assert git(out, "log", "-1", "--format=%s").strip() == "EcoSemantic 1.2.3"
    assert git(out, "log", "-1", "--format=%an <%ae>%n%cn <%ce>").splitlines() == [AUTHOR, AUTHOR]
    assert len(git(out, "log", "--oneline").splitlines()) == 2


def test_onto_refuses_a_branch_whose_tip_it_did_not_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = source_tree(tmp_path)
    url = public_repo(tmp_path, name="Someone Else", email="other@example.org", message="a fix")
    old_tip = git(url, "rev-parse", "main").strip()
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ending:
        build(
            source=source,
            out=out,
            author=AUTHOR,
            forbidden=[],
            secrets=[],
            onto=str(url),
            branch="main",
        )
    assert ending.value.code == 1
    assert old_tip in capsys.readouterr().err
    assert git(out, "rev-parse", "HEAD").strip() == old_tip


def test_onto_runs_the_scan_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = source_tree(tmp_path)
    (source / "notes" / "two.md").write_text("a northwind file\n", encoding="utf-8")
    git(source, "add", "--all")
    git(source, "commit", "-q", "-m", "third")
    url = public_repo(tmp_path)
    old_tip = git(url, "rev-parse", "main").strip()
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ending:
        build(
            source=source,
            out=out,
            author=AUTHOR,
            forbidden=["northwind"],
            secrets=[],
            onto=str(url),
            branch="main",
        )
    assert ending.value.code == 1
    assert "notes/two.md:1: forbidden word" in capsys.readouterr().out
    assert git(out, "rev-parse", "HEAD").strip() == old_tip


def test_onto_a_new_branch_starts_from_main(tmp_path: Path) -> None:
    source = source_tree(tmp_path)
    url = public_repo(tmp_path)
    old_tip = git(url, "rev-parse", "main").strip()
    out = tmp_path / "out"
    commit = build(
        source=source,
        out=out,
        author=AUTHOR,
        forbidden=[],
        secrets=[],
        onto=str(url),
        branch="platforms",
    )
    assert commit == git(out, "rev-parse", "HEAD").strip()
    assert git(out, "rev-parse", "--abbrev-ref", "HEAD").strip() == "platforms"
    assert git(out, "log", "-1", "--format=%P", "HEAD").strip() == old_tip
    assert git(out, "rev-parse", "main").strip() == old_tip
    assert len(git(out, "log", "--oneline").splitlines()) == 2


def test_onto_a_tree_equal_to_the_tip_commits_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = public_repo(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q")
    (source / "README.md").write_text("public\n", encoding="utf-8")
    git(source, "add", "--all")
    git(source, "commit", "-q", "-m", "first")
    old_tip = git(url, "rev-parse", "main").strip()
    out = tmp_path / "out"
    result = build(
        source=source,
        out=out,
        author=AUTHOR,
        forbidden=[],
        secrets=[],
        onto=str(url),
        branch="main",
    )
    assert result == old_tip
    assert len(git(out, "log", "--oneline").splitlines()) == 1
    assert "nothing to commit" in capsys.readouterr().out


def test_onto_and_branch_are_given_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ending:
        main([str(out), "--author", AUTHOR, "--onto", str(tmp_path / "url")])
    assert ending.value.code == 2
    assert "--onto and --branch are given together" in capsys.readouterr().err


def test_onto_without_a_branch_is_refused(tmp_path: Path) -> None:
    source = source_tree(tmp_path)
    url = public_repo(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as ending:
        build(
            source=source,
            out=out,
            author=AUTHOR,
            forbidden=[],
            secrets=[],
            onto=str(url),
            branch=None,
        )
    assert "--onto and --branch are given together" in str(ending.value)


def test_a_failed_git_call_surfaces_the_command_and_stderr(tmp_path: Path) -> None:
    tree = source_tree(tmp_path)
    with pytest.raises(SystemExit) as ending:
        _git(tree, "show", "refs/heads/does-not-exist")
    assert "does-not-exist" in str(ending.value)
    assert "fatal" in str(ending.value)


def test_a_remote_query_on_a_non_repository_surfaces_git_s_stderr(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(SystemExit) as ending:
        _remote_has_branch(str(not_a_repo), "main")
    assert "does not appear to be a git repository" in str(ending.value)


def test_a_branch_query_matches_only_the_named_ref(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    (seed / "README.md").write_text("x\n", encoding="utf-8")
    git(seed, "add", "--all")
    commit_as(seed, "first", "Ada Example", "ada@example.org")
    git(seed, "checkout", "-q", "-b", "release/platforms")
    (seed / "other.md").write_text("y\n", encoding="utf-8")
    git(seed, "add", "--all")
    commit_as(seed, "second", "Ada Example", "ada@example.org")
    bare = tmp_path / "public.git"
    git(seed, "clone", "--bare", "--quiet", str(seed), str(bare))
    assert _remote_has_branch(str(bare), "platforms") is False
