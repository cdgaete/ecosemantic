"""The files of one ecoinvent release, and the hash a profile pins them by."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SystemModel = Literal["cutoff"]


@dataclass(frozen=True)
class Release:
    """The five files of one ecoinvent release that a build reads."""

    version: str
    system_model: SystemModel
    ecospold: Path
    lcia: Path
    matrix: Path
    cumulative_lcia: Path
    overview: Path

    def files(self) -> dict[str, Path]:
        """The five files by role: ecospold, lcia, matrix, cumulative_lcia and overview."""
        return {
            "ecospold": self.ecospold,
            "lcia": self.lcia,
            "matrix": self.matrix,
            "cumulative_lcia": self.cumulative_lcia,
            "overview": self.overview,
        }


def sha256(path: Path) -> str:
    """The SHA-256 of a file, or of a directory's files ordered by their relative path parts."""
    digest = hashlib.sha256()
    if path.is_dir():
        files = sorted(
            (file for file in path.rglob("*") if file.is_file()),
            key=lambda file: file.relative_to(path).parts,
        )
    else:
        files = [path]
    for file in files:
        if path.is_dir():
            digest.update(file.relative_to(path).as_posix().encode())
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()
