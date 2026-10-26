"""Whether every exchange of a JSON-LD bundle resolves to whole entities, and the one rule the
bundle's readers apply to find an input's provider."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipReader

from ecosemantic.errors import Invalid


@dataclass(frozen=True)
class Miss:
    """One exchange that does not resolve, and what it lacks."""

    process: str
    exchange: int
    flow: str
    lacks: str


def resolve_provider(default_provider: str | None, candidates: list[str]) -> tuple[str | None, str]:
    """An input's provider: the one it names when that one provides it, else the sole provider;
    with none, the reason."""
    if default_provider is not None:
        if default_provider in candidates:
            return default_provider, ""
        return None, "its provider is not in the package"
    if len(candidates) == 1:
        return candidates[0], ""
    if candidates:
        return None, "several processes produce it"
    return None, "no process produces it"


def providers(
    processes: Iterable[o.Process], flow_types: Mapping[str, o.FlowType]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The processes producing each product flow, and those treating each waste flow."""
    producers: dict[str, list[str]] = {}
    treaters: dict[str, list[str]] = {}
    for process in processes:
        for e in process.exchanges or []:
            if e.flow is None or e.flow.id not in flow_types:
                continue
            kind = flow_types[e.flow.id]
            if kind == o.FlowType.PRODUCT_FLOW and not e.is_input:
                producers.setdefault(e.flow.id, []).append(process.id)
            if kind == o.FlowType.WASTE_FLOW and e.is_input and e.is_quantitative_reference:
                treaters.setdefault(e.flow.id, []).append(process.id)
    return producers, treaters


def _takes_provider(e: o.Exchange, kind: o.FlowType | None) -> bool:
    if e.is_quantitative_reference:
        return False
    if kind == o.FlowType.PRODUCT_FLOW:
        return bool(e.is_input)
    return kind == o.FlowType.WASTE_FLOW and not e.is_input


def _resolved(
    processes: Sequence[o.Process], flows: Mapping[str, o.Flow]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The processes producing each product flow, and those treating each waste flow."""
    return providers(processes, {i: f.flow_type for i, f in flows.items()})


def _lack(
    e: o.Exchange,
    flows: Mapping[str, o.Flow],
    properties: Mapping[str, str | None],
    groups: Mapping[str, set[str]],
    producers: Mapping[str, list[str]],
    treaters: Mapping[str, list[str]],
    *,
    providers: bool,
) -> str | None:
    if e.flow is None or e.flow.id not in flows:
        return "its flow"
    flow = flows[e.flow.id]
    references = [fp for fp in flow.flow_properties or [] if fp.is_ref_flow_property]
    if len(references) != 1 or references[0].flow_property is None:
        return "one reference flow property on its flow"
    prop = references[0].flow_property.id
    if prop not in properties:
        return f"flow property {prop}"
    group = properties[prop]
    if group is None or group not in groups:
        return f"the unit group of flow property {prop}"
    if e.flow_property is None or e.flow_property.id != prop:
        return "its flow's reference property"
    unit = e.unit.name if e.unit is not None else None
    if unit not in groups[group]:
        return f"unit {unit} in its flow's unit group"
    if providers and _takes_provider(e, flow.flow_type):
        waste = flow.flow_type == o.FlowType.WASTE_FLOW
        candidates = (treaters if waste else producers).get(flow.id, [])
        named = e.default_provider.id if e.default_provider is not None else None
        provider, reason = resolve_provider(named, candidates)
        if provider is None:
            return f"a provider: {reason}"
    return None


def misses(bundle: Path, *, providers: bool = True) -> list[Miss]:
    """Every exchange of the bundle's processes whose flow, property, unit or provider does not
    resolve inside the bundle; the providers only when they are asked for, since a cut-off input
    is one the import reports unlinked."""
    with ZipReader(str(bundle)) as reader:
        groups = {g.id: {u.name for u in g.units or []} for g in reader.read_each(o.UnitGroup)}
        properties = {
            p.id: (p.unit_group.id if p.unit_group is not None else None)
            for p in reader.read_each(o.FlowProperty)
        }
        flows = {f.id: f for f in reader.read_each(o.Flow)}
        processes = list(reader.read_each(o.Process))
    producers, treaters = _resolved(processes, flows)
    found: list[Miss] = []
    for process in processes:
        for e in process.exchanges or []:
            lack = _lack(e, flows, properties, groups, producers, treaters, providers=providers)
            if lack is not None:
                name = (e.flow.name or e.flow.id) if e.flow is not None else ""
                found.append(
                    Miss(
                        process=process.name or process.id,
                        exchange=e.internal_id or 0,
                        flow=flows[e.flow.id].name if e.flow and e.flow.id in flows else name,
                        lacks=lack,
                    )
                )
    return found


def require_whole(bundle: Path, *, providers: bool = True) -> None:
    """Nothing, or Invalid naming every exchange that does not resolve and what it lacks; the
    providers only when they are asked for."""
    found = misses(bundle, providers=providers)
    if found:
        named = "; ".join(
            f"{m.process} exchange {m.exchange} ({m.flow}) lacks {m.lacks}" for m in found
        )
        raise Invalid(f"{len(found)} exchanges of {bundle.name} are not whole: {named}")
