"""Life cycle calculations on a resolved system. Each call returns its result."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.ports.types import (
    Activity,
    FlowHotspots,
    Hotspots,
    InventoryResult,
    MonteCarloConfig,
    MonteCarloResult,
    Score,
    System,
    Tree,
)

TOP_N = 10
MAX_LEVEL = 3
MAX_NODES = 50
CUTOFF = 0.001


@runtime_checkable
class CalculationPort(Protocol):
    async def score(self, system: System, demand: list[DemandItem], method: Method) -> Score: ...

    async def scores(
        self, system: System, demand: list[DemandItem], methods: list[Method]
    ) -> list[Score]: ...

    async def hotspots(
        self, system: System, demand: list[DemandItem], method: Method, top_n: int = TOP_N
    ) -> Hotspots: ...

    async def flow_hotspots(
        self, system: System, demand: list[DemandItem], method: Method, top_n: int = TOP_N
    ) -> FlowHotspots: ...

    async def contribution_tree(
        self,
        system: System,
        demand: list[DemandItem],
        method: Method,
        max_level: int = MAX_LEVEL,
        max_nodes: int = MAX_NODES,
        cutoff: float = CUTOFF,
    ) -> Tree: ...

    async def supply(self, system: System, demand: list[DemandItem]) -> list[Activity]: ...

    async def inventory(self, system: System, demand: list[DemandItem]) -> InventoryResult: ...

    async def monte_carlo(
        self,
        system: System,
        demand: list[DemandItem],
        methods: list[Method],
        config: MonteCarloConfig,
        on_iteration: Callable[[int, float | None], bool] | None = None,
    ) -> MonteCarloResult: ...
