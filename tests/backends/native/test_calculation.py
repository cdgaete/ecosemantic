import pytest

from ecosemantic.backends.native.calculation import Named, NativeCalculation
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.errors import Invalid, NotFound, OtherBuild
from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import BackgroundRef, ForegroundRef, LinkedProcessRef
from ecosemantic.ports.types import System
from tests.conftest import fixture_system, split_system
from tests.engine_fixture import LOOP_DB, LOOP_FINGERPRINT
from tests.fixture_data import CODES, FIXTURE_DB, FIXTURE_FINGERPRINT

GWP = Method.of(("fixture", "gwp", "climate change > GWP100"), "kg CO2-Eq")
WIDGET = [DemandItem(ref=ForegroundRef(code="widget"), amount=1.0)]
PAPER = [DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["paper"]), amount=1.0)]


@pytest.fixture
def calculation(native_store: NativeStore) -> NativeCalculation:
    return NativeCalculation(native_store)


async def test_a_contribution_tree_takes_one_foreground_item_on_a_product_system(
    calculation: NativeCalculation,
) -> None:
    with pytest.raises(Invalid, match="takes exactly one foreground demand item"):
        await calculation.contribution_tree(fixture_system(), PAPER, GWP)
    with pytest.raises(Invalid, match="takes exactly one foreground demand item"):
        await calculation.contribution_tree(fixture_system(), WIDGET + WIDGET, GWP)
    with pytest.raises(Invalid, match="a contribution tree needs a product_system"):
        await calculation.contribution_tree(System(database=FIXTURE_DB), WIDGET, GWP)


async def test_a_method_or_a_database_the_store_lacks_is_not_found(
    calculation: NativeCalculation,
) -> None:
    noise = Method.of(("fixture", "noise", "decibel"), "dB")
    with pytest.raises(NotFound, match=r"lacks methods \['fixture > noise > decibel'\]"):
        await calculation.score(fixture_system(), WIDGET, noise)
    with pytest.raises(NotFound, match="no database 'nowhere'"):
        await calculation.score(System(database="nowhere"), PAPER, GWP)


def on_build(system: System, fingerprint: str | None) -> System:
    assert system.product_system is not None
    database = system.product_system.database.model_copy(update={"fingerprint": fingerprint})
    return system.model_copy(
        update={"product_system": system.product_system.model_copy(update={"database": database})}
    )


async def test_a_system_on_another_build_or_on_none_is_refused_naming_both(
    calculation: NativeCalculation, native_store: NativeStore
) -> None:
    assert native_store.registered(FIXTURE_DB).database.fingerprint == FIXTURE_FINGERPRINT
    assert native_store.registered(LOOP_DB).database.fingerprint == LOOP_FINGERPRINT
    held = FIXTURE_FINGERPRINT[:12]
    with pytest.raises(
        OtherBuild, match=f"names build 000000000000 of 'fixture'; this store holds build {held}"
    ) as raised:
        await calculation.score(on_build(fixture_system(), "0" * 64), WIDGET, GWP)
    assert (raised.value.named, raised.value.installed) == ("0" * 64, FIXTURE_FINGERPRINT)
    with pytest.raises(OtherBuild, match="names no build of 'fixture'"):
        await calculation.inventory(on_build(fixture_system(), None), WIDGET)
    # a demand on the database alone names no build to hold against it
    assert (await calculation.score(System(database=FIXTURE_DB), PAPER, GWP)).value > 0


async def test_a_linked_system_on_another_build_is_refused(
    calculation: NativeCalculation,
) -> None:
    system = split_system()
    linked = {
        key: frame.model_copy(
            update={"database": frame.database.model_copy(update={"fingerprint": "0" * 64})}
        )
        for key, frame in system.linked.items()
    }
    with pytest.raises(OtherBuild, match="'frame' names build 000000000000"):
        await calculation.supply(system.model_copy(update={"linked": linked}), WIDGET)


async def test_a_background_demand_has_no_supply_and_no_foreground_source(
    calculation: NativeCalculation,
) -> None:
    background = System(database=FIXTURE_DB)
    assert await calculation.supply(background, PAPER) == []
    found = await calculation.inventory(background, PAPER)
    assert found.rows and all(row.source is None for row in found.rows)
    assert found.dropped == 0 and found.floor > 0.0


async def test_a_linked_system_names_its_processes_by_system_and_pin(
    calculation: NativeCalculation,
) -> None:
    system = split_system()
    supplied = await calculation.supply(system, WIDGET)
    linked = [a.ref for a in supplied if isinstance(a.ref, LinkedProcessRef)]
    assert [ref.code for ref in linked] == ["frame"]
    assert linked[0].product_system_id in system.linked
    tree = await calculation.contribution_tree(system, WIDGET, GWP, cutoff=0.0)
    frame = next(child for child in tree.root.children if child.ref == linked[0])
    assert (frame.name, frame.location) == ("frame production", "GLO")


async def test_a_flow_the_background_item_of_a_demand_emits_most_has_no_source(
    calculation: NativeCalculation,
) -> None:
    steel = DemandItem(ref=BackgroundRef(database=FIXTURE_DB, id=CODES["steel"]), amount=9.0)
    found = await calculation.inventory(fixture_system(), [*WIDGET, steel])
    rows = {row.name: row for row in found.rows}
    assert rows["Methane, fossil"].source is None


async def test_top_n_keeps_the_largest_and_the_total_stays_whole(
    calculation: NativeCalculation,
) -> None:
    hotspots = await calculation.hotspots(fixture_system(), WIDGET, GWP, top_n=2)
    assert [h.rank for h in hotspots.items] == [1, 2]
    assert hotspots.total.value == pytest.approx(4.158)
    assert abs(hotspots.items[0].score) >= abs(hotspots.items[1].score)


def test_a_label_names_no_missing_location() -> None:
    assert Named("steel production", None, "steel").label() == "steel production"
    assert Named("steel production", "GLO", "steel").label() == "steel production [GLO]"
