"""What an ecoinvent release prepares for an install: one bundle built, validated and read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.databases.ecoinvent.build import build
from ecosemantic.databases.ecoinvent.download import ReleaseClient, download
from ecosemantic.databases.ecoinvent.profile import Profile
from ecosemantic.databases.ecoinvent.release import SystemModel
from ecosemantic.databases.ecoinvent.validate import TOLERANCE, Validation, validate
from ecosemantic.errors import Invalid
from ecosemantic.package.background import Import, read_background
from ecosemantic.ports.types import InstallProgress, Reporter

_LIMIT = 5


@dataclass(frozen=True)
class Prepared:
    """What a release becomes before it is installed: its bundle, the import of it, the name it is
    installed under, and what the validation measured."""

    bundle: Path
    imported: Import
    name: str
    validation: Validation


def _bytes(*paths: Path) -> int:
    """The bytes these paths take, a directory counted by the files it holds."""
    return sum(
        file.stat().st_size
        for path in paths
        for file in (path.rglob("*") if path.is_dir() else (path,))
        if file.is_file()
    )


def _difference(validation: Validation) -> str:
    """The largest relative difference a validation measured, and the first mismatches."""
    kind, largest = max(
        validation.largest_rel_diff.items(), key=lambda item: item[1], default=("", 0.0)
    )
    return (
        f"the bundle differs from the release by {largest} in {kind}: "
        f"{validation.mismatches[:_LIMIT]}"
    )


def prepare(
    version: str,
    system_model: SystemModel,
    client: ReleaseClient,
    profile: Profile,
    work: Path,
    report: Reporter,
) -> Prepared:
    """Download a release's five files, build it into `work`, validate the bundle against the
    release's own matrices and cumulative LCIA under the profile's tolerances, and read the bundle
    back under its name. A validation that differs is `Invalid`, naming the largest relative
    difference and the first mismatches, raised before the bundle is read. Each step is reported,
    the download with the bytes of the files it fetched."""
    report(InstallProgress(step="downloading"))
    release = download(version, system_model, client)
    report(InstallProgress(step="downloaded", count=_bytes(*release.files().values())))
    report(InstallProgress(step="building"))
    built = build(release, profile, work, datetime.now(UTC))
    report(InstallProgress(step="validating"))
    validation = validate(
        release,
        built.bundle,
        work / "validation",
        tolerance=TOLERANCE,
        workbook_disagrees=profile.workbook_disagrees,
        matrix_reference_tolerance=profile.matrix_reference_tolerance,
    )
    if validation.mismatches:
        raise Invalid(_difference(validation))
    report(InstallProgress(step="reading"))
    name = f"ecoinvent-{version}-{system_model}"
    imported = read_background(built.bundle, name, foreground=frozenset())
    return Prepared(bundle=built.bundle, imported=imported, name=name, validation=validation)
