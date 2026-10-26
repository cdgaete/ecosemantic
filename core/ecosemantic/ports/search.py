"""Text search over one background database."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ecosemantic.model.entities import Method
from ecosemantic.ports.types import ElementaryFlowHit, FlowType, Page, ProcessHit


@runtime_checkable
class SearchPort(Protocol):
    async def processes(
        self,
        database: str,
        query: str,
        location: str | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[ProcessHit]: ...

    async def elementary_flows(
        self,
        database: str,
        query: str,
        compartment: str | None = None,
        sub_compartment: str | None = None,
        flow_type: FlowType | None = None,
        unit: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> Page[ElementaryFlowHit]: ...

    async def methods(
        self, database: str, query: str, limit: int = 20, cursor: str | None = None
    ) -> Page[Method]: ...
