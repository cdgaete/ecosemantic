"""What a release carries: each of the six wheels and six sdists holds the licence and the notice,
and the view's wheel holds the built page and its third-party notices. Prints one JSON report
and exits 1 when a file lacks one or the build holds other than six of each.

    python scripts/release_contents.py DIST
"""

from __future__ import annotations

import json
import sys
import tarfile
import zipfile
from pathlib import Path

LICENCE_FILES = ("LICENSE", "NOTICE")
VIEW_FILES = (
    "ecosemantic/view/static/index.html",
    "ecosemantic/view/static/THIRD_PARTY_NOTICES.txt",
)


def _wheel(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    held = {name.split(".dist-info/", 1)[1] for name in names if ".dist-info/" in name}
    lacking = [f"licenses/{name}" for name in LICENCE_FILES if f"licenses/{name}" not in held]
    if path.name.startswith("ecosemantic_view-"):
        lacking += [name for name in VIEW_FILES if name not in names]
    return lacking


def _sdist(path: Path) -> list[str]:
    with tarfile.open(path) as archive:
        held = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}
    return [name for name in LICENCE_FILES if name not in held]


def missing(path: Path) -> list[str]:
    """The files a built distribution should hold and does not."""
    return _wheel(path) if path.suffix == ".whl" else _sdist(path)


def main() -> int:
    dist = Path(sys.argv[1])
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    report = {path.name: missing(path) for path in wheels + sdists}
    passed = len(wheels) == 6 and len(sdists) == 6 and not any(report.values())
    print(json.dumps({"passed": passed, "missing": report}, indent=1))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
