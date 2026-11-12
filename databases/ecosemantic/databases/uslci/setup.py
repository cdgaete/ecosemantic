"""What an install of a USLCI release is held to before anything is written: the profile's two
lists, and the access notices its datasets carry."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import olca_schema as o
from lca_data_interface import CommonsServer
from olca_schema.zipio import ZipReader

from ecosemantic.databases.lists import read_unlinked
from ecosemantic.databases.prepared import PreparedRelease
from ecosemantic.databases.uslci.build import build
from ecosemantic.databases.uslci.download import Commons, download
from ecosemantic.databases.uslci.profile import Pin, Profile, recorded
from ecosemantic.databases.uslci.validate import list_mismatches
from ecosemantic.errors import Invalid
from ecosemantic.ports.types import InstallProgress, Reporter


@dataclass(frozen=True)
class Notice:
    """One access notice a release's datasets carry, and how many of them carry it."""

    text: str | None
    datasets: int


@dataclass(frozen=True)
class Prepared(PreparedRelease):
    """A USLCI release prepared for an install, with the pins it was read at and its access
    notices."""

    pins: tuple[Pin, ...]
    notices: tuple[Notice, ...]


def commons(base: str) -> Commons:
    """The Collaboration Server an address names, as a download's client."""
    return CommonsServer(base)


def _restrictions(process: o.Process) -> str | None:
    """The access notice a process documents, or nothing when it documents none."""
    documentation = process.process_documentation
    text = documentation.restrictions_description if documentation is not None else None
    return text or None


def notices(*inventories: Path) -> tuple[Notice, ...]:
    """Each distinct `restrictionsDescription` the processes of every inventory given carry,
    character for character, with the number of processes carrying it, most carried first and then
    by text; the processes carrying none, or an empty one, are one notice of no text."""
    counted: Counter[str | None] = Counter()
    for inventory in inventories:
        with ZipReader(str(inventory)) as reader:
            counted.update(_restrictions(process) for process in reader.read_each(o.Process))
    ordered = sorted(counted.items(), key=lambda item: (-item[1], item[0] or ""))
    return tuple(Notice(text=text, datasets=count) for text, count in ordered)


def prepare(profile: Profile, server: Commons, work: Path, report: Reporter) -> Prepared:
    """Download a release, build it into `work`, and hold it to the two lists the profile records:
    an unlinked input or a left-out exchange outside them is `Invalid` naming every one, raised
    before anything is installed. The import it answers has the inputs no process provides
    cleared, as the install drops them, with the profile's list of them. Each step is reported with
    the bytes of the files it fetched."""
    listed = recorded(profile.unlinked)
    report(InstallProgress(step="downloading"))
    files = download(profile, server)
    fetched = (files.inventory, *files.bridged, *files.methods)
    report(InstallProgress(step="downloaded", count=sum(path.stat().st_size for path in fetched)))
    report(InstallProgress(step="building"))
    built = build(
        files.inventory, files.methods, version=profile.version, out_dir=work, bridged=files.bridged
    )
    report(InstallProgress(step="checking"))
    mismatches = list_mismatches(built.imported, built.left_out, profile)
    if mismatches:
        raise Invalid("; ".join(mismatches))
    return Prepared(
        bundle=built.bundle,
        imported=replace(built.imported, unlinked=[]),
        unlinked=read_unlinked(listed) if listed is not None else (),
        dropped=tuple(built.imported.unlinked),
        pins=(profile.inventory, *profile.bridged, *profile.methods),
        notices=notices(files.inventory, *files.bridged),
    )
