import pytest

from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.search import NativeSearch
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.ports.calculation import CalculationPort
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.search import SearchPort
from tests.conformance.calculation import CalculationConformance, MonteCarloConformance
from tests.conformance.inventory import InventoryConformance
from tests.conformance.search import SearchConformance


class TestNativeInventory(InventoryConformance):
    @pytest.fixture
    def inventory(self, native_store: NativeStore) -> NativeInventory:
        return NativeInventory(native_store)

    def test_satisfies_the_port(self, inventory: NativeInventory) -> None:
        assert isinstance(inventory, InventoryPort)


class TestNativeSearch(SearchConformance):
    @pytest.fixture
    def search(self, native_store: NativeStore) -> NativeSearch:
        return NativeSearch(native_store)

    def test_satisfies_the_port(self, search: NativeSearch) -> None:
        assert isinstance(search, SearchPort)


class TestNativeCalculation(CalculationConformance, MonteCarloConformance):
    @pytest.fixture
    def calculation(self, native_store: NativeStore) -> NativeCalculation:
        return NativeCalculation(native_store)

    def test_satisfies_the_port(self, calculation: NativeCalculation) -> None:
        assert isinstance(calculation, CalculationPort)
