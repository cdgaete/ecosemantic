from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from scripts.release_contents import missing

REPOSITORY = Path(__file__).resolve().parents[1]
ISIC = "ecosemantic/ports/data/isic_rev4_english_structure.csv"
ISIC_SOURCE = "core/ecosemantic/ports/data/isic_rev4_english_structure.csv"
HASH = re.compile(r"\b[0-9a-f]{64}\b")


def wheel(path: Path, names: list[str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "x")
    return path


def sdist(path: Path, names: list[str]) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    return path


def test_a_wheel_carries_its_licence_and_notice(tmp_path: Path) -> None:
    whole = wheel(
        tmp_path / "ecosemantic_core-0.1.0-py3-none-any.whl",
        [
            "ecosemantic/ports/__init__.py",
            "ecosemantic_core-0.1.0.dist-info/licenses/LICENSE",
            "ecosemantic_core-0.1.0.dist-info/licenses/NOTICE",
        ],
    )
    bare = wheel(tmp_path / "ecosemantic_mcp-0.1.0-py3-none-any.whl", ["ecosemantic/mcp/x.py"])
    assert missing(whole) == []
    assert missing(bare) == ["licenses/LICENSE", "licenses/NOTICE"]


def test_an_sdist_carries_its_licence_and_notice(tmp_path: Path) -> None:
    whole = sdist(
        tmp_path / "ecosemantic_core-0.1.0.tar.gz",
        [
            "ecosemantic_core-0.1.0/LICENSE",
            "ecosemantic_core-0.1.0/NOTICE",
            "ecosemantic_core-0.1.0/x",
        ],
    )
    bare = sdist(tmp_path / "ecosemantic_mcp-0.1.0.tar.gz", ["ecosemantic_mcp-0.1.0/x"])
    assert missing(whole) == []
    assert missing(bare) == ["LICENSE", "NOTICE"]


def test_the_view_wheel_carries_the_built_page_and_its_notices(tmp_path: Path) -> None:
    licences = [
        "ecosemantic_view-0.1.0.dist-info/licenses/LICENSE",
        "ecosemantic_view-0.1.0.dist-info/licenses/NOTICE",
    ]
    bare = wheel(tmp_path / "ecosemantic_view-0.1.0-py3-none-any.whl", licences)
    assert missing(bare) == [
        "ecosemantic/view/static/index.html",
        "ecosemantic/view/static/THIRD_PARTY_NOTICES.txt",
    ]


def recorded(destination: str) -> str:
    """The SHA-256 the provenance table records for the file a source is taken into."""
    for line in (REPOSITORY / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        found = HASH.findall(line)
        if destination in line and found:
            return found[-1]
    raise AssertionError(f"PROVENANCE.md holds no row for {destination}")


def test_the_core_wheel_carries_the_isic_structure_the_provenance_records(tmp_path: Path) -> None:
    subprocess.run(
        [
            str(shutil.which("uv")),
            "build",
            "--package",
            "ecosemantic-core",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=True,
    )
    [built] = tmp_path.glob("ecosemantic_core-*.whl")
    with zipfile.ZipFile(built) as archive:
        shipped = archive.read(ISIC)
    assert hashlib.sha256(shipped).hexdigest() == recorded(ISIC_SOURCE)
