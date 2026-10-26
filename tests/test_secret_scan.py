from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.secret_scan import Finding, findings, main

REPOSITORY = Path(__file__).resolve().parents[1]

GITHUB = "gh" + "p_" + "A" * 36
KEY = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
SECRET = "q7Zx" + "f9Wt"


def tree(tmp_path: Path, files: dict[str, str]) -> Path:
    """A directory holding each given text under the name it is keyed by."""
    root = tmp_path / "tree"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def tracked_tree(tmp_path: Path) -> Path:
    """A copy of every file the repository tracks, laid out as the repository lays them."""
    listed = subprocess.run(
        [str(shutil.which("git")), "-C", str(REPOSITORY), "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    root = tmp_path / "repository"
    for name in listed:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / name, target)
    return root


def test_a_private_key_is_found(tmp_path: Path) -> None:
    root = tree(tmp_path, {"keys/app.pem": "held\n" + KEY + "\n"})
    assert findings(root, [], []) == [Finding(root / "keys" / "app.pem", 2, "private key")]


def test_a_token_is_found(tmp_path: Path) -> None:
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    root = tree(tmp_path, {"notes.md": "one\n" + GITHUB + "\n" + aws + "\n"})
    assert [(found.line, found.rule) for found in findings(root, [], [])] == [
        (2, "token"),
        (3, "token"),
    ]


def test_a_home_path_is_found(tmp_path: Path) -> None:
    text = "\n".join(("/home/" + "ada/work", "/Users/" + "ada/x", "C:\\Users\\" + "ada\\x"))
    root = tree(tmp_path, {"log.txt": text})
    assert [(found.line, found.rule) for found in findings(root, [], [])] == [
        (1, "home path"),
        (2, "home path"),
        (3, "home path"),
    ]


def test_a_home_path_named_person_is_not_found(tmp_path: Path) -> None:
    root = tree(tmp_path, {"log.txt": "/home/" + "person/work\n"})
    assert findings(root, [], []) == []


def test_a_forbidden_word_is_found(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "one\ntwo\n"})
    assert findings(root, ["two"], []) == [Finding(root / "a.txt", 2, "forbidden word")]


def test_a_secret_is_found(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "one\ntwo " + SECRET + "\n"})
    assert findings(root, [], [SECRET]) == [Finding(root / "a.txt", 2, "secret")]


def test_a_clean_tree_has_no_finding(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "nothing to see\n", "b/c.txt": "nor here\n"})
    assert findings(root, ["absent"], ["absent"]) == []


def test_a_file_that_is_not_text_is_skipped(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "clean\n"})
    (root / "blob.bin").write_bytes(b"\xff\xfe" + GITHUB.encode())
    assert findings(root, [], []) == []


def test_a_git_directory_is_skipped(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "clean\n", ".git/config": GITHUB + "\n"})
    assert findings(root, [], []) == []


def test_a_forbidden_word_matches_as_a_whole_word(tmp_path: Path) -> None:
    root = tree(tmp_path, {"a.txt": "northwind\nnorthern\nnorth\n"})
    assert findings(root, ["north"], []) == [Finding(root / "a.txt", 3, "forbidden word")]


def test_main_prints_no_secret_and_exits_1_on_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, {"a.txt": "clean\n" + SECRET + "\n"})
    token_file = tmp_path / "token"
    token_file.write_text("unused\n" + SECRET + "\n", encoding="utf-8")
    assert main([str(root), "--secret-file", str(token_file)]) == 1
    printed = capsys.readouterr().out
    assert "a.txt:2: secret" in printed
    assert "1 finding" in printed
    assert SECRET not in printed


def test_main_exits_0_when_nothing_is_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, {"a.txt": "clean\n"})
    assert main([str(root), "--forbid", "absent"]) == 0
    assert "0 findings" in capsys.readouterr().out


def test_the_package_tree_passes(tmp_path: Path) -> None:
    forbidden = [word for word in os.environ.get("SECRET_SCAN_FORBID", "").split(",") if word]
    assert findings(tracked_tree(tmp_path), forbidden, []) == []
