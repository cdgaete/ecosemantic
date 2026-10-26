"""Read-only access to a background database."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ecosemantic.model.entities import Method
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef
from ecosemantic.ports.types import BackgroundProcess, Compartment, ElementaryFlow


@runtime_checkable
class InventoryPort(Protocol):
    async def list_databases(self) -> list[Database]: ...

    async def get_database(self, name: str) -> Database: ...

    async def get_process(
        self, ref: BackgroundRef, exchanges: bool = False
    ) -> BackgroundProcess: ...

    async def get_elementary_flow(self, ref: ElementaryFlowRef) -> ElementaryFlow: ...

    async def missing(
        self, refs: Sequence[BackgroundRef | ElementaryFlowRef]
    ) -> list[BackgroundRef | ElementaryFlowRef]: ...

    async def treatments(self, refs: Sequence[BackgroundRef]) -> list[BackgroundRef]: ...

    async def list_methods(
        self, database: str, impact_method: str | None = None
    ) -> list[Method]: ...

    async def resolve_method(self, database: str, reference: str) -> Method: ...

    async def list_units(self, database: str) -> list[str]: ...

    async def list_locations(self, database: str) -> list[str]: ...

    async def list_compartments(self, database: str) -> list[Compartment]: ...
