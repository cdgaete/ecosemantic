from __future__ import annotations

import pytest

from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.search import SearchPort
from tests.conformance.inventory import InventoryConformance
from tests.conformance.search import SearchConformance
from tests.memory_background import MemoryInventory, MemorySearch


class TestMemoryInventory(InventoryConformance):
    @pytest.fixture(scope="class")
    @classmethod
    def inventory(cls) -> MemoryInventory:
        return MemoryInventory()

    def test_satisfies_the_port(self, inventory: MemoryInventory) -> None:
        assert isinstance(inventory, InventoryPort)


class TestMemorySearch(SearchConformance):
    @pytest.fixture(scope="class")
    @classmethod
    def search(cls) -> MemorySearch:
        return MemorySearch()

    def test_satisfies_the_port(self, search: MemorySearch) -> None:
        assert isinstance(search, SearchPort)
