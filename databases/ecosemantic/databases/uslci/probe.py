"""What a USLCI release and its methods hold, counted from their own JSON for a build that reads
them."""

from __future__ import annotations

import json
import tempfile
import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipReader

from ecosemantic.databases.lists import distinct_unlinked
from ecosemantic.databases.uslci.build import build
from ecosemantic.errors import EcoSemanticError, Invalid, NotSupported
from ecosemantic.model import units
from ecosemantic.package.background import exchange_refusal, read_background
from ecosemantic.package.olca import uncertainty_refusal


@dataclass(frozen=True)
class Probe:
    """What a release and its methods hold against what the core's importer reads: its schema
    versions, its counts, the units the core lacks or defines otherwise, the exchanges it would
    refuse, the inputs a build leaves unlinked, and the bridge inputs it links and cannot."""

    schema_versions: dict[str, int]
    processes: int
    elementary_flows: int
    methods: int
    categories: int
    characterised: dict[str, int]
    unknown_units: dict[str, int]
    other_property: int
    refused: dict[str, int]
    unit_factors_differ: dict[str, int]
    unlinked_by_category: dict[str, int]
    bridges_linked: int
    bridges_unlinked: int
    build_refused: str | None


@dataclass(frozen=True)
class _Unlinked:
    """What a probe's build answered: the unlinked inputs by their flow's top category, the units it
    converted with a repository's own factor, the bridge inputs it linked and could not, and the
    message of a build that stopped instead."""

    by_category: dict[str, int]
    by_own_factor: dict[str, int]
    bridges_linked: int
    bridges_unlinked: int
    refused: str | None


def _schema_version(path: Path) -> int:
    """The schema version a package's `openlca.json` declares."""
    with zipfile.ZipFile(path) as archive:
        if "openlca.json" not in archive.namelist():
            raise Invalid(f"{path} declares no openlca.json")
        return int(json.loads(archive.read("openlca.json"))["schemaVersion"])


def _known(symbol: str) -> bool:
    """Whether the core's unit table holds a symbol."""
    try:
        units.by_symbol(symbol)
    except NotSupported:
        return False
    return True


def _exchanges(processes: Sequence[o.Process]) -> list[o.Exchange]:
    """Every exchange of every process."""
    return [exchange for process in processes for exchange in process.exchanges or []]


def _reference_property(flow: o.Flow) -> str | None:
    """The id of the flow property a flow is referenced in."""
    reference = next((fp for fp in flow.flow_properties or [] if fp.is_ref_flow_property), None)
    return reference.flow_property.id if reference and reference.flow_property else None


def _flows_of(processes: Sequence[o.Process], flows: dict[str, o.Flow]) -> set[str]:
    """The ids of the elementary flows the processes use."""
    return {
        exchange.flow.id
        for exchange in _exchanges(processes)
        if exchange.flow is not None
        and exchange.flow.id in flows
        and flows[exchange.flow.id].flow_type == o.FlowType.ELEMENTARY_FLOW
    }


def _characterised(reader: ZipReader, method: o.ImpactMethod, used: set[str]) -> set[str]:
    """The ids of the elementary flows a method characterises that the processes use."""
    found: set[str] = set()
    for ref in method.impact_categories or []:
        category = reader.read(o.ImpactCategory, ref.id) if ref.id is not None else None
        if category is None:
            continue
        for factor in category.impact_factors or []:
            if factor.flow is not None and factor.flow.id in used:
                found.add(factor.flow.id)
    return found


def _top_categories(*packages: Path) -> dict[str, str]:
    """The top category of each flow the packages hold, the earlier package's record of a flow it
    shares."""
    found: dict[str, str] = {}
    for path in packages:
        with ZipReader(str(path)) as reader:
            for flow in reader.read_each(o.Flow):
                found.setdefault(flow.id, (flow.category or "").split("/")[0])
    return found


def _unlinked(inventory: Path, methods: Sequence[Path], bridged: Sequence[Path]) -> _Unlinked:
    """The inputs a build of the release, its bridged repositories and its methods leaves unlinked,
    by their flow's top category, the units it converts with a repository's own factor, the bridge
    inputs it links and cannot, or the message of a build that stops; the build works in a directory
    removed with it."""
    with tempfile.TemporaryDirectory(prefix="ecosemantic-uslci-probe-") as directory:
        try:
            built = build(
                inventory, methods, version="probe", out_dir=Path(directory), bridged=bridged
            )
        except EcoSemanticError as error:
            return _Unlinked(
                by_category={},
                by_own_factor={},
                bridges_linked=0,
                bridges_unlinked=0,
                refused=str(error),
            )
        imported = read_background(built.bundle, "uslci-probe", foreground=frozenset())
    rows = distinct_unlinked(imported, _top_categories(inventory, *bridged))
    return _Unlinked(
        by_category=dict(Counter(row.flow_category for row in rows)),
        by_own_factor=built.unit_converted,
        bridges_linked=built.bridges_linked,
        bridges_unlinked=built.bridges_unlinked,
        refused=None,
    )


def probe(inventory: Path, methods: Sequence[Path], *, bridged: Sequence[Path] = ()) -> Probe:
    """Count what a release, the repositories its bridges link to and its methods hold, what of it
    the core's importer cannot take, the inputs a build leaves unlinked by their flow's top
    category, and the bridge inputs it links and cannot, or why a build stops."""
    versions = {inventory.name: _schema_version(inventory)}
    versions |= {path.name: _schema_version(path) for path in methods}
    versions |= {path.name: _schema_version(path) for path in bridged}
    with ZipReader(str(inventory)) as reader:
        processes = list(reader.read_each(o.Process))
        flows = {flow.id: flow for flow in reader.read_each(o.Flow)}
        used = _flows_of(processes, flows)
        unknown_units = Counter(
            exchange.unit.name
            for exchange in _exchanges(processes)
            if exchange.unit is not None
            and exchange.unit.name is not None
            and not _known(exchange.unit.name)
        )
        other_property = sum(
            1
            for exchange in _exchanges(processes)
            if exchange.flow is not None
            and exchange.flow.id in flows
            and exchange.flow_property is not None
            and exchange.flow_property.id != _reference_property(flows[exchange.flow.id])
        )
        refused = Counter(
            reason
            for exchange in _exchanges(processes)
            if exchange.flow is not None
            and exchange.flow.id in flows
            and (
                reason := uncertainty_refusal(exchange.uncertainty, exchange.amount or 0.0)
                or exchange_refusal(exchange, flows[exchange.flow.id])
            )
        )
        elementary = sum(
            1 for flow in flows.values() if flow.flow_type == o.FlowType.ELEMENTARY_FLOW
        )
    characterised: dict[str, int] = {}
    method_count = 0
    categories = 0
    for path in methods:
        with ZipReader(str(path)) as reader:
            for method in reader.read_each(o.ImpactMethod):
                method_count += 1
                characterised[method.name or ""] = len(_characterised(reader, method, used))
            categories += len(list(reader.read_each(o.ImpactCategory)))
    found = _unlinked(inventory, methods, bridged)
    return Probe(
        schema_versions=versions,
        processes=len(processes),
        elementary_flows=elementary,
        methods=method_count,
        categories=categories,
        characterised=characterised,
        unknown_units=dict(unknown_units),
        other_property=other_property,
        refused=dict(refused),
        unit_factors_differ=found.by_own_factor,
        unlinked_by_category=found.by_category,
        bridges_linked=found.bridges_linked,
        bridges_unlinked=found.bridges_unlinked,
        build_refused=found.refused,
    )
