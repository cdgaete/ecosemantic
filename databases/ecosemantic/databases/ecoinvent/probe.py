"""What a release holds that a build cannot read, as the evidence a refusal names."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ecosemantic.databases.ecoinvent.datasets import read_datasets
from ecosemantic.databases.ecoinvent.lcia import read_methods
from ecosemantic.databases.ecoinvent.masterdata import flow_type, read_masterdata, read_units
from ecosemantic.databases.ecoinvent.overview import read_urls
from ecosemantic.databases.ecoinvent.profile import Profile
from ecosemantic.databases.ecoinvent.release import Release
from ecosemantic.errors import NotSupported
from ecosemantic.model import units

_LIMIT = 20


@dataclass(frozen=True)
class Probe:
    """Everything a release holds that a build cannot read: units the core lacks, features the
    reader does not take, features it reads as documentation, spreads of zero, factor rows no
    flow answers, and the gaps between the datasets and the Database Overview's URLs."""

    datasets: int
    unknown_units: dict[str, list[str]]
    unread: dict[str, list[str]]
    degenerate_uncertainty: list[str]
    unmatched_factors: list[tuple[str, str, str]]
    without_url: list[str]
    urls_without_dataset: list[str]
    documentation: dict[str, list[str]] = field(default_factory=dict)
    units_without_use: list[str] = field(default_factory=list)
    compartments: list[tuple[str, str, str]] = field(default_factory=list)

    def clean(self, profile: Profile) -> bool:
        """Whether the release holds nothing a build would refuse: the profile's expected
        unmatched factors, zero spreads and datasets without a URL, its documentation features,
        and the two lists it keeps for information aside."""
        spread = (
            len(self.degenerate_uncertainty) == profile.expected_zero_spread
            if profile.zero_spread == "none"
            else not self.degenerate_uncertainty
        )
        return (
            not self.unknown_units
            and not self.unread
            and spread
            and not self.urls_without_dataset
            and len(self.without_url) == profile.expected_without_url
            and len(self.unmatched_factors) == profile.expected_unmatched_factors
            and all(feature in profile.read_as_documentation for feature in self.documentation)
        )


def _known(symbol: str) -> bool:
    """Whether the core's unit registry knows a symbol."""
    try:
        units.by_symbol(symbol)
    except NotSupported:
        return False
    return True


def probe(release: Release, profile: Profile) -> Probe:
    """Read a release with its profile's layouts and list what a build could not read."""
    master = read_masterdata(release.ecospold)
    urls = read_urls(release.overview, profile.overview)
    datasets, findings = read_datasets(release.ecospold, urls=urls)
    name = f"ecoinvent-{release.version}-{release.system_model}"
    _, unmatched = read_methods(release.lcia, profile.lcia, master, name)
    codes = {dataset.code for dataset in datasets}
    unknown_units = {symbol: list(users) for symbol, users in master.unknown_units.items()}
    for symbol, users in findings.unknown_units.items():
        unknown_units.setdefault(symbol, []).extend(users)
    used = set(master.unknown_units) | set(findings.unknown_units)
    declared = set(read_units(release.ecospold))
    pairs = sorted({(e.compartment, e.subcompartment) for e in master.elementary.values()})
    return Probe(
        datasets=len(datasets),
        unknown_units=unknown_units,
        unread=findings.unread,
        degenerate_uncertainty=findings.degenerate_uncertainty,
        unmatched_factors=unmatched,
        without_url=[dataset.code for dataset in datasets if dataset.url is None],
        urls_without_dataset=[key for key in urls if key not in codes],
        documentation=findings.documentation,
        units_without_use=sorted(
            symbol for symbol in declared if symbol not in used and not _known(symbol)
        ),
        compartments=[
            (compartment, subcompartment, flow_type(compartment))
            for compartment, subcompartment in pairs
        ],
    )


def _listed(items: Sequence[object]) -> dict[str, object]:
    """A list as JSON: its first twenty entries and its full count."""
    return {"count": len(items), "first": list(items[:_LIMIT])}


def _grouped(grouped: Mapping[str, Sequence[object]]) -> dict[str, object]:
    """A mapping of lists as JSON: how many keys it holds, and each list cut to twenty."""
    return {
        "count": len(grouped),
        "first": {name: _listed(items) for name, items in grouped.items()},
    }


def report(found: Probe) -> dict[str, object]:
    """A probe as JSON, every list cut to its first twenty entries with its full count."""
    return {
        "datasets": found.datasets,
        "unknown_units": _grouped(found.unknown_units),
        "unread": _grouped(found.unread),
        "degenerate_uncertainty": _listed(found.degenerate_uncertainty),
        "unmatched_factors": _listed(found.unmatched_factors),
        "without_url": _listed(found.without_url),
        "urls_without_dataset": _listed(found.urls_without_dataset),
        "documentation": _grouped(found.documentation),
        "units_without_use": _listed(found.units_without_use),
        "compartments": _listed(found.compartments),
    }
