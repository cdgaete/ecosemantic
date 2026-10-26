"""Installing a database: the records a caller posts and follows, and who starts its process."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from ecosemantic.ports.types import Account, DatabaseSource, Install, InstallDraft, InstallPatch


@runtime_checkable
class InstallPort(Protocol):
    async def post_install(self, draft: InstallDraft) -> Install: ...

    async def get_install(self, install_id: uuid.UUID) -> Install: ...

    async def list_installs(self) -> list[Install]: ...

    async def cancel_install(self, install_id: uuid.UUID) -> Install: ...

    async def update_install(self, install_id: uuid.UUID, patch: InstallPatch) -> Install: ...

    def slot(self) -> AbstractAsyncContextManager[object]: ...

    def changes(self) -> AsyncIterator[uuid.UUID]: ...


class InstallLauncher(Protocol):
    """The sources an install may come from, and the process that carries one."""

    def sources(self) -> list[DatabaseSource]: ...

    def start(self, install_id: uuid.UUID, account: Account | None) -> int: ...

    def alive(self, install_id: uuid.UUID) -> bool: ...
