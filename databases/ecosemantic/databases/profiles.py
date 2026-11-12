"""The release profiles a source's command reads and records: the labels a releases directory
carries, the list files the release has recorded, the profile a label names read as the model the
source declares, and whether a run may be recorded and how its profile is written."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from ecosemantic.errors import Invalid, NotFound

M = TypeVar("M", bound=BaseModel)


def _numbers(version: str) -> tuple[int, ...]:
    """The numbers a release label carries in order, so labels order by the release they name."""
    return tuple(int(number) for number in re.findall(r"\d+", version))


def versions(directory: Path) -> tuple[str, ...]:
    """The release labels the profiles directory carries, newest first."""
    labels = (path.stem for path in directory.glob("*.yaml"))
    return tuple(sorted(labels, key=_numbers, reverse=True))


def recorded(directory: Path, name: str) -> Path | None:
    """The list file a profile names, or nothing when the release has not recorded it yet."""
    path = directory / name
    return path if path.is_file() else None


def read_profile(model: type[M], directory: Path, version: str) -> M:
    """The profile named for a release label, read as the model a source declares; a label without
    one is not found."""
    path = directory / f"{version}.yaml"
    if not path.is_file():
        carried = ", ".join(versions(directory))
        raise NotFound(f"{path} does not exist; the releases carried are {carried}")
    return model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def refuse_mismatches(mismatches: Sequence[str]) -> None:
    """Refuse a run that found a mismatch, naming how many and the first one."""
    if mismatches:
        raise Invalid(f"{len(mismatches)} mismatches, the first: {mismatches[0]}")


def write_profile(profile: BaseModel, directory: Path, version: str) -> Path:
    """Write a release's profile as `<directory>/<version>.yaml`, its keys in the model's order, and
    answer the path."""
    path = directory / f"{version}.yaml"
    path.write_text(
        yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    return path
