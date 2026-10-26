"""A stored base bundle: the processes a set of references reaches, their records copied byte
for byte, and the unit a base flow is measured in."""

from __future__ import annotations

import zipfile
from collections import deque
from collections.abc import Iterable
from pathlib import Path

import olca_schema as o
from olca_schema.zipio import ZipReader

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model import units
from ecosemantic.package.wholeness import providers, resolve_provider

RESOURCES = "elementary flows/resource"


class BaseBundle:
    """The bundle a base database was installed from, read once."""

    def __init__(self, path: Path, foreground: frozenset[str] = frozenset()) -> None:
        self.path = path
        self.zipped = zipfile.ZipFile(path)
        with ZipReader(str(path)) as reader:
            self.groups = {g.id: g for g in reader.read_each(o.UnitGroup)}
            self.properties = {p.id: p for p in reader.read_each(o.FlowProperty)}
            self.flows = {f.id: f for f in reader.read_each(o.Flow)}
            self.processes = {
                p.id: p for p in reader.read_each(o.Process) if p.id not in foreground
            }
            self.categories = list(reader.read_each(o.ImpactCategory))
            self.methods = list(reader.read_each(o.ImpactMethod))
        self.producers, self.treaters = providers(
            self.processes.values(), {i: f.flow_type for i, f in self.flows.items()}
        )
        self.members = set(self.zipped.namelist())

    def __enter__(self) -> BaseBundle:
        return self

    def __exit__(self, *_: object) -> None:
        self.zipped.close()

    def _inputs(self, process: o.Process) -> list[tuple[o.Exchange, str]]:
        found = []
        for e in process.exchanges or []:
            if e.flow is None or e.flow.id not in self.flows or e.is_quantitative_reference:
                continue
            kind = self.flows[e.flow.id].flow_type
            waste = kind == o.FlowType.WASTE_FLOW
            if (kind == o.FlowType.PRODUCT_FLOW and e.is_input) or (waste and not e.is_input):
                candidates = (self.treaters if waste else self.producers).get(e.flow.id, [])
                named = e.default_provider.id if e.default_provider is not None else None
                provider, _ = resolve_provider(named, candidates)
                if provider is not None:
                    found.append((e, provider))
        return found

    def closure(self, provider_ids: Iterable[str]) -> set[str]:
        """Every process the given ones reach through their providers, themselves included."""
        start = list(provider_ids)
        unknown = sorted(i for i in start if i not in self.processes)
        if unknown:
            raise NotFound(f"{self.path.name} holds no process {unknown}")
        reached = set(start)
        queue = deque(start)
        while queue:
            for _, provider in self._inputs(self.processes[queue.popleft()]):
                if provider not in reached:
                    reached.add(provider)
                    queue.append(provider)
        return reached

    def links(self, process_ids: set[str]) -> list[dict[str, dict[str, object]]]:
        """The openLCA process links of the processes' inputs, each to the provider the reader
        links it to, in process and exchange order."""
        out: list[dict[str, dict[str, object]]] = []
        for process_id in sorted(process_ids):
            process = self.processes[process_id]
            for e, provider in self._inputs(process):
                out.append(
                    {
                        "provider": {"@type": "Process", "@id": provider},
                        "flow": {"@type": "Flow", "@id": e.flow.id},
                        "process": {"@type": "Process", "@id": process_id},
                        "exchange": {"internalId": e.internal_id},
                    }
                )
        return out

    def read(self, member: str) -> bytes:
        """The bytes of one member, as the bundle holds them."""
        return self.zipped.read(member)

    def holds(self, member: str) -> bool:
        """Whether the bundle carries a member at this path."""
        return member in self.members

    def _flow_members(self, flow_id: str) -> set[str]:
        flow = self.flows[flow_id]
        out = {f"flows/{flow_id}.json"}
        for factor in flow.flow_properties or []:
            if factor.flow_property is None:
                continue
            prop = self.properties[factor.flow_property.id]
            out.add(f"flow_properties/{prop.id}.json")
            if prop.unit_group is not None:
                out.add(f"unit_groups/{prop.unit_group.id}.json")
        if flow.location is not None:
            out.add(f"locations/{flow.location.id}.json")
        return out

    def copy(self, target: zipfile.ZipFile, process_ids: set[str]) -> set[str]:
        """Write the processes, every flow, property, unit group and location they name, and
        every impact method with the flows its factors name, byte for byte."""
        members: set[str] = set()
        for process_id in process_ids:
            process = self.processes[process_id]
            members.add(f"processes/{process_id}.json")
            if process.location is not None:
                members.add(f"locations/{process.location.id}.json")
            for e in process.exchanges or []:
                if e.flow is not None and e.flow.id in self.flows:
                    members |= self._flow_members(e.flow.id)
        for category in self.categories:
            members.add(f"lcia_categories/{category.id}.json")
            for factor in category.impact_factors or []:
                if factor.flow is not None and factor.flow.id in self.flows:
                    members |= self._flow_members(factor.flow.id)
        members |= {f"lcia_methods/{m.id}.json" for m in self.methods}
        written = {m for m in members if m in self.members}
        for member in sorted(written):
            target.writestr(member, self.zipped.read(member))
        return written

    def flow_unit(self, flow_id: str, unit: str) -> tuple[o.Ref, o.Ref]:
        """The unit of the flow's unit group that the model unit names, and the flow's reference
        property; Invalid when the group holds no such unit. The platform holds an exchange in
        its provider's unit, which the reader keeps as its producers declare it."""
        flow = self.flows[flow_id]
        reference = next(fp for fp in flow.flow_properties or [] if fp.is_ref_flow_property)
        prop = self.properties[reference.flow_property.id]
        group = self.groups[prop.unit_group.id]
        names = set(units.by_name(unit).symbols) | {unit}
        found = next((u for u in group.units or [] if u.name in names), None)
        if found is None:
            held = sorted(u.name or "" for u in group.units or [])
            raise Invalid(f"{flow.name!r} is measured in {held}; its group holds no {unit!r}")
        return (
            o.Ref(ref_type=o.RefType.Unit, id=found.id, name=found.name),
            o.Ref(ref_type=o.RefType.FlowProperty, id=prop.id, name=prop.name),
        )

    def is_resource(self, flow_id: str) -> bool:
        """Whether an elementary flow is a resource the technosphere takes in."""
        return (self.flows[flow_id].category or "").lower().startswith(RESOURCES)
