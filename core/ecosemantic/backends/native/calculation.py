"""The calculation port over the engine: each database's calculation solved on the store's thread,
its labels named for people from the catalog and the product systems."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

from ecosemantic.backends.native.store import NativeStore
from ecosemantic.compute.links import linked_credit_loops
from ecosemantic.compute.montecarlo import should_stop, summarize_samples, worst_rel_se
from ecosemantic.engine.calculation import Calculation, Solution
from ecosemantic.engine.foreground import Foreground
from ecosemantic.engine.montecarlo import MonteCarlo, Refactorised, Serial
from ecosemantic.engine.paths import PathNode
from ecosemantic.errors import Invalid, OtherBuild
from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef, LinkedProcessRef
from ecosemantic.model.validation import credit_loops, off_build
from ecosemantic.ports.calculation import CUTOFF, MAX_LEVEL, MAX_NODES, TOP_N
from ecosemantic.ports.types import (
    Activity,
    FlowHotspot,
    FlowHotspots,
    FlowType,
    Hotspot,
    Hotspots,
    InventoryResult,
    InventoryRow,
    LinkedLoop,
    MonteCarloCategory,
    MonteCarloConfig,
    MonteCarloResult,
    Score,
    Stopped,
    System,
    Tree,
    TreeKind,
    TreeNode,
    fraction_of,
)

T = TypeVar("T")
TreeRef = BackgroundRef | ForegroundRef | LinkedProcessRef | ElementaryFlowRef


@dataclass(frozen=True)
class Named:
    """A background activity as people read it."""

    name: str
    location: str | None
    reference_product: str

    def label(self) -> str:
        """The activity as a sentence names it: its name, and its location when it has one."""
        return f"{self.name} [{self.location}]" if self.location else self.name


@dataclass(frozen=True)
class NamedFlow:
    """An elementary flow as people read it."""

    name: str
    compartment: str
    sub_compartment: str | None
    flow_type: FlowType
    unit: str


class NativeCalculation:
    """Life cycle calculations over the store's databases, each on its engine calculation."""

    def __init__(self, store: NativeStore) -> None:
        self.store = store

    def _activities(self, database: str, labels: Iterable[str]) -> dict[str, Named]:
        wanted = sorted(set(labels))
        if not wanted:
            return {}
        rows = (
            self.store.catalog(database)
            .execute(
                "SELECT native_id, name, location, reference_product FROM processes"
                " WHERE native_id IN (SELECT unnest($labels))",
                {"labels": wanted},
            )
            .fetchall()
        )
        return {label: Named(name, location, product) for label, name, location, product in rows}

    def _flows(self, database: str, labels: Iterable[str]) -> dict[str, NamedFlow]:
        wanted = sorted(set(labels))
        if not wanted:
            return {}
        rows = (
            self.store.catalog(database)
            .execute(
                "SELECT code, name, compartment, sub_compartment, flow_type, unit FROM flows"
                " WHERE code IN (SELECT unnest($labels))",
                {"labels": wanted},
            )
            .fetchall()
        )
        return {row[0]: NamedFlow(*row[1:]) for row in rows}

    def _foreground(self, calculation: Calculation, system: System) -> Foreground | None:
        if system.product_system is None:
            return None
        return calculation.foreground(system.product_system, system.linked)

    def _require_build(self, system: System) -> None:
        """OtherBuild when the product system, or a system it links, names a build of the
        database other than the installed one, or none."""
        if system.product_system is None:
            return
        installed = self.store.registered(system.database).database
        off = off_build([system.product_system, *system.linked.values()], installed)
        if off:
            raise OtherBuild(
                off[0].name, installed.name, off[0].database.fingerprint, installed.fingerprint
            )

    async def _run(self, system: System, fn: Callable[[Calculation], T]) -> T:
        self._require_build(system)
        return await self.store.run(
            system.database, lambda: fn(self.store.calculation(system.database))
        )

    def _total(self, calculation: Calculation, solution: Solution, method: Method) -> float:
        return float(calculation.scores(solution, [method]).data[0])

    async def score(self, system: System, demand: list[DemandItem], method: Method) -> Score:
        return (await self.scores(system, demand, [method]))[0]

    async def scores(
        self, system: System, demand: list[DemandItem], methods: list[Method]
    ) -> list[Score]:
        def run(calculation: Calculation) -> list[Score]:
            solution = calculation.solve(self._foreground(calculation, system), demand)
            values = calculation.scores(solution, methods).data
            return [
                Score(value=float(value), unit=method.unit, method=method)
                for value, method in zip(values, methods, strict=True)
            ]

        return await self._run(system, run)

    async def supply(self, system: System, demand: list[DemandItem]) -> list[Activity]:
        def run(calculation: Calculation) -> list[Activity]:
            foreground = self._foreground(calculation, system)
            if foreground is None:
                return []
            levels = calculation.supply(foreground, demand).data
            return [
                Activity(ref=foreground.ref(j), level=float(level))
                for j, level in enumerate(levels)
            ]

        return await self._run(system, run)

    async def hotspots(
        self, system: System, demand: list[DemandItem], method: Method, top_n: int = TOP_N
    ) -> Hotspots:
        def run(calculation: Calculation) -> Hotspots:
            foreground = self._foreground(calculation, system)
            solution = calculation.solve(foreground, demand)
            total = self._total(calculation, solution, method)
            split = calculation.by_process(solution, method)
            background, own = split.background.data, split.foreground.data
            ranked = [(float(background[i]), False, int(i)) for i in np.flatnonzero(background)]
            ranked += [(float(own[j]), True, int(j)) for j in np.flatnonzero(own)]
            ranked.sort(key=lambda entry: -abs(entry[0]))
            top = ranked[:top_n]
            labels = calculation.background.coords["activity"].labels
            named = self._activities(
                system.database, (str(labels[i]) for _, fg, i in top if not fg)
            )
            items = []
            for rank, (value, is_foreground, at) in enumerate(top, start=1):
                if is_foreground and foreground is not None:
                    process = foreground.columns[at].process
                    ref: BackgroundRef | ForegroundRef | LinkedProcessRef = foreground.ref(at)
                    found = Named(process.name, process.location, process.reference_product)
                else:
                    ref = BackgroundRef(database=system.database, id=str(labels[at]))
                    found = named[ref.id]
                items.append(
                    Hotspot(
                        rank=rank,
                        ref=ref,
                        name=found.name,
                        location=found.location,
                        reference_product=found.reference_product,
                        score=value,
                        fraction=fraction_of(value, total),
                    )
                )
            return Hotspots(total=Score(value=total, unit=method.unit, method=method), items=items)

        return await self._run(system, run)

    async def flow_hotspots(
        self, system: System, demand: list[DemandItem], method: Method, top_n: int = TOP_N
    ) -> FlowHotspots:
        def run(calculation: Calculation) -> FlowHotspots:
            solution = calculation.solve(self._foreground(calculation, system), demand)
            scores = calculation.by_flow(solution, method).data
            total = float(scores.sum())
            ranked = sorted(np.flatnonzero(scores), key=lambda row: -abs(scores[row]))[:top_n]
            labels = calculation.background.coords["flow"].labels
            flows = self._flows(system.database, (str(labels[row]) for row in ranked))
            elementary_flows = self.store.registered(system.database).database.elementary_flows
            items = []
            for rank, row in enumerate(ranked, start=1):
                flow = flows[str(labels[row])]
                items.append(
                    FlowHotspot(
                        rank=rank,
                        flow=ElementaryFlowRef(database=elementary_flows, id=str(labels[row])),
                        name=flow.name,
                        compartment=flow.compartment,
                        amount=float(solution.inventory.data[row]),
                        unit=flow.unit,
                        score=float(scores[row]),
                        fraction=fraction_of(float(scores[row]), total),
                    )
                )
            return FlowHotspots(
                total=Score(value=total, unit=method.unit, method=method), items=items
            )

        return await self._run(system, run)

    async def contribution_tree(
        self,
        system: System,
        demand: list[DemandItem],
        method: Method,
        max_level: int = MAX_LEVEL,
        max_nodes: int = MAX_NODES,
        cutoff: float = CUTOFF,
    ) -> Tree:
        if len(demand) != 1 or not isinstance(demand[0].ref, ForegroundRef):
            raise Invalid("a contribution tree takes exactly one foreground demand item")

        def run(calculation: Calculation) -> Tree:
            foreground = self._foreground(calculation, system)
            if foreground is None:
                raise Invalid("a contribution tree needs a product_system")
            walked = calculation.paths(foreground, demand[0], method, max_level, max_nodes, cutoff)
            nodes = _nodes(walked.root)
            activities = self._activities(
                system.database, (n.label for n in nodes if n.kind == "activity" and n.label)
            )
            flows = self._flows(
                system.database, (n.label for n in nodes if n.kind == "flow" and n.label)
            )
            elementary_flows = self.store.registered(system.database).database.elementary_flows

            def described(node: PathNode) -> tuple[TreeKind, TreeRef | None, str, str | None]:
                if node.kind == "remainder" or node.label is None:
                    return "remainder", None, "remainder", ""
                if node.kind == "flow":
                    flow = flows[node.label]
                    ref = ElementaryFlowRef(database=elementary_flows, id=node.label)
                    return "elementary_flow", ref, flow.name, flow.compartment
                if node.kind == "process":
                    process = foreground.columns[node.position].process
                    return "process", foreground.ref(node.position), process.name, process.location
                activity = activities[node.label]
                ref = BackgroundRef(database=system.database, id=node.label)
                return "process", ref, activity.name, activity.location

            def node_of(node: PathNode) -> TreeNode:
                kind, ref, name, location = described(node)
                return TreeNode(
                    kind=kind,
                    ref=ref,
                    name=name,
                    location=location,
                    score=node.score,
                    fraction=fraction_of(node.score, walked.total),
                    level=node.level,
                    children=[node_of(child) for child in node.children],
                )

            return Tree(
                total=Score(value=walked.total, unit=method.unit, method=method),
                root=node_of(walked.root),
                truncated=walked.truncated,
            )

        return await self._run(system, run)

    async def inventory(self, system: System, demand: list[DemandItem]) -> InventoryResult:
        def run(calculation: Calculation) -> InventoryResult:
            foreground = self._foreground(calculation, system)
            found = calculation.inventory(calculation.solve(foreground, demand))
            amounts = found.amounts.data
            labels = calculation.background.coords["flow"].labels
            nonzero = [int(row) for row in np.flatnonzero(amounts)]
            flows = self._flows(system.database, (str(labels[row]) for row in nonzero))
            columns = (
                {str(label): j for j, label in enumerate(foreground.labels)}
                if foreground is not None
                else {}
            )
            elementary_flows = self.store.registered(system.database).database.elementary_flows
            rows = []
            for row in nonzero:
                label = str(labels[row])
                flow = flows[label]
                source = found.sources[label]
                rows.append(
                    InventoryRow(
                        flow=ElementaryFlowRef(database=elementary_flows, id=label),
                        name=flow.name,
                        compartment=flow.compartment,
                        sub_compartment=flow.sub_compartment,
                        flow_type=flow.flow_type,
                        unit=flow.unit,
                        amount=float(amounts[row]),
                        source=None
                        if source is None or foreground is None
                        else foreground.ref(columns[source]),
                    )
                )
            return InventoryResult(rows=rows, floor=found.floor, dropped=found.dropped)

        return await self._run(system, run)

    async def monte_carlo(
        self,
        system: System,
        demand: list[DemandItem],
        methods: list[Method],
        config: MonteCarloConfig,
        on_iteration: Callable[[int, float | None], bool] | None = None,
    ) -> MonteCarloResult:
        def run(calculation: Calculation) -> MonteCarloResult:
            foreground = self._foreground(calculation, system)
            sampler = MonteCarlo(
                calculation,
                foreground,
                demand,
                methods,
                scope=config.scope,
                seed=config.seed,
                solve=Refactorised(self.store.solver),
            )
            pins = (
                {c.system: c.at_hash for c in foreground.columns if c.at_hash is not None}
                if foreground is not None
                else {}
            )
            samples: list[list[float]] = [[] for _ in methods]
            dropped: list[int] = []
            dropped_loops: list[list[str]] = []
            dropped_linked: list[LinkedLoop] = []
            failing: list[str] = []
            limit = config.n if config.n is not None else config.n_max
            stopped: Stopped = "fixed" if config.n is not None else "ceiling"
            for draw in Serial().run(sampler, range(limit)):
                if draw.scores is None:
                    dropped.append(draw.index)
                    for owned in draw.short:
                        if owned.system not in pins:
                            if owned.loop.codes not in dropped_loops:
                                dropped_loops.append(owned.loop.codes)
                            continue
                        linked = LinkedLoop(
                            product_system_id=owned.system,
                            at_hash=pins[owned.system],
                            codes=owned.loop.codes,
                        )
                        if linked not in dropped_linked:
                            dropped_linked.append(linked)
                    failing += [label for label in draw.failing if label not in failing]
                else:
                    for at, value in enumerate(draw.scores):
                        samples[at].append(float(value))
                if on_iteration is not None:
                    reached = worst_rel_se(samples)[0] if samples[0] else None
                    if not on_iteration(draw.index + 1, reached):
                        stopped = "cancelled"
                        break
                if (
                    config.n is None
                    and draw.index + 1 >= config.n_min
                    and should_stop(samples, config.n_min, config.rel_se_target)
                ):
                    stopped = "target"
                    break
            named = self._activities(system.database, failing)
            dropped_background = [named[label].label() for label in failing]
            if not samples[0]:
                linked_names = foreground.linked_names if foreground is not None else {}
                names = "; ".join(
                    [", ".join(codes) for codes in dropped_loops]
                    + [
                        f"{', '.join(n.codes)} of {linked_names[n.product_system_id]}"
                        for n in dropped_linked
                    ]
                    + dropped_background
                )
                raise Invalid(
                    f"all {len(dropped)} draws were dropped: {names} used as much of their "
                    "products as they made in each; narrow the distributions on their amounts"
                )
            _, gating = worst_rel_se(samples)
            return MonteCarloResult(
                database=self.store.registered(system.database).database,
                n=len(samples[0]),
                stopped=stopped,
                gating_method=methods[gating],
                scope=config.scope,
                normals_at_amount=sampler.normals_at_amount,
                credit_loops=credit_loops(system.product_system)
                if system.product_system is not None
                else [],
                dropped_draws=dropped,
                dropped_loops=dropped_loops,
                dropped_background=dropped_background,
                linked_credit_loops=linked_credit_loops(system.linked.values()),
                dropped_linked_loops=dropped_linked,
                categories=[
                    MonteCarloCategory(
                        method=method, summary=summarize_samples(samples[at]), samples=samples[at]
                    )
                    for at, method in enumerate(methods)
                ],
            )

        return await self._run(system, run)


def _nodes(root: PathNode) -> Sequence[PathNode]:
    """Every node of a walk."""
    found = [root]
    for child in root.children:
        found += _nodes(child)
    return found
