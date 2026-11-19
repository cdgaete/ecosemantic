"""Build one release into one openLCA JSON-LD bundle, refusing what the probe shows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from ecosemantic.databases.ecoinvent.masterdata import base_flows
from ecosemantic.databases.ecoinvent.probe import Probe, probe_read, read_release
from ecosemantic.databases.ecoinvent.profile import Profile, verify
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.databases.revision import revise
from ecosemantic.errors import Conflict, NotSupported
from ecosemantic.package.base_writer import BaseRows, Written, write_base_bundle
from ecosemantic.package.manifest import Correction

_LIMIT = 5


def _refusal(found: Probe, profile: Profile) -> NotSupported:
    """The error a build raises, naming every kind of thing the probe found in the order a
    reader resolves them."""
    return NotSupported(
        "the release holds things a build cannot read: "
        f"{len(found.unknown_units)} units the core does not know "
        f"{list(found.unknown_units.items())[:_LIMIT]}; "
        f"{len(found.unread)} features the reader does not take "
        f"{list(found.unread.items())[:_LIMIT]}; "
        f"{len(found.degenerate_uncertainty)} uncertainties with no spread "
        f"{found.degenerate_uncertainty[:_LIMIT]}, the profile expects "
        f"{profile.expected_zero_spread}; "
        f"{len(found.documentation)} features not pinned as documentation "
        f"{list(found.documentation)[:_LIMIT]}; "
        f"{len(found.unmatched_factors)} factor rows no elementary flow answers, the profile "
        f"expects {profile.expected_unmatched_factors} {found.unmatched_factors[:_LIMIT]}; "
        f"{len(found.without_url)} datasets the Database Overview gives no URL "
        f"{found.without_url[:_LIMIT]}, the profile expects {profile.expected_without_url}, and "
        f"{len(found.urls_without_dataset)} overview rows name "
        f"no dataset {found.urls_without_dataset[:_LIMIT]}"
    )


def build(
    release: Release,
    profile: Profile,
    out_dir: Path,
    now: datetime,
    *,
    revision: int,
    corrections: Sequence[Correction],
) -> Written:
    """Probe, refuse anything unknown, and write the release as one bundle: the release with its
    corrections, read into the canonical shape, at the revision its profile names."""
    verify(release, profile)
    read = read_release(release, profile)
    found = probe_read(release, profile, read)
    if not found.clean(profile):
        raise _refusal(found, profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / f"{read.name}.zip"
    if destination.exists():
        raise Conflict(f"{destination.name} exists; name another destination")
    staged = out_dir / f".{read.name}.staging.zip"
    staged.unlink(missing_ok=True)
    written = write_base_bundle(
        BaseRows(
            datasets=read.datasets,
            flows=base_flows(read.master),
            methods=read.methods,
            locations=read.master.geographies,
        ),
        scheme="ecoinvent",
        name=read.name,
        version=release.version,
        destination=staged,
        now=now,
    )
    try:
        revise(
            staged,
            destination,
            name=read.name,
            version=release.version,
            revision=revision,
            corrections=corrections,
            now=now,
        )
    finally:
        staged.unlink(missing_ok=True)
    return Written(
        bundle=destination,
        processes=written.processes,
        flows=written.flows,
        methods=written.methods,
    )
