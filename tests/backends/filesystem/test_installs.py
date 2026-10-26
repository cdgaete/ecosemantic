from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.installs import (
    INSTALL_FILE,
    FilesystemInstalls,
    install_dir,
    uploads_dir,
)
from ecosemantic.errors import Unavailable
from ecosemantic.ports.install import InstallPort
from ecosemantic.ports.types import InstallPatch
from tests.conformance.installs import InstallConformance, draft


async def entering(installs: FilesystemInstalls) -> None:
    """Take the workspace's slot in a flow of its own, as a second server on this directory
    would, and give it straight back."""
    async with installs.slot():
        pass


class TestFilesystemInstalls(InstallConformance):
    @pytest.fixture
    def installs(self, tmp_path: Path) -> FilesystemInstalls:
        return FilesystemInstalls(tmp_path)

    def test_satisfies_the_port(self, installs: FilesystemInstalls) -> None:
        assert isinstance(installs, InstallPort)

    async def test_an_install_is_a_record_under_installs_in_the_data_directory(
        self, installs: FilesystemInstalls, tmp_path: Path
    ) -> None:
        posted = await installs.post_install(draft())
        assert install_dir(tmp_path, posted.id) == tmp_path / "installs" / str(posted.id)
        assert (install_dir(tmp_path, posted.id) / INSTALL_FILE).is_file()
        assert await FilesystemInstalls(tmp_path).get_install(posted.id) == posted

    def test_an_upload_is_written_under_the_installs_directory(self, tmp_path: Path) -> None:
        assert uploads_dir(tmp_path) == tmp_path / "installs" / "uploads"

    async def test_nothing_is_listed_before_the_first_install(
        self, installs: FilesystemInstalls
    ) -> None:
        assert await installs.list_installs() == []

    async def test_a_second_store_on_the_same_directory_waits_for_the_slot(
        self, installs: FilesystemInstalls, tmp_path: Path
    ) -> None:
        second = FilesystemInstalls(tmp_path)
        async with installs.slot():
            waiting = asyncio.create_task(entering(second))
            await asyncio.sleep(0.5)
            # filelock refuses a wait its own task's hold would deadlock, so the second flow is
            # a task of its own, as a second server is a process of its own
            assert not waiting.done()
        await asyncio.wait_for(waiting, timeout=5)

    async def test_a_record_this_version_cannot_read_is_unavailable_naming_its_folder(
        self, installs: FilesystemInstalls, tmp_path: Path
    ) -> None:
        posted = await installs.post_install(draft())
        record = install_dir(tmp_path, posted.id) / INSTALL_FILE
        stored = json.loads(record.read_text(encoding="utf-8"))
        del stored["draft"]
        record.write_text(json.dumps(stored), encoding="utf-8")
        for read in (lambda: installs.get_install(posted.id), installs.list_installs):
            with pytest.raises(Unavailable) as caught:
                await read()
            assert str(posted.id) in str(caught.value) and "draft" in str(caught.value)
            assert caught.value.hint is not None and str(record.parent) in caught.value.hint


async def test_an_install_written_by_another_instance_is_announced(tmp_path: Path) -> None:
    watcher = FilesystemInstalls(tmp_path)
    writer = FilesystemInstalls(tmp_path)
    posted = await writer.post_install(draft())
    changes = watcher.changes()
    await writer.update_install(posted.id, InstallPatch(status="running"))
    assert await asyncio.wait_for(anext(changes), 5) == posted.id
