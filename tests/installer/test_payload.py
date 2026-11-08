from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts import payload
from scripts.payload import (
    BUNDLED,
    CORE_DISTRIBUTIONS,
    build,
    built_version,
    defines,
    emptied,
    export_requirements,
    locked_at,
    locked_version,
    longest_path,
    notices,
    pruned,
    record_payload,
    requirement_gaps,
    requirement_names,
    workspace_version,
)

REPOSITORY = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY / "installer"
LOCK = INSTALLER / "win-x64.requirements.txt"


def installed(
    site: Path,
    name: str,
    version: str,
    fields: list[tuple[str, str]],
    files: dict[str, str],
) -> Path:
    """One distribution installed into site-packages: its metadata and the licence texts it
    ships."""
    directory = site / f"{name.replace('-', '_')}-{version}.dist-info"
    directory.mkdir(parents=True)
    metadata = [
        "Metadata-Version: 2.4",
        f"Name: {name}",
        f"Version: {version}",
        *(f"{key}: {value}" for key, value in fields),
        "",
        "The distribution's description.",
        "",
    ]
    (directory / "METADATA").write_text("\n".join(metadata), encoding="utf-8")
    for relative, text in files.items():
        (directory / relative).parent.mkdir(parents=True, exist_ok=True)
        (directory / relative).write_text(text, encoding="utf-8")
    return directory


def cpython_terms(*, without: str | None = None) -> str:
    """CPython's licence with a line of terms for every library the Windows payload links, each
    named as its own statement names it, less the library named."""
    lines = ["PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2", ""]
    for library, names in BUNDLED.items():
        if library != without:
            lines.append(f"{names[0]} terms, {library}'s own statement.")
    return "\n".join(lines) + "\n"


def test_the_pruned_paths_are_tcl_tk_idle_and_the_launchers(tmp_path: Path) -> None:
    # the paths the payload drops
    for name in (
        "tcl/tk.tcl",
        "Lib/tkinter/__init__.py",
        "Lib/idlelib/__init__.py",
        "Lib/turtledemo/__init__.py",
        "DLLs/_tkinter.pyd",
        "DLLs/tcl86t.dll",
        "DLLs/tk86t.dll",
        "Scripts/pip.exe",
        "python.exe",
        "Lib/json/__init__.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert sorted(path.relative_to(tmp_path).as_posix() for path in pruned(tmp_path)) == [
        "DLLs/_tkinter.pyd",
        "DLLs/tcl86t.dll",
        "DLLs/tk86t.dll",
        "Lib/idlelib",
        "Lib/tkinter",
        "Lib/turtledemo",
        "Scripts",
        "tcl",
    ]
    assert (tmp_path / "python.exe").exists()


def test_the_longest_path_is_measured_from_the_payload_root(tmp_path: Path) -> None:
    library = tmp_path / "python" / "Lib" / "site-packages" / "some_distribution" / "__pycache__"
    library.mkdir(parents=True)
    longest = library / "module.cpython-313.pyc"
    longest.write_text("x", encoding="utf-8")
    (tmp_path / "python" / "python.exe").write_text("x", encoding="utf-8")
    path, length = longest_path(tmp_path)
    assert path == "python/Lib/site-packages/some_distribution/__pycache__/module.cpython-313.pyc"
    assert length == len(path)
    empty = (
        tmp_path
        / "python"
        / "Lib"
        / "site-packages"
        / "some_distribution"
        / "__pycache__"
        / "a_directory_at_the_module_s_depth"
    )
    empty.mkdir()
    path, length = longest_path(tmp_path)
    assert path.endswith("/a_directory_at_the_module_s_depth")
    assert length == len(path)


def test_the_payload_record_measures_from_the_folder_the_installer_receives(
    tmp_path: Path,
) -> None:
    out = tmp_path / "payload"
    module = out / "python" / "Lib" / "site-packages" / "some_distribution" / "module.py"
    module.parent.mkdir(parents=True)
    module.write_text("x", encoding="utf-8")
    (out / "python" / "python.exe").write_text("x", encoding="utf-8")
    held = record_payload(out, core="0.1.12", python="3.13.18")
    assert (held.core, held.python) == ("0.1.12", "3.13.18")
    assert held.files == 2
    assert held.longest_path == "python/Lib/site-packages/some_distribution/module.py"
    assert held.longest_length == len(held.longest_path)
    assert json.loads((out / "payload.json").read_text(encoding="utf-8")) == held.document()
    assert held.summary(out, 3) == (
        f"{out}: CPython 3.13.18 with 0.1.12, 2 files, 3 modules compiled, "
        f"the longest path {held.longest_length} characters"
    )


def test_notices_carry_every_distribution_s_licence_and_cpython_s(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed(
        site,
        "anyio",
        "4.11.0",
        [("License-Expression", "MIT")],
        {"licenses/LICENSE": "The MIT licence anyio ships.\n"},
    )
    installed(
        site,
        "colorama",
        "0.4.6",
        [("Classifier", "License :: OSI Approved :: BSD License")],
        {},
    )
    installed(site, "folded", "1.0", [("License", "Apache License\n Version 2.0")], {})
    installed(site, "ecosemantic-core", "0.1.12", [("License-Expression", "PolyForm-1.0.0")], {})
    installed(site, "pip", "26.2.2", [("License-Expression", "MIT")], {})
    terms = cpython_terms()
    text = notices(site, terms)
    assert text.startswith("# Third-party notices\n")
    assert "3 distributions" in text
    assert terms.strip() in text
    for library in BUNDLED:
        assert f"{library}'s own statement" in text, library
    assert "## anyio@4.11.0" in text
    assert "Declared licence: MIT" in text
    assert "The MIT licence anyio ships." in text
    assert "### licenses/LICENSE" in text
    assert "## colorama@0.4.6" in text
    assert "Declared licence: License :: OSI Approved :: BSD License" in text
    assert "This distribution ships no licence file." in text
    assert "Declared licence: Apache License Version 2.0" in text
    assert "## ecosemantic-core@0.1.12" in text
    assert "## pip@26.2.2" in text


def test_cpython_terms_that_state_no_terms_for_a_linked_library_are_refused(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    installed(site, "anyio", "4.11.0", [("License-Expression", "MIT")], {})
    with pytest.raises(SystemExit, match="state no terms for SQLite; pin each library"):
        notices(site, cpython_terms(without="SQLite"))


def test_a_distribution_without_any_licence_fails_the_notices_naming_it(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed(site, "nameless", "1.0", [("License", "UNKNOWN")], {})
    installed(site, "bare", "2.0", [], {})
    with pytest.raises(SystemExit, match="bare 2.0, nameless 1.0"):
        notices(site, cpython_terms())


def test_every_library_the_cpython_texts_do_not_name_is_pinned() -> None:
    record = json.loads((INSTALLER / "python.json").read_text(encoding="utf-8"))
    pinned = record["licence"]["bundled"]
    assert set(pinned) == {"SQLite", "liblzma"}
    for library, one in pinned.items():
        assert one["version"], library
        assert one["url"].startswith("https://"), library
        assert len(one["sha256"]) == 64, library
        assert one["release"] == record["release"], library


def commits_the_lock(environ: Mapping[str, str]) -> bool:
    """Whether this run holds the lock the committed file pins. A job whose `uv sync` resolves with
    another setting rewrites `uv.lock` in its own checkout before the tests run, so the file the
    freshness below proves is that job's resolution and not the committed one."""
    return environ.get("UV_RESOLUTION", "highest") == "highest"


def test_the_lock_is_the_resolution_uv_lock_holds(tmp_path: Path) -> None:
    if not commits_the_lock(os.environ):
        pytest.skip(
            f"UV_RESOLUTION is {os.environ['UV_RESOLUTION']}, so uv re-resolved uv.lock "
            "before this run, and the committed resolution is not what is on disk"
        )
    committed = LOCK.read_text(encoding="utf-8")
    assert locked_version(committed) == workspace_version()
    exported = tmp_path / LOCK.name
    export_requirements(exported)
    assert committed == f"{locked_at(workspace_version())}\n{exported.read_text(encoding='utf-8')}"


def test_the_freshness_of_the_lock_is_asked_of_the_committed_resolution_only() -> None:
    assert commits_the_lock({})
    assert commits_the_lock({"UV_RESOLUTION": "highest"})
    assert not commits_the_lock({"UV_RESOLUTION": "lowest-direct"})


def test_every_requirement_line_carries_a_hash() -> None:
    text = LOCK.read_text(encoding="utf-8")
    blocks = [
        line
        for line in text.replace("\\\n", " ").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(blocks) > 100
    for block in blocks:
        assert "--hash=sha256:" in block, block


def test_the_lock_names_none_of_the_core_s_own_distributions() -> None:
    text = LOCK.read_text(encoding="utf-8")
    assert set(requirement_names(text)) & set(CORE_DISTRIBUTIONS) == set()


def test_the_requirement_check_names_a_missing_distribution(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed(
        site,
        "asks",
        "1.0",
        [
            ("License-Expression", "MIT"),
            ("Requires-Dist", "missing>=2"),
            ("Requires-Dist", "elsewhere; sys_platform == 'emscripten'"),
            ("Requires-Dist", "extraful[big]"),
        ],
        {},
    )
    installed(
        site,
        "extraful",
        "1.0",
        [("License-Expression", "MIT"), ("Requires-Dist", "only-with-the-extra; extra == 'big'")],
        {},
    )
    gaps = requirement_gaps(site, (("asks", ""),))
    assert len(gaps) == 2, gaps
    assert "asks requires missing>=2, and the payload holds no missing" in gaps
    assert "extraful[big] requires only-with-the-extra" in " ".join(gaps)


def test_the_requirement_check_names_a_version_the_specifier_refuses(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed(
        site,
        "asks",
        "1.0",
        [("License-Expression", "MIT"), ("Requires-Dist", "held>=2")],
        {},
    )
    installed(site, "held", "1.0", [("License-Expression", "MIT")], {})
    assert requirement_gaps(site, (("asks", ""),)) == [
        "asks requires held>=2, and the payload holds held 1.0"
    ]


def test_the_build_refuses_a_platform_other_than_its_host(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="a win-arm64 payload is built on win-arm64"):
        build("win-arm64", INSTALLER, tmp_path / "payload")
    assert not (tmp_path / "payload").exists()


def test_a_build_of_another_version_or_missing_a_wheel_is_refused(tmp_path: Path) -> None:
    for name in CORE_DISTRIBUTIONS:
        (tmp_path / f"{name.replace('-', '_')}-0.1.12-py3-none-any.whl").touch()
    assert built_version(tmp_path) == "0.1.12"
    shifted = tmp_path / "shifted"
    shifted.mkdir()
    for name in CORE_DISTRIBUTIONS:
        version = "0.2.0" if name == "ecosemantic-core" else "0.1.12"
        (shifted / f"{name.replace('-', '_')}-{version}-py3-none-any.whl").touch()
    with pytest.raises(SystemExit, match="holds core wheels of 0.1.12, 0.2.0"):
        built_version(shifted)
    other = tmp_path / "other"
    other.mkdir()
    (other / "ecosemantic-0.1.12-py3-none-any.whl").touch()
    with pytest.raises(SystemExit, match="holds no wheel for ecosemantic-core"):
        built_version(other)
    twice = tmp_path / "twice"
    twice.mkdir()
    for version in ("0.1.9", "0.1.12"):
        for name in CORE_DISTRIBUTIONS:
            (twice / f"{name.replace('-', '_')}-{version}-py3-none-any.whl").touch()
    with pytest.raises(SystemExit) as refused:
        built_version(twice)
    for name in CORE_DISTRIBUTIONS:
        assert f"{name} 0.1.12, 0.1.9" in str(refused.value)


def test_defines_name_the_version_the_budgets_and_the_payload(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    (payload / "python").mkdir(parents=True)
    (payload / "python" / "python.exe").write_text("x", encoding="utf-8")
    built = {
        "core": "0.1.12",
        "python": "3.13.18",
        "files": 1,
        "longest": {"path": "python/python.exe", "length": 17},
    }
    (payload / "payload.json").write_text(json.dumps(built), encoding="utf-8")
    budgets = json.loads((INSTALLER / "budgets.json").read_text(encoding="utf-8"))
    out = tmp_path / "defines.iss"
    defines(payload, out)
    written = out.read_text(encoding="utf-8")
    assert '#define AppVersion "0.1.12"' in written
    assert "#define LongestPath 17" in written
    assert f"#define DatabasesBudget {budgets['databases']}" in written
    assert f"#define ModelsBudget {budgets['models']}" in written
    payload_dir = os.path.realpath(payload)
    assert f'#define PayloadDir "{payload_dir}"' in written


def test_an_out_folder_no_earlier_build_wrote_is_refused_before_anything_is_removed(
    tmp_path: Path,
) -> None:
    out = tmp_path / "payload"
    out.mkdir()
    kept = out / "notes.txt"
    kept.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match=re.escape(f"{out} holds no payload.json")):
        emptied(out)
    assert kept.is_file()


def test_an_out_folder_an_earlier_build_wrote_is_cleared(tmp_path: Path) -> None:
    out = tmp_path / "payload"
    (out / "python").mkdir(parents=True)
    (out / "payload.json").write_text("{}", encoding="utf-8")
    emptied(out)
    assert not out.exists()


def test_a_distribution_without_a_name_or_a_version_is_refused(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    folder = site / "nameless-1.0.dist-info"
    folder.mkdir(parents=True)
    (folder / "METADATA").write_text("Metadata-Version: 2.4\n\nx\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=re.escape(f"{folder} states no Name and no Version")):
        requirement_gaps(site, (("asks", ""),))


def test_the_export_asks_for_each_extra_the_one_tuple_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def recorded(
        command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
    ) -> str:
        seen.append(command)
        Path(command[command.index("-o") + 1]).write_text("", encoding="utf-8")
        return ""

    monkeypatch.setattr(payload, "CORE_EXTRAS", (("ecosemantic", "tray"),))
    monkeypatch.setattr(payload, "_run", recorded)
    export_requirements(tmp_path / "requirements.txt")
    extras = [seen[0][index + 1] for index, part in enumerate(seen[0]) if part == "--extra"]
    assert extras == ["tray"], seen[0]


def test_the_usage_line_names_where_the_workflow_writes_the_defines() -> None:
    usage = payload.__doc__ or ""
    assert "defines --payload OUT --out installer/windows/defines.iss" in usage, usage
