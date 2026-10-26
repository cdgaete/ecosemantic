"""A free-form query over a graph-shaped backend. Declared here, implemented by deployments."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import JsonValue


@runtime_checkable
class GraphQueryPort(Protocol):
    async def query(
        self, database: str, statement: str, parameters: dict[str, JsonValue] | None = None
    ) -> list[dict[str, JsonValue]]: ...
