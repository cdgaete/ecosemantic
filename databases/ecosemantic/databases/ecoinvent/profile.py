"""The per-version facts a build pins: its layouts, the path and hash of each file, and the
decisions the probe asked for."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import yaml
from ecoinvent_interface import CachedStorage, Settings
from pydantic import BaseModel, ConfigDict

from ecosemantic.databases.ecoinvent.datasets import ZeroSpread
from ecosemantic.databases.ecoinvent.lcia import LciaLayout, Sheet
from ecosemantic.databases.ecoinvent.release import Release, SystemModel, sha256
from ecosemantic.errors import Conflict, Invalid, NotFound

RELEASES = Path(__file__).parent / "releases"

_LCIA = LciaLayout(
    factors=Sheet(
        "CFs",
        ("Method", "Category", "Indicator", "Name", "Compartment", "Subcompartment", "CF"),
    ),
    units=Sheet("Indicators", ("Method", "Category", "Indicator", "Indicator Unit")),
)
_OVERVIEW = Sheet("Cut-Off AO", ("Activity UUID & Product UUID", "ecoQuery URL"))


class FileHash(BaseModel):
    """One release file as a profile pins it: its path under the cache directory, and the hash
    of it."""

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str


class Validated(BaseModel):
    """What a validated release measured: its dataset and category counts and the largest
    relative difference of each kind against ecoinvent's own numbers."""

    model_config = ConfigDict(frozen=True)

    datasets: int
    categories: int
    largest_rel_diff: dict[str, float]


class Profile(BaseModel):
    """One release's pinned facts: the files a build reads, the layouts it names, and the
    decisions the probe asked for."""

    model_config = ConfigDict(frozen=True)

    version: str
    system_model: SystemModel
    files: dict[str, FileHash]
    lcia: LciaLayout
    overview: Sheet
    zero_spread: ZeroSpread = "refuse"
    expected_unmatched_factors: int = 0
    expected_zero_spread: int = 0
    expected_without_url: int = 0
    read_as_documentation: list[str] = []
    workbook_disagrees: list[str] = []
    matrix_reference_tolerance: float | None = None
    validated: Validated | None = None


def cache_dir() -> Path:
    """The directory ecoinvent_interface caches a release's files in."""
    return CachedStorage(Settings().output_path).dir


def _cached(path: str) -> Path:
    """The file a profile's path names under the cache directory."""
    return Path(os.path.normpath(cache_dir() / path))


def read_profile(path: Path) -> Profile:
    """The profile a YAML file holds; a file named by an absolute path is invalid."""
    profile = Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    for role, file in profile.files.items():
        if Path(file.path).is_absolute():
            raise Invalid(f"{role} names {file.path}, which is not under the cache directory")
    return profile


def profiled() -> list[tuple[str, SystemModel]]:
    """The releases a profile is recorded for under `releases/`, oldest first."""
    found: list[tuple[str, SystemModel]] = []
    for path in sorted(RELEASES.glob("*.yaml")):
        version, _, system_model = path.stem.rpartition("-")
        found.append((version, cast(SystemModel, system_model)))
    return found


def pinned(version: str, system_model: SystemModel) -> Profile:
    """The profile a release is recorded in; a release with none is not found, naming the profiles
    there are."""
    path = RELEASES / f"{version}-{system_model}.yaml"
    if not path.is_file():
        carried = ", ".join(f"{release}-{model}" for release, model in profiled()) or "none"
        raise NotFound(f"{path} does not exist; the profiles carried are {carried}")
    return read_profile(path)


def default_profile(release: Release) -> Profile:
    """The 3.10 layout and the hash of each of a release's files, named relative to the cache
    directory, with no decision taken."""
    base = cache_dir()
    return Profile(
        version=release.version,
        system_model=release.system_model,
        files={
            role: FileHash(path=os.path.relpath(path, base), sha256=sha256(path))
            for role, path in release.files().items()
        },
        lcia=_LCIA,
        overview=_OVERVIEW,
    )


def verify(release: Release, profile: Profile) -> None:
    """Refuse a release whose pinned files differ from the hashes its profile carries."""
    named = set(profile.files)
    expected = set(release.files())
    if named != expected:
        raise Invalid(
            f"the profile of {release.version} names {sorted(named)}, not {sorted(expected)}"
        )
    for role, pinned in profile.files.items():
        file = _cached(pinned.path)
        actual = sha256(file)
        if actual != pinned.sha256:
            raise Conflict(f"{role} {file} hashes {actual}, the profile pins {pinned.sha256}")
