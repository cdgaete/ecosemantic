"""Read-only access to a background database."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ecosemantic.errors import NotFound
from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.types import (
    BackgroundProcess,
    ClassificationScheme,
    ClassificationValue,
    Compartment,
    DatabaseSummary,
    ElementaryFlow,
    Factor,
    Location,
    Page,
    WeightingSet,
)


def no_flow(ref: ElementaryFlowRef) -> NotFound:
    """The miss every inventory raises for a flow a database it serves does not hold."""
    return NotFound(f"no flow {ref.id!r} in {ref.database!r}")


@runtime_checkable
class InventoryPort(Protocol):
    async def list_databases(self) -> list[Database]: ...

    async def get_database(self, name: str) -> Database: ...

    async def get_process(
        self, ref: BackgroundRef, exchanges: bool = False
    ) -> BackgroundProcess: ...

    async def get_elementary_flow(self, ref: ElementaryFlowRef) -> ElementaryFlow: ...

    async def get_elementary_flows(
        self, database: str, ids: Sequence[str]
    ) -> list[ElementaryFlow]: ...

    async def missing(
        self, refs: Sequence[BackgroundRef | ElementaryFlowRef]
    ) -> list[BackgroundRef | ElementaryFlowRef]: ...

    async def treatments(self, refs: Sequence[BackgroundRef]) -> list[BackgroundRef]: ...

    async def list_methods(
        self, database: str, impact_method: str | None = None
    ) -> list[Method]: ...

    async def weighting_sets(self, database: str, impact_method: str) -> list[WeightingSet]: ...

    async def resolve_method(self, database: str, reference: str) -> Method: ...

    async def list_units(self, database: str) -> list[str]: ...

    async def list_locations(self, database: str) -> list[Location]: ...

    async def list_compartments(self, database: str) -> list[Compartment]: ...

    async def summarize(self, database: str) -> DatabaseSummary: ...

    async def list_classifications(self, database: str) -> list[ClassificationScheme]: ...

    async def classification_values(
        self, database: str, scheme: str
    ) -> list[ClassificationValue]: ...

    async def factors(
        self,
        database: str,
        method_id: str,
        query: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[Factor]: ...
