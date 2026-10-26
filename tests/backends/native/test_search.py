import pytest

from ecosemantic.backends.native.search import NativeSearch
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.errors import Invalid, NotFound
from tests.fixture_data import FIXTURE_DB, FLOW_IDS


@pytest.fixture
def search(native_store: NativeStore) -> NativeSearch:
    return NativeSearch(native_store)


@pytest.mark.parametrize("query", ["", "  ", "* **", '""'])
async def test_a_query_with_no_term_is_invalid(search: NativeSearch, query: str) -> None:
    with pytest.raises(Invalid, match="a search needs at least one term"):
        await search.processes(FIXTURE_DB, query)


async def test_flows_filter_by_type_unit_and_sub_compartment(search: NativeSearch) -> None:
    resources = await search.elementary_flows(FIXTURE_DB, "water", flow_type="natural resource")
    assert {hit.ref.id for hit in resources.items} == {FLOW_IDS["water_in"]}
    assert (await search.elementary_flows(FIXTURE_DB, "water", flow_type="emission")).items == []
    urban = await search.elementary_flows(
        FIXTURE_DB, "particulate", sub_compartment="urban air close to ground", unit="kilogram"
    )
    assert {hit.ref.id for hit in urban.items} == {FLOW_IDS["pm"]}


async def test_a_search_names_a_database_the_store_serves(search: NativeSearch) -> None:
    with pytest.raises(NotFound, match="no database 'nowhere'"):
        await search.processes("nowhere", "steel")
