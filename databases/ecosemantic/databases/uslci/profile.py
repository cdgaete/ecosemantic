"""The facts a USLCI release pins: the repositories and the hashes of their files, the two lists
its validation holds it to, and what a validated run recorded."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ecosemantic.databases import profiles

RELEASES = Path(__file__).parent / "releases"


class Pin(BaseModel):
    """One repository a release is read from, the commit it is taken at, and the SHA-256 of the
    file that commit serves."""

    model_config = ConfigDict(frozen=True)

    repository: str
    commit: str
    sha256: str
    release: str | None = None


class Validated(BaseModel):
    """What a validated profile measured: its dataset and category counts, and the largest
    relative difference of its scores against the independent computation's."""

    model_config = ConfigDict(frozen=True)

    datasets: int
    categories: int
    largest_rel_diff_to_independent: float


class Profile(BaseModel):
    """One USLCI release's pinned facts: its inventory, the repositories its bridges link to and its
    methods, the file names of its two lists, and the tolerance and counts a validated run
    recorded."""

    model_config = ConfigDict(frozen=True)

    version: str
    server: str
    inventory: Pin
    methods: tuple[Pin, ...]
    bridged: tuple[Pin, ...] = ()
    unlinked: str
    left_out: str
    tolerance: float | None = None
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
