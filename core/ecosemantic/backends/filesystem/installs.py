"""The install port over a directory: one folder per install under the data directory."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from filelock import AsyncFileLock

from ecosemantic.backends.filesystem.records import RecordFolder, newest_first
from ecosemantic.ports.types import Install, InstallDraft, InstallPatch

INSTALLS_DIR = "installs"
INSTALL_FILE = "install.json"
UPLOADS_DIR = "uploads"


def install_dir(root: Path, install_id: uuid.UUID) -> Path:
    """The directory of one install under the data directory, whether or not it exists yet."""
    return root / INSTALLS_DIR / str(install_id)


def uploads_dir(root: Path) -> Path:
    """The directory a package uploaded for an install is written to before that install reads
    it."""
    return root / INSTALLS_DIR / UPLOADS_DIR


class FilesystemInstalls:
    """Install records as one JSON file per install, newest first by the time they were posted.

    The install process writes a record from its own process while the server reads it, so a
    record is replaced whole and every change is read and written under a lock both take.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.records = RecordFolder(root, INSTALLS_DIR, INSTALL_FILE, Install, "install")

    def read_record(self, install_id: uuid.UUID) -> Install:
        """One install, read synchronously; the install process's callback runs off the event
        loop."""
        return self.records.read(install_id)

    def apply_patch(self, install_id: uuid.UUID, patch: InstallPatch) -> Install:
        """The record with the patch's named fields applied, written synchronously."""
        return self.records.patch(install_id, patch.applied_to)

    async def post_install(self, draft: InstallDraft) -> Install:
        install = Install(id=uuid.uuid4(), draft=draft, posted_at=datetime.now(UTC))
        return await asyncio.to_thread(self.records.write, install.id, install)

    async def get_install(self, install_id: uuid.UUID) -> Install:
        return await asyncio.to_thread(self.read_record, install_id)

    async def list_installs(self) -> list[Install]:
        return newest_first(await asyncio.to_thread(self.records.all))

    async def cancel_install(self, install_id: uuid.UUID) -> Install:
        def ask() -> Install:
            return self.records.patch(
                install_id, lambda install: install.cancellation().applied_to(install)
            )

        return await asyncio.to_thread(ask)

    async def update_install(self, install_id: uuid.UUID, patch: InstallPatch) -> Install:
        return await asyncio.to_thread(self.apply_patch, install_id, patch)

    def slot(self) -> AsyncFileLock:
        """The workspace's one-install slot, which every process over this directory shares."""
        return self.records.slot()

    def changes(self) -> AsyncIterator[uuid.UUID]:
        """Every install any process wrote, from the moment this is called."""
        return self.records.changed()
