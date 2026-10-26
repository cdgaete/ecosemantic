"""Fetch one ecoinvent release's files through ecoinvent_interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ecoinvent_interface import ReleaseType

from ecosemantic.databases.ecoinvent.release import Release, SystemModel
from ecosemantic.errors import Invalid, NotFound


class ReleaseClient(Protocol):
    """What ecoinvent_interface.EcoinventRelease offers a download; a test doubles it. Every
    argument is positional, so a method's parameter names are not part of the port."""

    def get_release(
        self,
        _version: str,
        _system_model: str,
        _release_type: ReleaseType,
        _extract: bool,
        /,
    ) -> Path: ...

    def get_extra(self, _version: str, _filename: str, /) -> Path: ...

    def list_extra_files(self, _version: str, /) -> dict[str, object]: ...


def download(version: str, system_model: SystemModel, client: ReleaseClient) -> Release:
    """Fetch the unit processes, matrix export, cumulative LCIA, LCIA implementation and Database
    Overview of one release into ecoinvent_interface's cache."""
    ecospold = client.get_release(version, system_model, ReleaseType.ecospold, True)
    matrix = client.get_release(version, system_model, ReleaseType.matrix, True)
    cumulative = client.get_release(version, system_model, ReleaseType.cumulative_lcia, True)
    extras = client.list_extra_files(version)
    lcia_name = f"ecoinvent {version}_LCIA_implementation.7z"
    overview_name = f"Database-Overview-for-ecoinvent-v{version}.xlsx"
    missing = [n for n in (lcia_name, overview_name) if n not in extras]
    if missing:
        raise NotFound(f"ecoinvent {version} lists no {missing}")
    lcia_dir = client.get_extra(version, lcia_name)
    return Release(
        version=version,
        system_model=system_model,
        ecospold=ecospold,
        lcia=_one(lcia_dir, "*.xlsx"),
        matrix=_matrix(matrix),
        cumulative_lcia=_one(cumulative, "*.xlsx"),
        overview=client.get_extra(version, overview_name),
    )


def _matrix(folder: Path) -> Path:
    """The directory holding the matrix export's files, from a release that puts them directly in
    the extracted folder and one that nests them a level deeper."""
    found = sorted({path.parent for path in folder.rglob("A_public.csv")})
    if len(found) != 1:
        raise Invalid(f"{folder} holds {len(found)} directories holding A_public.csv, not one")
    return found[0]


def _one(folder: Path, pattern: str) -> Path:
    found = sorted(folder.glob(pattern))
    if len(found) != 1:
        raise Invalid(f"{folder} holds {len(found)} files matching {pattern}, not one")
    return found[0]
