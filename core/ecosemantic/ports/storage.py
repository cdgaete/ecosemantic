"""Foreground persistence and the request queue beside it. Every write names its actor."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.ports.types import (
    Layout,
    LogEntry,
    Outcome,
    ProductSystemSummary,
    Request,
    RequestDraft,
    Restored,
    Source,
    StoreChange,
)


@runtime_checkable
class StoragePort(Protocol):
    async def list_product_systems(self) -> list[ProductSystemSummary]: ...

    async def get_product_system(self, product_system_id: uuid.UUID) -> ProductSystem: ...

    async def get_version(
        self, product_system_id: uuid.UUID, content_hash: str
    ) -> ProductSystem: ...

    async def put_product_system(
        self, product_system: ProductSystem, actor: Actor, message: str, source: Source = "mcp"
    ) -> LogEntry: ...

    async def delete_product_system(self, product_system_id: uuid.UUID, actor: Actor) -> None: ...

    async def log(self, product_system_id: uuid.UUID) -> list[LogEntry]: ...

    async def get_layout(self, product_system_id: uuid.UUID) -> Layout: ...

    async def put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout: ...

    async def post_request(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request: ...

    async def list_requests(
        self, product_system_id: uuid.UUID, open_only: bool = False
    ) -> list[Request]: ...

    async def resolve_request(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request: ...

    async def return_package(
        self,
        product_system_id: uuid.UUID,
        exported_root: Path,
        actor: Actor,
        at_entry: int | None = None,
    ) -> LogEntry:
        """Store an export openLCA returns over the stored system, as of the log entry
        `at_entry` states or its base tag names."""
        ...

    async def export_package(self, product_system_id: uuid.UUID, destination: Path) -> None:
        """Write the stored package whole, sidecar and versions included, as a zip."""
        ...

    async def restore_package(self, source: Path) -> Restored:
        """Hold the zipped package: added when absent, unchanged when held at the same state;
        Conflict when held at another."""
        ...

    def changes(self) -> AsyncIterator[StoreChange]: ...
