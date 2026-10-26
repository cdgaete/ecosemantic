from __future__ import annotations

import pytest

from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.errors import NotFound
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.ports.resolver import FlowInfo, Resolver
from tests.conftest import CO2, COTTON
from tests.dict_resolver import DictResolver
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS


def test_dict_resolver_answers_known_references(resolver: DictResolver) -> None:
    assert resolver.background(COTTON).reference_product == "cotton fibre"
    assert resolver.flow(CO2).flow_type == "emission"


def test_dict_resolver_raises_on_unknown(resolver: DictResolver) -> None:
    with pytest.raises(NotFound):
        resolver.background(BackgroundRef(database="d", id="x"))
    with pytest.raises(NotFound):
        resolver.flow(ElementaryFlowRef(database="b", id="x"))


@pytest.fixture
def inventory_resolver(native_store: NativeStore) -> InventoryResolver:
    return InventoryResolver(NativeInventory(native_store))


def test_inventory_resolver_satisfies_the_protocol(inventory_resolver: InventoryResolver) -> None:
    assert isinstance(inventory_resolver, Resolver)


def test_inventory_resolver_names_a_background_process(
    inventory_resolver: InventoryResolver,
) -> None:
    info = inventory_resolver.background(BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]))
    assert info.name == "steel production" and info.reference_product == "steel"
    assert info.location == "GLO" and info.unit == "kilogram"


def test_inventory_resolver_carries_the_flow_type(
    inventory_resolver: InventoryResolver,
) -> None:
    water = inventory_resolver.flow(
        ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["water_in"])
    )
    # a bundle files a natural resource under openLCA's "Resource"
    assert water.name == "Water, river" and water.compartment == "Resource"
    assert water.sub_compartment == "in water" and water.unit == "cubic meter"
    assert water.flow_type == "natural resource"
    co2 = inventory_resolver.flow(ElementaryFlowRef(database=FIXTURE_BIO, id=FLOW_IDS["co2"]))
    assert co2.flow_type == "emission"


def test_inventory_resolver_raises_rather_than_inventing(
    inventory_resolver: InventoryResolver,
) -> None:
    with pytest.raises(NotFound):
        inventory_resolver.background(
            BackgroundRef(database=FIXTURE_DB, id=CODES["steel"][:-1] + "0")
        )
    with pytest.raises(NotFound):
        inventory_resolver.flow(ElementaryFlowRef(database=FIXTURE_BIO, id="nothing"))


def test_the_resolver_reuses_one_loop_and_rebuilds_it_after_close(
    inventory_resolver: InventoryResolver,
) -> None:
    ref = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])
    inventory_resolver.background(ref)
    loop = inventory_resolver._loop
    assert loop is not None
    inventory_resolver.background(ref)
    assert inventory_resolver._loop is loop
    inventory_resolver.close()
    assert inventory_resolver._loop is None
    assert inventory_resolver.background(ref).name == "steel production"
    assert inventory_resolver._loop is not None and inventory_resolver._loop is not loop


def test_flow_info_carries_its_side() -> None:
    info = FlowInfo(
        name="Secondary materials",
        compartment="inventory indicator",
        sub_compartment="resource use",
        unit="kilogram",
        flow_type="inventory indicator",
    )
    assert info.side == "input" and info.model_dump()["side"] == "input"
