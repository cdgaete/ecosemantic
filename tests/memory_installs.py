"""The install port over dictionaries: a second implementation that proves the port's
consumers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from ecosemantic.errors import NotFound
from ecosemantic.ports.types import (
    Account,
    DatabaseSource,
    Install,
    InstallDraft,
    InstallPatch,
)


class MemoryInstalls:
    """Install records held in memory, newest first."""

    def __init__(self) -> None:
        self._installs: dict[uuid.UUID, Install] = {}
        self._slot = asyncio.Lock()
        self._watchers: set[asyncio.Queue[uuid.UUID]] = set()

    def _announce(self, install_id: uuid.UUID) -> None:
        for queue in self._watchers:
            queue.put_nowait(install_id)

    def changes(self) -> AsyncIterator[uuid.UUID]:
        queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._watchers.add(queue)

        async def iterate() -> AsyncIterator[uuid.UUID]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._watchers.discard(queue)

        return iterate()

    def read_record(self, install_id: uuid.UUID) -> Install:
        """One install, read synchronously, as the filesystem store reads one."""
        if install_id not in self._installs:
            raise NotFound(f"no install {install_id}")
        return self._installs[install_id]

    def apply_patch(self, install_id: uuid.UUID, patch: InstallPatch) -> Install:
        """The record with the patch's named fields applied."""
        self._installs[install_id] = patch.applied_to(self.read_record(install_id))
        return self._installs[install_id]

    async def post_install(self, draft: InstallDraft) -> Install:
        install = Install(id=uuid.uuid4(), draft=draft, posted_at=datetime.now(UTC))
        self._installs[install.id] = install
        return install

    async def get_install(self, install_id: uuid.UUID) -> Install:
        return self.read_record(install_id)

    async def list_installs(self) -> list[Install]:
        return sorted(self._installs.values(), key=lambda i: (i.posted_at, str(i.id)), reverse=True)

    async def cancel_install(self, install_id: uuid.UUID) -> Install:
        asked = self.apply_patch(install_id, self.read_record(install_id).cancellation())
        self._announce(asked.id)
        return asked

    async def update_install(self, install_id: uuid.UUID, patch: InstallPatch) -> Install:
        install = self.apply_patch(install_id, patch)
        self._announce(install.id)
        return install

    def slot(self) -> asyncio.Lock:
        """The workspace's one-install slot, which only this process shares."""
        return self._slot


class MemoryInstaller:
    """A launcher with no process: it records who it was asked to start, names the pid it would
    have started, and holds every install it started alive unless it is named dead."""

    def __init__(self, sources: list[DatabaseSource]) -> None:
        self._sources = sources
        self.started: list[tuple[uuid.UUID, Account | None]] = []
        self.dead: set[uuid.UUID] = set()

    def sources(self) -> list[DatabaseSource]:
        return self._sources

    def start(self, install_id: uuid.UUID, account: Account | None) -> int:
        self.started.append((install_id, account))
        return 4242

    def alive(self, install_id: uuid.UUID) -> bool:
        return install_id not in self.dead
