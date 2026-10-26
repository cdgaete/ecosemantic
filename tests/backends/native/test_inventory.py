import dataclasses
from pathlib import Path

import pytest

from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.engine.background import Background
from ecosemantic.engine.calculation import Calculation
from ecosemantic.errors import NotFound
from ecosemantic.model.entities import DemandItem, Method
from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef
from ecosemantic.package.background import read_background
from tests.engine_fixture import fixture_bundle
from tests.fixture_data import CODES, FIXTURE_BIO, FIXTURE_DB, FLOW_IDS, LOOP_DB
from tests.openlca_fixture import FLOW_IDS as OPENLCA_FLOWS
from tests.openlca_fixture import PROCESSES as OPENLCA_PROCESSES
from tests.openlca_fixture import WIDGET_CLIMATE, build_package

STEEL = BackgroundRef(database=FIXTURE_DB, id=CODES["steel"])


@pytest.fixture
def inventory(native_store: NativeStore) -> NativeInventory:
    return NativeInventory(native_store)


async def test_a_process_read_without_exchanges_has_none(inventory: NativeInventory) -> None:
    steel = await inventory.get_process(STEEL)
    assert steel.exchanges is None
    assert (steel.reference_product, steel.location, steel.classifications) == ("steel", "GLO", [])


async def test_exchanges_come_in_the_dataset_order_with_their_side_and_reference(
    inventory: NativeInventory,
) -> None:
    steel = await inventory.get_process(STEEL, exchanges=True)
    assert steel.exchanges is not None
    assert [(e.side, e.reference, e.flow, e.supplier) for e in steel.exchanges] == [
        ("output", True, "steel", None),
        ("input", False, "electricity", "electricity production"),
        ("output", False, "Carbon dioxide, fossil", None),
        ("output", False, "Methane, fossil", None),
    ]


async def test_references_the_store_does_not_hold_are_not_found(
    inventory: NativeInventory,
) -> None:
    with pytest.raises(NotFound, match="no database 'nowhere'"):
        await inventory.get_process(BackgroundRef(database="nowhere", id=CODES["steel"]))
    with pytest.raises(NotFound, match="holds the elementary flows of 'fixture'"):
        await inventory.get_process(BackgroundRef(database=FIXTURE_BIO, id=CODES["steel"]))
    with pytest.raises(NotFound, match=f"no flow '{CODES['steel']}' in 'fixture-biosphere'"):
        await inventory.get_elementary_flow(
            ElementaryFlowRef(database=FIXTURE_BIO, id=CODES["steel"])
        )
    with pytest.raises(NotFound, match="uses the elementary flows 'fixture'"):
        await inventory.get_elementary_flow(ElementaryFlowRef(database=FIXTURE_DB, id="x"))


async def test_methods_filter_by_impact_method_and_resolve_by_specification(
    inventory: NativeInventory,
) -> None:
    water = await inventory.list_methods(FIXTURE_DB, impact_method="water")
    assert [m.spec for m in water] == ["fixture > water > water use > m3"]
    assert await inventory.list_methods(FIXTURE_DB, impact_method="nowhere") == []
    assert await inventory.resolve_method(FIXTURE_DB, water[0].spec) == water[0]


async def test_each_database_answers_from_its_own_catalog(inventory: NativeInventory) -> None:
    assert await inventory.list_units(LOOP_DB) == ["kilogram", "kilowatt hour", "megajoule"]
    co2 = await inventory.get_elementary_flow(
        ElementaryFlowRef(database="looped-biosphere", id=FLOW_IDS["co2"])
    )
    assert (co2.compartment, co2.sub_compartment, co2.flow_type) == ("air", None, "emission")


async def test_classifications_comments_and_links_travel_from_the_import(tmp_path: Path) -> None:
    bundle = fixture_bundle(tmp_path)
    imported = read_background(bundle, FIXTURE_DB, foreground=frozenset())
    key = ("fixture", CODES["steel"])
    steel = imported.datasets[key] | {
        "classifications": [("ISIC rev.4 ecoinvent", "2410:Manufacture of basic iron"), "steel"],
        "comment": "hot rolled",
        "url": "https://example.org/steel",
    }
    described = dataclasses.replace(imported, datasets=imported.datasets | {key: steel})
    install(tmp_path / "data", described, bundle, version="1", system_model="unit process")
    store = NativeStore(tmp_path / "data")
    read = await NativeInventory(store).get_process(STEEL)
    store.close()
    assert read.classifications == [
        "ISIC rev.4 ecoinvent: 2410:Manufacture of basic iron",
        "steel",
    ]
    assert (read.comment, read.url) == ("hot rolled", "https://example.org/steel")


OLCA = "fixture-olca"
STEEL_CODE = f"{OPENLCA_PROCESSES['steel']}_{OPENLCA_FLOWS['steel']}"
WIDGET_CODE = f"{OPENLCA_PROCESSES['widget']}_{OPENLCA_FLOWS['widget']}"
TREATMENT_CODE = f"{OPENLCA_PROCESSES['treatment']}_{OPENLCA_FLOWS['scrap']}"


def installed(directory: Path, bundle: Path) -> NativeStore:
    """The bundle installed, its unlinked input cut off as the setup commands hand it over."""
    imported = read_background(bundle, OLCA, foreground=frozenset())
    install(
        directory / "data",
        dataclasses.replace(imported, unlinked=[]),
        bundle,
        version="1",
        system_model="unit process",
        dropped=imported.unlinked,
    )
    return NativeStore(directory / "data")


def olca_installed(directory: Path, **flags: bool) -> tuple[Path, NativeStore]:
    """The openLCA fixture's package, built with these flags, installed in a directory."""
    bundle = build_package(directory / "package.zip", **flags)
    return bundle, installed(directory, bundle)


async def test_a_process_without_a_location_has_none(tmp_path: Path) -> None:
    bundle, store = olca_installed(tmp_path, no_location=True)
    imported = read_background(bundle, OLCA, foreground=frozenset())
    assert imported.datasets[(OLCA, STEEL_CODE)]["location"] is None
    rows = (
        store.catalog(OLCA)
        .execute("SELECT location FROM processes WHERE native_id = ?", [STEEL_CODE])
        .fetchall()
    )
    read = await NativeInventory(store).get_process(BackgroundRef(database=OLCA, id=STEEL_CODE))
    store.close()
    assert rows == [(None,)]
    assert read.location is None


async def test_list_locations_lists_the_codes_there_are(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path, no_location=True)
    locations = await NativeInventory(store).list_locations(OLCA)
    store.close()
    assert locations == ["GLO"]


async def test_a_category_is_carried_as_a_classification(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path)
    rows = (
        store.catalog(OLCA)
        .execute("SELECT classifications FROM processes WHERE native_id = ?", [WIDGET_CODE])
        .fetchall()
    )
    read = await NativeInventory(store).get_process(BackgroundRef(database=OLCA, id=WIDGET_CODE))
    store.close()
    assert rows == [(["Category: Manufacturing/assembly"],)]
    assert read.classifications == ["Category: Manufacturing/assembly"]


async def test_an_exchange_names_its_flow_and_its_supplier_apart(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path)
    read = await NativeInventory(store).get_process(
        BackgroundRef(database=OLCA, id=WIDGET_CODE), exchanges=True
    )
    store.close()
    assert read.exchanges is not None
    rows = {e.flow: e for e in read.exchanges}
    steel = rows["steel, low-alloyed"]
    assert (steel.supplier, steel.side, steel.reference) == ("steel production", "input", False)
    assert (steel.amount, steel.unit) == (0.5, "kilogram")
    assert rows["Carbon dioxide, fossil"].supplier is None


async def test_the_reference_output_is_listed_with_its_own_amount(tmp_path: Path) -> None:
    amount = 0.0012755102040816326
    bundle = build_package(tmp_path / "package.zip", widget_reference=amount)
    store = installed(tmp_path, bundle)
    read = await NativeInventory(store).get_process(
        BackgroundRef(database=OLCA, id=WIDGET_CODE), exchanges=True
    )
    store.close()
    assert read.exchanges is not None
    reference = read.exchanges[0]
    assert (reference.flow, reference.side, reference.reference) == ("widget", "output", True)
    assert reference.amount == pytest.approx(amount)
    assert reference.supplier is None and reference.cut_off is None
    assert reference.input is not None and reference.input.id == WIDGET_CODE


async def test_a_treated_waste_is_the_reference_row_of_its_dataset(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path)
    read = await NativeInventory(store).get_process(
        BackgroundRef(database=OLCA, id=TREATMENT_CODE), exchanges=True
    )
    store.close()
    assert read.exchanges is not None
    reference = read.exchanges[0]
    assert (reference.flow, reference.side, reference.reference) == ("steel scrap", "input", True)
    assert reference.amount == pytest.approx(1.0)


async def test_treatments_names_the_processes_whose_production_is_negative(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path)
    inventory = NativeInventory(store)
    treatment = BackgroundRef(database=OLCA, id=TREATMENT_CODE)
    widget = BackgroundRef(database=OLCA, id=WIDGET_CODE)
    steel = BackgroundRef(database=OLCA, id=STEEL_CODE)
    found = await inventory.treatments([widget, treatment, steel, treatment])
    with pytest.raises(NotFound, match="'nowhere'"):
        await inventory.treatments([BackgroundRef(database="nowhere", id=WIDGET_CODE)])
    store.close()
    assert found == [treatment, treatment]


async def test_a_cut_off_reaches_the_port_without_an_input(tmp_path: Path) -> None:
    _, store = olca_installed(tmp_path)
    read = await NativeInventory(store).get_process(
        BackgroundRef(database=OLCA, id=WIDGET_CODE), exchanges=True
    )
    store.close()
    assert read.exchanges is not None
    assert [(e.flow, e.side, e.cut_off) for e in read.exchanges] == [
        ("widget", "output", None),
        ("steel, low-alloyed", "input", None),
        ("fuel oil", "input", None),
        ("imported part", "input", "its provider is not in the package"),
        ("steel scrap", "output", None),
        ("Carbon dioxide, fossil", "output", None),
        ("Water, river", "input", None),
    ]
    cut_off = next(e for e in read.exchanges if e.cut_off is not None)
    assert (cut_off.amount, cut_off.unit) == (1.0, "kilogram")
    assert cut_off.input is None and cut_off.supplier is None and cut_off.reference is False


def score(directory: Path, key: tuple[str, ...]) -> float:
    """One widget's climate change score on the installed background."""
    calculation = Calculation(Background.load(directory / "background"))
    demand = [DemandItem(ref=BackgroundRef(database=OLCA, id=WIDGET_CODE), amount=1.0)]
    solution = calculation.solve(None, demand)
    return float(calculation.scores(solution, [Method.of(key, "kg CO2-Eq")]).values()[0])


def test_a_cut_off_is_never_scored(tmp_path: Path) -> None:
    bundle = build_package(tmp_path / "package.zip")
    imported = read_background(bundle, OLCA, foreground=frozenset())
    key = next(m.key for m in imported.methods if m.key[2] == "climate change")
    today = install(
        tmp_path / "today",
        dataclasses.replace(imported, unlinked=[]),
        bundle,
        version="1",
        system_model="unit process",
    ).directory
    dropped = install(
        tmp_path / "dropped",
        dataclasses.replace(imported, unlinked=[]),
        bundle,
        version="1",
        system_model="unit process",
        dropped=imported.unlinked,
    ).directory
    assert (
        Background.load(dropped / "background").fingerprint()
        == Background.load(today / "background").fingerprint()
    )
    assert score(dropped, key) == pytest.approx(score(today, key)) == pytest.approx(WIDGET_CLIMATE)
