"""What an install of a BAFU release is held to before anything is written, and what its bundle
holds and the core does not apply."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from lca_data_interface import NexusSession

from ecosemantic.databases.bafu.build import build
from ecosemantic.databases.bafu.download import Downloads, Nexus, download
from ecosemantic.databases.bafu.profile import Profile, recorded
from ecosemantic.databases.lists import (
    UnlinkedRow,
    distinct_unlinked,
    flow_categories,
    process_ids,
    unlinked_mismatches,
)
from ecosemantic.errors import Invalid
from ecosemantic.package.background import Import, Unlinked, read_background
from ecosemantic.ports.types import Account, InstallProgress, Reporter


@dataclass(frozen=True)
class NotApplied:
    """What a bundle holds and the core's import does not apply: how many normalisation and
    weighting sets its methods carry, how many exchanges carry a data-quality entry, how many
    parameters it states, and how many of its impact factors carry a formula."""

    nw_sets: int
    dq_entries: int
    parameters: int
    factor_formulas: int


@dataclass(frozen=True)
class Prepared:
    """What a release becomes before it is installed: its bundle, the import of it with the inputs
    no process provides left out, the unlinked inputs its profile holds it to, the records of those
    inputs the install lists as cut off, the licence file a person reads to accept the pack's
    terms, the release's citation, and what the bundle holds and the core does not apply."""

    bundle: Path
    imported: Import
    unlinked: tuple[UnlinkedRow, ...]
    dropped: tuple[Unlinked, ...]
    licence: Path
    citation: str
    not_applied: NotApplied


def session(base: str, account: Account) -> NexusSession:
    """The Nexus session a release's server is reached through, logging in with the account it is
    given."""
    return NexusSession(
        account.username,
        account.password.get_secret_value(),
        token=None if account.token is None else account.token.get_secret_value(),
        base=base,
    )


def _records(bundle: Path) -> list[dict[str, object]]:
    """Every JSON record a bundle holds, parsed."""
    with zipfile.ZipFile(bundle) as archive:
        return [
            cast(dict[str, object], json.loads(archive.read(name)))
            for name in archive.namelist()
            if name.endswith(".json")
        ]


def _typed(records: Sequence[dict[str, object]], model: str) -> list[dict[str, object]]:
    """The records of one openLCA model."""
    return [record for record in records if record.get("@type") == model]


def _listed(record: dict[str, object], field: str) -> list[dict[str, object]]:
    """The records a record's field holds, none when it holds nothing."""
    return cast(list[dict[str, object]], record.get(field) or [])


def not_applied(bundle: Path) -> NotApplied:
    """What a bundle holds and the core's import does not apply, counted from its records."""
    records = _records(bundle)
    categories = _typed(records, "ImpactCategory")
    processes = _typed(records, "Process")
    return NotApplied(
        nw_sets=sum(len(_listed(method, "nwSets")) for method in _typed(records, "ImpactMethod")),
        dq_entries=sum(
            1
            for process in processes
            for exchange in _listed(process, "exchanges")
            if exchange.get("dqEntry")
        ),
        parameters=len(_typed(records, "Parameter"))
        + sum(len(_listed(record, "parameters")) for record in categories + processes),
        factor_formulas=sum(
            1
            for category in categories
            for factor in _listed(category, "impactFactors")
            if factor.get("formula")
        ),
    )


def prepare(profile: Profile, nexus: Nexus, work: Path, report: Reporter) -> Prepared:
    """Download a release's pack with its terms accepted — the command asks for them first — build
    it into `work`, read the bundle back under the release's name, and hold the unlinked inputs of
    that import to the list the profile records: one outside the list is `Invalid` naming every
    one, raised before anything is installed. The import it answers has those inputs cleared, as
    the install drops them. Each step is reported, the download with the bytes of its files."""
    report(InstallProgress(step="downloading"))
    fetched = cast(Downloads, download(profile, nexus, accept_terms=True, results=False))
    report(
        InstallProgress(
            step="downloaded",
            count=fetched.inventory.stat().st_size + fetched.licence.stat().st_size,
        )
    )
    report(InstallProgress(step="building"))
    built = build(fetched.inventory, version=profile.version, out_dir=work)
    report(InstallProgress(step="reading"))
    imported = read_background(built.bundle, f"bafu-{profile.version}", foreground=frozenset())
    report(InstallProgress(step="checking"))
    found = distinct_unlinked(imported, flow_categories(imported))
    mismatches = unlinked_mismatches(
        found=found, path=recorded(profile.unlinked), processes=process_ids(imported)
    )
    if mismatches:
        raise Invalid("; ".join(mismatches))
    return Prepared(
        bundle=built.bundle,
        imported=replace(imported, unlinked=[]),
        unlinked=found,
        dropped=tuple(imported.unlinked),
        licence=fetched.licence,
        citation=fetched.citation,
        not_applied=not_applied(built.bundle),
    )
