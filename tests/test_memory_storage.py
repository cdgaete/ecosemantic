from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from ecosemantic.errors import NotSupported
from ecosemantic.ports.storage import StoragePort
from tests.conformance.storage import StorageConformance
from tests.memory_storage import MemoryStorage


class TestMemoryStorage(StorageConformance):
    @pytest.fixture
    def storage(self) -> MemoryStorage:
        return MemoryStorage()

    def test_satisfies_the_port(self, storage: MemoryStorage) -> None:
        assert isinstance(storage, StoragePort)


async def test_memory_storage_holds_no_package(tmp_path: Path) -> None:
    with pytest.raises(NotSupported, match="no package"):
        await MemoryStorage().export_package(uuid.uuid4(), tmp_path / "p.zip")
