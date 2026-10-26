"""The release profiles a source's command reads: the labels a releases directory carries, the list
files the release has recorded, and the profile a label names, read as the model the source
declares."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from ecosemantic.errors import NotFound

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
    return model.model_validate(yaml.safe_load(path.read_text()))
