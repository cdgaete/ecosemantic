"""Build one release into one openLCA JSON-LD bundle, refusing what the probe shows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ecosemantic.databases.ecoinvent.datasets import read_datasets
from ecosemantic.databases.ecoinvent.lcia import read_methods
from ecosemantic.databases.ecoinvent.masterdata import base_flows, read_masterdata
from ecosemantic.databases.ecoinvent.overview import read_urls
from ecosemantic.databases.ecoinvent.probe import Probe, probe
from ecosemantic.databases.ecoinvent.profile import Profile, verify
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.errors import NotSupported
from ecosemantic.package.base_writer import BaseRows, Written, write_base_bundle

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


def build(release: Release, profile: Profile, out_dir: Path, now: datetime) -> Written:
    """Probe, refuse anything unknown, and write the release as one bundle."""
    verify(release, profile)
    found = probe(release, profile)
    if not found.clean(profile):
        raise _refusal(found, profile)
    master = read_masterdata(release.ecospold)
    urls = read_urls(release.overview, profile.overview)
    datasets, _ = read_datasets(release.ecospold, urls=urls)
    name = f"ecoinvent-{release.version}-{release.system_model}"
    methods, _ = read_methods(release.lcia, profile.lcia, master, name)
    out_dir.mkdir(parents=True, exist_ok=True)
    return write_base_bundle(
        BaseRows(datasets=datasets, flows=base_flows(master), methods=methods),
        scheme="ecoinvent",
        name=name,
        version=release.version,
        destination=out_dir / f"{name}.zip",
        now=now,
    )
