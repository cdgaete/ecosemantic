"""The facts a BAFU release pins: the two packs Nexus serves, the workbook's columns mapped to the
method and category each scores, its total column, the lists its validation holds it to, and what a
validated run recorded."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ecosemantic.databases import profiles

RELEASES = Path(__file__).parent / "releases"


class Pack(BaseModel):
    """One file a release is read from: the datafile Nexus serves, its version, its format, and the
    SHA-256 of the bytes the profile pins."""

    model_config = ConfigDict(frozen=True)

    pack: str
    version: int
    format: str
    sha256: str


class Column(BaseModel):
    """One workbook column that scores a category, and the method and category it scores."""

    model_config = ConfigDict(frozen=True)

    header: str
    method: str
    category: str


class Total(BaseModel):
    """The workbook column that sums one method's categories."""

    model_config = ConfigDict(frozen=True)

    header: str
    method: str


class Validated(BaseModel):
    """What a validated run measured: the processes and columns it compared, how many known
    differences it holds, and the largest relative difference inside the tolerance."""

    model_config = ConfigDict(frozen=True)

    processes: int
    columns: int
    differences: int
    largest_rel_diff_within_tolerance: float


class Profile(BaseModel):
    """One BAFU release's pinned facts: its inventory and results packs, the workbook's columns and
    total, the file names of its two lists, and the tolerance and counts a validated run
    recorded."""

    model_config = ConfigDict(frozen=True)

    version: str
    server: str
    citation: str
    inventory: Pack
    results: Pack
    columns: tuple[Column, ...]
    total: Total
    unlinked: str
    differences: str
    tolerance: float
    validated: Validated | None = None


def versions() -> tuple[str, ...]:
    """The release labels the profiles directory carries, newest first."""
    return profiles.versions(RELEASES)


def recorded(name: str) -> Path | None:
    """The list file a profile names, or nothing when the release has not recorded it yet."""
    return profiles.recorded(RELEASES, name)


def read_profile(version: str) -> Profile:
    """The profile named for a release label; a label without one is not found."""
    return profiles.read_profile(Profile, RELEASES, version)
