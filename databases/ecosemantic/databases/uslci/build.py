"""Build a USLCI release and its methods into one openLCA JSON-LD bundle the core imports."""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import olca_schema as o

from ecosemantic.databases.lists import LeftOut, LeftOutRow, write_left_out
from ecosemantic.errors import Conflict, Invalid, NotSupported
from ecosemantic.model import units
from ecosemantic.package.background import exchange_refusal, read_background
from ecosemantic.package.olca import uncertainty_refusal
from ecosemantic.package.wholeness import require_whole

Record = dict[str, object]
SCALED = ("geomMean", "mean", "sd", "minimum", "mode", "maximum")
CATEGORIES = "lcia_categories"
METHODS = "lcia_methods"
ELEMENTARY = "ELEMENTARY_FLOW"


@dataclass(frozen=True)
class Built:
    """What a build wrote: the bundle, the counts of it, the bridge inputs it linked and could not,
    and the exchanges it left out."""

    bundle: Path
    processes: int
    elementary_flows: int
    methods: int
    categories: int
    converted: int
    unit_converted: dict[str, int]
    bridges_linked: int
    bridges_unlinked: int
    left_out: tuple[LeftOutRow, ...]


@dataclass(frozen=True)
class _Rewritten:
    """One process written for the bundle: the exchanges it converted by their unit's name, and the
    bridge inputs it linked and could not."""

    process: Record
    converted: int
    by_unit: dict[str, int]
    linked: int
    unlinked: int


def _members(path: Path) -> dict[str, bytes]:
    """Every member of a package, as the bytes it holds."""
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _parsed(content: bytes) -> Record:
    """One record the bytes of a member hold as JSON."""
    return cast(Record, json.loads(content))


def _record_member(name: str, folder: str) -> bool:
    """Whether an archive member is a record of a folder: `<folder>/<id>.json` under one separator.
    A directory entry and a member under `bin/` are not records, whatever their folder."""
    prefix = f"{folder}/"
    return name.startswith(prefix) and name.endswith(".json") and "/" not in name[len(prefix) :]


def _records(members: dict[str, bytes], folder: str) -> dict[str, Record]:
    """The records a package's folder holds, by the id each declares."""
    found = [_parsed(content) for name, content in members.items() if _record_member(name, folder)]
    return {cast(str, record["@id"]): record for record in found}


def _folders(members: dict[str, bytes]) -> dict[str, dict[str, Record]]:
    """The records of every folder a package holds, by folder and then by the id each declares."""
    found: dict[str, dict[str, Record]] = {}
    for name, content in members.items():
        folder, _, _rest = name.partition("/")
        if not _record_member(name, folder):
            continue
        record = _parsed(content)
        found.setdefault(folder, {})[cast(str, record["@id"])] = record
    return found


def _serialised(record: Record) -> bytes:
    """A record as the bytes a member holds."""
    return json.dumps(record).encode()


def _flag(record: Record, key: str) -> bool:
    """Whether a record's flag is set: openLCA writes a boolean only when it is true."""
    return bool(record.get(key))


def _flow_type(record: Record) -> str:
    """The flow type an openLCA flow record declares."""
    return cast(str, record["flowType"])


def _ref_id(ref: object) -> str:
    """The id a reference holds."""
    return cast(str, cast(Record, ref)["@id"])


def _ref_name(ref: object) -> str:
    """The name a reference holds."""
    return cast(str, cast(Record, ref)["name"])


def _exchanges(process: Record) -> list[Record]:
    """The exchanges a process record holds."""
    return [cast(Record, exchange) for exchange in cast(list[object], process["exchanges"])]


def _properties(flow: Record) -> list[Record]:
    """The flow property records a flow declares."""
    return [cast(Record, item) for item in cast(list[object], flow["flowProperties"])]


def _declared(flow: Record, property_id: str) -> Record:
    """The record of one flow property a flow declares."""
    for declared in _properties(flow):
        if _ref_id(declared["flowProperty"]) == property_id:
            return declared
    raise Invalid(f"flow {flow['name']} declares no flow property {property_id}")


def _reference(flow: Record) -> tuple[Record, float]:
    """The record of a flow's reference property and the factor it is given in."""
    declared = [item for item in _properties(flow) if _flag(item, "isRefFlowProperty")]
    if len(declared) != 1:
        raise Invalid(f"flow {flow['name']} declares {len(declared)} reference flow properties")
    return declared[0], float(cast(float, declared[0]["conversionFactor"]))


def _units(group: Record) -> list[Record]:
    """The units a unit group record holds."""
    return [cast(Record, unit) for unit in cast(list[object], group["units"])]


def _unit_group(
    groups: dict[str, Record], properties: dict[str, Record], property_id: str
) -> Record:
    """The unit group the flow property a record identifies is measured in."""
    return groups[_ref_id(properties[property_id]["unitGroup"])]


def _unit(group: Record, ref: object) -> Record:
    """The unit a unit group holds under the id a reference names, or else under its name."""
    by_id = [unit for unit in _units(group) if unit["@id"] == _ref_id(ref)]
    if by_id:
        return by_id[0]
    by_name = [unit for unit in _units(group) if unit["name"] == _ref_name(ref)]
    if by_name:
        return by_name[0]
    raise Invalid(f"unit group {group['name']} holds no unit {_ref_name(ref)}")


def _reference_unit(group: Record) -> Record:
    """The unit a unit group declares as its reference."""
    for unit in _units(group):
        if _flag(unit, "isRefUnit"):
            return unit
    raise Invalid(f"unit group {group['name']} declares no reference unit")


def _differs(unit: Record, reference: Record) -> bool:
    """Whether USLCI's factor for a unit, against its group's reference unit, is not the core's own
    by more than 1e-12 relatively; a unit the core's table lacks differs."""
    mine = float(cast(float, unit["conversionFactor"])) / float(
        cast(float, reference["conversionFactor"])
    )
    try:
        theirs = (
            units.by_symbol(cast(str, unit["name"])).factor
            / units.by_symbol(cast(str, reference["name"])).factor
        )
    except NotSupported:
        return True
    return abs(mine - theirs) > 1e-12 * max(abs(mine), abs(theirs))


def _rerouted(ref: object, entity: Record) -> Record:
    """A reference to another entity of the same kind, keeping what the record said of it."""
    return {**cast(Record, ref), "@id": entity["@id"], "name": entity["name"]}


def _scaled(exchange: Record, number: float) -> Record:
    """An exchange whose amount and distribution parameters are multiplied by a number, and whose
    formula says so; the geometric standard deviation does not move."""
    fixed: Record = {**exchange, "amount": float(cast(float, exchange["amount"])) * number}
    uncertainty = exchange.get("uncertainty")
    if uncertainty is not None:
        given = cast(Record, uncertainty)
        fixed["uncertainty"] = {
            **given,
            **{
                key: float(cast(float, given[key])) * number
                for key in SCALED
                if given.get(key) is not None
            },
        }
    formula = exchange.get("amountFormula")
    if formula is not None:
        fixed["amountFormula"] = f"({formula}) * {number}"
    return fixed


def _moved(
    exchange: Record,
    flow: Record,
    groups: dict[str, Record],
    properties: dict[str, Record],
) -> tuple[Record, float | None, str | None]:
    """An exchange in its flow's reference property and reference unit, with the number its amount
    and distribution were multiplied by, and the name of the unit it was moved out of when USLCI's
    factor for that unit is not the core's. The number is the factor of its unit over its
    property's reference unit, divided by the flow's factor for that property and multiplied by its
    factor for the reference one; an exchange already whole is unchanged."""
    reference, reference_factor = _reference(flow)
    given_id = _ref_id(exchange["flowProperty"])
    reference_id = _ref_id(reference["flowProperty"])
    given_group = _unit_group(groups, properties, given_id)
    given_unit = _unit(given_group, exchange["unit"])
    reference_unit = _reference_unit(_unit_group(groups, properties, reference_id))
    number = (
        float(cast(float, given_unit["conversionFactor"]))
        / float(cast(float, _reference_unit(given_group)["conversionFactor"]))
        / float(cast(float, _declared(flow, given_id)["conversionFactor"]))
        * reference_factor
    )
    by_property = given_id != reference_id
    if not by_property and not _differs(given_unit, reference_unit):
        return exchange, None, None
    fixed = _scaled(exchange, number)
    fixed["flowProperty"] = _rerouted(exchange["flowProperty"], properties[reference_id])
    fixed["unit"] = _rerouted(exchange["unit"], reference_unit)
    return fixed, number, None if by_property else str(given_unit["name"])


def _left_out(
    process: Record, exchange: Record, flow: Record, what: LeftOut, reason: str
) -> LeftOutRow:
    """One exchange a build leaves out, or writes without its distribution."""
    return LeftOutRow(
        process_id=cast(str, process["@id"]),
        process_name=cast(str, process["name"]),
        exchange_id=int(cast(int, exchange["internalId"])),
        flow_id=cast(str, flow["@id"]),
        flow_name=cast(str, flow["name"]),
        what=what,
        reason=reason,
    )


def _stated(exchange: Record) -> str | None:
    """The process id an input's description states as `defaultProvider.@id`, or nothing when its
    description is not a JSON object or names none."""
    description = exchange.get("description")
    if not isinstance(description, str):
        return None
    try:
        stated = json.loads(description)
    except json.JSONDecodeError:
        return None
    if not isinstance(stated, dict):
        return None
    named = stated.get("defaultProvider.@id")
    return named if isinstance(named, str) else None


def bridge_provider(exchange: Record, held: Collection[str]) -> str | None:
    """The process id a bridge input's description names as its provider, when `held` holds it: a
    description that is not a JSON object naming `defaultProvider.@id` names no provider, and one
    naming a process `held` lacks links nothing."""
    named = _stated(exchange)
    return named if named is not None and named in held else None


def _provider_ref(named: str, names: Mapping[str, str]) -> Record:
    """The reference a bundle writes for the input a description gives a provider."""
    return {"@type": "Process", "@id": named, "name": names[named]}


def _process(
    process: Record,
    flows: dict[str, Record],
    groups: dict[str, Record],
    properties: dict[str, Record],
    names: Mapping[str, str],
    left_out: list[LeftOutRow],
) -> _Rewritten:
    """A process with each exchange in its flow's reference property and reference unit, each
    distribution the core cannot hold written without it, each exchange it cannot hold left out and
    listed, and each input its description names a provider for written with that provider when
    `names` holds it."""
    written: list[object] = []
    converted = 0
    by_unit: dict[str, int] = {}
    linked = 0
    unlinked = 0
    for exchange in _exchanges(process):
        flow = flows.get(_ref_id(exchange["flow"]))
        moved = exchange
        if flow is not None:
            moved, number, unit = _moved(exchange, flow, groups, properties)
            converted += int(number is not None and unit is None)
            if unit is not None:
                by_unit[unit] = by_unit.get(unit, 0) + 1
            as_olca = o.Exchange.from_dict(moved)
            reason = exchange_refusal(as_olca, o.Flow.from_dict(flow))
            if reason is not None:
                left_out.append(_left_out(process, exchange, flow, "exchange", reason))
                continue
            refused = uncertainty_refusal(as_olca.uncertainty, as_olca.amount or 0.0)
            if refused is not None:
                moved = {key: value for key, value in moved.items() if key != "uncertainty"}
                left_out.append(_left_out(process, exchange, flow, "distribution", refused))
        stated = _stated(moved) if _flag(moved, "isInput") else None
        provider = bridge_provider(moved, names) if stated is not None else None
        if provider is not None:
            moved = {**moved, "defaultProvider": _provider_ref(provider, names)}
            linked += 1
        elif stated is not None:
            unlinked += 1
        written.append(moved)
    return _Rewritten(
        process={**process, "exchanges": written},
        converted=converted,
        by_unit=by_unit,
        linked=linked,
        unlinked=unlinked,
    )


def _rewritten(
    factor: Record,
    owner: str,
    flows: dict[str, Record],
    groups: dict[str, Record],
    properties: dict[str, Record],
) -> Record:
    """One factor whose unit is the one the written unit group holds under the name it names."""
    flow = flows[_ref_id(factor["flow"])]
    property_id = _ref_id(factor["flowProperty"])
    if not [item for item in _properties(flow) if _ref_id(item["flowProperty"]) == property_id]:
        raise Invalid(
            f"{owner}: {flow['name']} carries no flow property {_ref_name(factor['flowProperty'])}"
        )
    group = _unit_group(groups, properties, property_id)
    unit = _unit(group, factor["unit"])
    if unit["@id"] == _ref_id(factor["unit"]):
        return factor
    return {**factor, "unit": _rerouted(factor["unit"], unit)}


def _category(
    category: Record,
    method: Record,
    flows: dict[str, Record],
    groups: dict[str, Record],
    properties: dict[str, Record],
) -> Record:
    """A category whose every factor's unit the written bundle carries; a factor whose flow
    property the written flow lacks, or whose unit no group holds, stops the build."""
    factors = []
    for factor in cast(list[object], category["impactFactors"]):
        record = cast(Record, factor)
        owner = f"{method['name']}, {category['name']}, {_ref_name(record['flow'])}"
        factors.append(_rewritten(record, owner, flows, groups, properties))
    return {**category, "impactFactors": factors}


def _characterised(packages: Sequence[dict[str, bytes]]) -> set[str]:
    """The ids of the flows the method packages' categories characterise."""
    return {
        _ref_id(cast(Record, factor)["flow"])
        for members in packages
        for category in _records(members, CATEGORIES).values()
        for factor in cast(list[object], category["impactFactors"])
    }


def _used(processes: dict[str, Record], flows: dict[str, Record]) -> set[str]:
    """The ids of the elementary flows the processes use."""
    return {
        flow_id
        for process in processes.values()
        for flow_id in (_ref_id(exchange["flow"]) for exchange in _exchanges(process))
        if flow_id in flows and _flow_type(flows[flow_id]) == ELEMENTARY
    }


def build(
    inventory: Path,
    methods: Sequence[Path],
    *,
    version: str,
    out_dir: Path,
    bridged: Sequence[Path] = (),
) -> Built:
    """Write a release, the repositories its bridges link to and its methods as
    `<out_dir>/uslci-<version>.zip`, and the exchanges left out beside it as
    `left-out-<version>.csv`. An exchange is written in its flow's reference unit, converted with
    the own factor of the repository its process came from where that factor is not the core's. A
    bridge input whose description names a process the bundle holds is written with it as its
    provider. The bundle is checked whole but for its providers, which the import reports as
    unlinked inputs. A record two method packages both hold is the one of the package later in the
    sequence, the profile's newest last; a record the release and a bridged repository both hold is
    the release's."""
    destination = out_dir / f"uslci-{version}.zip"
    if destination.exists():
        raise Conflict(f"{destination.name} exists; name another destination")
    out_dir.mkdir(parents=True, exist_ok=True)
    release = _members(inventory)
    packages = [_members(path) for path in methods]
    bridged_folders = [_folders(_members(path)) for path in bridged]
    release_folders = _folders(release)
    groups = release_folders.get("unit_groups", {})
    properties = release_folders.get("flow_properties", {})
    flows = release_folders.get("flows", {})
    processes = release_folders.get("processes", {})
    joined: dict[str, dict[str, Record]] = {}
    taken: dict[str, set[str]] = {
        folder: set(records) for folder, records in release_folders.items()
    }
    for folders in bridged_folders:
        for folder, records in folders.items():
            if folder in ("flows", "processes"):
                continue
            for entity_id, record in records.items():
                if entity_id in taken.setdefault(folder, set()):
                    continue
                joined.setdefault(folder, {})[entity_id] = record
                taken[folder].add(entity_id)
    merged_flows = dict(flows)
    merged_processes = dict(processes)
    for folders in bridged_folders:
        for flow_id, flow in folders.get("flows", {}).items():
            merged_flows.setdefault(flow_id, flow)
        for process_id, process in folders.get("processes", {}).items():
            merged_processes.setdefault(process_id, process)
    used = _used(merged_processes, merged_flows)
    characterised = _characterised(packages)
    kept = {
        flow_id: flow
        for flow_id, flow in merged_flows.items()
        if _flow_type(flow) != ELEMENTARY or flow_id in used | characterised
    }
    added_flows: dict[str, Record] = {}
    added_properties: dict[str, Record] = {}
    added_groups: dict[str, Record] = {}
    written_methods: dict[str, bytes] = {}
    categories: dict[str, Record] = {}
    for members in packages:
        added_flows |= {i: r for i, r in _records(members, "flows").items() if i not in flows}
        added_properties |= {
            i: r for i, r in _records(members, "flow_properties").items() if i not in properties
        }
        added_groups |= {
            i: r for i, r in _records(members, "unit_groups").items() if i not in groups
        }
        written_methods |= {
            name: content
            for name, content in members.items()
            if name.startswith(f"{METHODS}/") or name.endswith("/")
        }
        held = _records(members, CATEGORIES)
        for method in _records(members, METHODS).values():
            for ref in cast(list[object], method["impactCategories"]):
                if _ref_id(ref) in held:
                    categories[_ref_id(ref)] = _category(
                        held[_ref_id(ref)],
                        method,
                        kept | added_flows,
                        groups | added_groups,
                        properties | added_properties,
                    )
    kept |= added_flows
    all_groups = groups | added_groups | joined.get("unit_groups", {})
    all_properties = properties | added_properties | joined.get("flow_properties", {})
    names = {
        process_id: cast(str, process["name"]) for process_id, process in merged_processes.items()
    }
    left_out: list[LeftOutRow] = []
    outcomes = [
        _process(process, kept, all_groups, all_properties, names, left_out)
        for process in processes.values()
    ]
    for folders in bridged_folders:
        own_groups = {**all_groups, **folders.get("unit_groups", {})}
        own_properties = {**all_properties, **folders.get("flow_properties", {})}
        outcomes.extend(
            _process(process, kept, own_groups, own_properties, names, left_out)
            for process_id, process in folders.get("processes", {}).items()
            if process_id not in processes
        )
    rewritten = {cast(str, outcome.process["@id"]): outcome.process for outcome in outcomes}
    converted = sum(outcome.converted for outcome in outcomes)
    unit_converted: dict[str, int] = {}
    for outcome in outcomes:
        for name, count in outcome.by_unit.items():
            unit_converted[name] = unit_converted.get(name, 0) + count
    linked = sum(outcome.linked for outcome in outcomes)
    unlinked = sum(outcome.unlinked for outcome in outcomes)
    written: dict[str, bytes] = {
        name: content
        for name, content in release.items()
        if name.endswith("/") or name.split("/", 1)[0] not in ("processes", "flows")
    }
    written |= {f"flows/{flow_id}.json": _serialised(flow) for flow_id, flow in kept.items()}
    written |= {f"processes/{i}.json": _serialised(p) for i, p in rewritten.items()}
    written |= {
        f"{folder}/{i}.json": _serialised(record)
        for folder, records in joined.items()
        for i, record in records.items()
    }
    written |= {f"flow_properties/{i}.json": _serialised(p) for i, p in added_properties.items()}
    written |= {f"unit_groups/{i}.json": _serialised(g) for i, g in added_groups.items()}
    written |= {f"{CATEGORIES}/{i}.json": _serialised(c) for i, c in categories.items()}
    written |= written_methods
    staged = destination.with_name(f"{destination.name}.partial")
    try:
        with zipfile.ZipFile(staged, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in written.items():
                archive.writestr(name, content)
        require_whole(staged, providers=False)
        read_background(staged, f"uslci-{version}", foreground=frozenset())
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    rows = tuple(sorted(left_out, key=lambda row: row.key))
    write_left_out(out_dir / f"left-out-{version}.csv", rows)
    return Built(
        bundle=destination,
        processes=len(rewritten),
        elementary_flows=sum(1 for flow in kept.values() if _flow_type(flow) == ELEMENTARY),
        methods=sum(1 for name in written if _record_member(name, METHODS)),
        categories=sum(1 for name in written if _record_member(name, CATEGORIES)),
        converted=converted,
        unit_converted=dict(sorted(unit_converted.items())),
        bridges_linked=linked,
        bridges_unlinked=unlinked,
        left_out=rows,
    )
