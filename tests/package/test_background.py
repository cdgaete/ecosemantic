from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import olca_schema as o
import pytest
from olca_schema.zipio import ZipReader

from ecosemantic.errors import Invalid, NotSupported
from ecosemantic.model.entities import Uncertainty
from ecosemantic.package.background import Import, exchange_refusal, read_background
from ecosemantic.package.canonical import UNSTATED, UNSTATED_NAME
from tests.openlca_fixture import (
    FLOW_IDS,
    FLOWS,
    METHOD,
    MISSING_LOCATION,
    MISSING_PROVIDER,
    NAME,
    NORMALISATION,
    NORMALISATION_SET,
    PROCESSES,
    PUBLISHER_FLOW_IDS,
    WEIGHTS,
    WEIGHTS_SET,
    WEIGHTS_UNIT,
    build_package,
)


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_package(tmp_path_factory.mktemp("olca") / "fixture.zip")


def test_the_package_reads_back_with_olca_schema(package: Path) -> None:
    with ZipReader(str(package)) as reader:
        processes = list(reader.read_each(o.Process))
        flows = list(reader.read_each(o.Flow))
        methods = list(reader.read_each(o.ImpactMethod))
    assert {p.id for p in processes} == set(PROCESSES.values())
    assert {f.id for f in flows} == set(FLOW_IDS.values())
    assert len(methods) == 1 and len(methods[0].impact_categories or []) == 2


@pytest.fixture(scope="module")
def imported(package: Path) -> Import:
    return read_background(package, NAME, foreground=frozenset())


def _code(process: str, flow: str) -> str:
    return f"{PROCESSES[process]}_{FLOW_IDS[flow]}"


def _exchanges(imported: Import, process: str, flow: str) -> dict[object, dict[str, object]]:
    dataset = imported.datasets[(NAME, _code(process, flow))]
    return {e["input"]: e for e in dataset["exchanges"]}


def test_one_dataset_per_product_and_one_per_treated_waste(imported: Import) -> None:
    assert imported.database == NAME and imported.biosphere == f"{NAME}-biosphere"
    assert {code for _, code in imported.datasets} == {
        _code("elec", "electricity"),
        _code("steel", "steel"),
        _code("refinery", "fuel"),
        _code("refinery", "gas"),
        _code("widget", "widget"),
        _code("treatment", "scrap"),
    }
    steel = imported.datasets[(NAME, _code("steel", "steel"))]
    assert steel["name"] == "steel production"
    assert steel["reference product"] == "steel, low-alloyed"
    assert steel["unit"] == "kilogram" and steel["location"] == "GLO"
    assert steel["type"] == "process"


def test_amounts_arrive_in_canonical_units_with_scaled_uncertainty(imported: Import) -> None:
    steel = _exchanges(imported, "steel", "steel")
    elec = steel[(NAME, _code("elec", "electricity"))]
    assert elec["type"] == "technosphere" and elec["amount"] == pytest.approx(7.2)
    assert elec["unit"] == "megajoule"
    uncertainty = elec["uncertainty"]
    assert isinstance(uncertainty, Uncertainty) and uncertainty.type == "lognormal"
    assert "negative" not in uncertainty.params
    assert uncertainty.params["loc"] == pytest.approx(math.log(7.2))
    assert uncertainty.params["scale"] == pytest.approx(math.log(1.2))
    co2 = steel[(f"{NAME}-biosphere", FLOW_IDS["co2"])]
    assert co2["type"] == "biosphere" and co2["amount"] == pytest.approx(0.5)
    assert steel[(f"{NAME}-biosphere", FLOW_IDS["ch4"])]["amount"] == pytest.approx(0.01)
    assert steel[(NAME, _code("steel", "steel"))]["type"] == "production"


def test_allocation_scales_inputs_and_keeps_each_product_whole(imported: Import) -> None:
    fuel = _exchanges(imported, "refinery", "fuel")
    gas = _exchanges(imported, "refinery", "gas")
    assert fuel[(NAME, _code("elec", "electricity"))]["amount"] == pytest.approx(3.0)
    assert fuel[(f"{NAME}-biosphere", FLOW_IDS["co2"])]["amount"] == pytest.approx(1.5)
    assert fuel[(NAME, _code("refinery", "fuel"))]["amount"] == 1.0
    assert gas[(NAME, _code("elec", "electricity"))]["amount"] == pytest.approx(1.0)
    assert gas[(NAME, _code("refinery", "gas"))]["amount"] == 1.0
    assert (NAME, _code("refinery", "gas")) not in fuel


def test_causal_allocation_gives_each_product_its_share_of_each_exchange(tmp_path: Path) -> None:
    imported = read_background(
        build_package(tmp_path / "c.zip", causal=True, causal_factors=True),
        NAME,
        foreground=frozenset(),
    )
    fuel = _exchanges(imported, "refinery", "fuel")
    gas = _exchanges(imported, "refinery", "gas")
    # fuel takes 0.9 of the electricity and 0.5 of the carbon dioxide, gas takes 0.1 and 0.5
    assert fuel[(NAME, _code("elec", "electricity"))]["amount"] == pytest.approx(4.0 * 0.9)
    assert gas[(NAME, _code("elec", "electricity"))]["amount"] == pytest.approx(4.0 * 0.1)
    assert fuel[(f"{NAME}-biosphere", FLOW_IDS["co2"])]["amount"] == pytest.approx(2.0 * 0.5)
    assert gas[(f"{NAME}-biosphere", FLOW_IDS["co2"])]["amount"] == pytest.approx(2.0 * 0.5)
    assert fuel[(NAME, _code("refinery", "fuel"))]["amount"] == 1.0
    assert gas[(NAME, _code("refinery", "gas"))]["amount"] == 1.0
    assert (NAME, _code("refinery", "gas")) not in fuel


def test_a_causal_pair_without_a_factor_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match=rf"refinery production.*gas.*{FLOWS['co2'][0]}"):
        read_background(
            build_package(
                tmp_path / "m.zip",
                causal=True,
                causal_factors=True,
                omit_causal_factor=("gas", 4),
            ),
            NAME,
            foreground=frozenset(),
        )


def test_links_by_provider_by_flow_and_through_waste(imported: Import) -> None:
    widget = _exchanges(imported, "widget", "widget")
    assert widget[(NAME, _code("steel", "steel"))]["amount"] == 0.5
    assert widget[(NAME, _code("refinery", "fuel"))]["amount"] == 1.0
    assert widget[(NAME, _code("treatment", "scrap"))]["amount"] == pytest.approx(-0.1)
    assert widget[(f"{NAME}-biosphere", FLOW_IDS["water"])]["amount"] == pytest.approx(0.02)
    treatment = _exchanges(imported, "treatment", "scrap")
    assert treatment[(NAME, _code("treatment", "scrap"))]["amount"] == -1.0
    assert treatment[(NAME, _code("treatment", "scrap"))]["type"] == "production"


def test_the_missing_provider_is_the_one_unlinked_input(imported: Import) -> None:
    assert [(u.process, u.flow, u.provider_id) for u in imported.unlinked] == [
        ("widget production", "imported part", MISSING_PROVIDER)
    ]
    widget = _exchanges(imported, "widget", "widget")
    assert all(FLOW_IDS["part"] not in str(code) for _, code in widget)


def test_a_process_reads_its_category_then_its_tags_as_classifications(tmp_path: Path) -> None:
    package = build_package(
        tmp_path / "tagged.zip",
        categories={"elec": "Energy/carriers"},
        tags={
            "elec": ["CPC: 17100: Electrical energy"],
            "steel": ["By-product classification: allocatable product", "CPC: 4123"],
        },
    )
    imported = read_background(package, NAME, foreground=frozenset())
    elec = imported.datasets[(NAME, _code("elec", "electricity"))]
    assert elec["classifications"] == [
        ("Category", "Energy/carriers"),
        "CPC: 17100: Electrical energy",
    ]
    steel = imported.datasets[(NAME, _code("steel", "steel"))]
    assert steel["classifications"] == [
        "By-product classification: allocatable product",
        "CPC: 4123",
    ]
    widget = imported.datasets[(NAME, _code("widget", "widget"))]
    assert widget["classifications"] == [("Category", "Manufacturing/assembly")]
    treatment = imported.datasets[(NAME, _code("treatment", "scrap"))]
    assert treatment["classifications"] == []


def test_elementary_flows_carry_compartment_type_and_cas(imported: Import) -> None:
    co2 = imported.flows[(f"{NAME}-biosphere", FLOW_IDS["co2"])]
    assert (co2["compartment"], co2["sub_compartment"], co2["type"]) == (
        "air",
        "unspecified",
        "emission",
    )
    assert "categories" not in co2
    assert co2["unit"] == "kilogram" and co2["CAS number"] == "124-38-9"
    water = imported.flows[(f"{NAME}-biosphere", FLOW_IDS["water"])]
    assert (water["compartment"], water["sub_compartment"]) == ("natural resource", "in water")
    assert water["type"] == "natural resource" and water["unit"] == "cubic meter"


def _placed(imported: Import, flow_id: str) -> tuple[object, object, object]:
    flow = imported.flows[(f"{NAME}-biosphere", flow_id)]
    return (flow["compartment"], flow["sub_compartment"], flow["type"])


def test_a_flow_of_each_publisher_vocabulary_is_placed(tmp_path: Path) -> None:
    imported = read_background(
        build_package(tmp_path / "publishers.zip", publisher_flows=True),
        NAME,
        foreground=frozenset(),
    )
    assert _placed(imported, PUBLISHER_FLOW_IDS["nox"]) == ("air", "unspecified", "emission")
    assert _placed(imported, PUBLISHER_FLOW_IDS["dust"]) == (
        "air",
        "troposphere, rural",
        "emission",
    )
    assert _placed(imported, PUBLISHER_FLOW_IDS["ore"]) == (
        "natural resource",
        "ground",
        "natural resource",
    )
    assert _placed(imported, PUBLISHER_FLOW_IDS["wages"]) == (
        "economic",
        "unspecified",
        "economic",
    )
    assert _placed(imported, FLOW_IDS["co2"]) == ("air", "unspecified", "emission")
    assert _placed(imported, FLOW_IDS["water"]) == (
        "natural resource",
        "in water",
        "natural resource",
    )


def test_cas_numbers_are_read_canonical(tmp_path: Path) -> None:
    imported = read_background(
        build_package(
            tmp_path / "cas.zip",
            extra_flows={"digit": ("Wages", "Elementary flows/Economic/unspecified")},
            cas={
                "co2": "000124-38-9",
                "water": "7732-18-5",
                "ch4": "n.a.",
                "digit": "7732190",
            },
        ),
        NAME,
        foreground=frozenset(),
    )
    flows = {flow["name"]: flow for flow in imported.flows.values()}
    answers = {name: (flow["CAS number"], flow["CAS as published"]) for name, flow in flows.items()}
    assert answers == {
        "Carbon dioxide, fossil": ("124-38-9", None),
        "Methane, fossil": (None, "n.a."),
        "Water, river": ("7732-18-5", None),
        "Wages": (None, "7732190"),
    }
    assert imported.cas_set_aside == 2


def test_an_unknown_compartment_refuses_the_import_naming_it_and_its_count(
    tmp_path: Path,
) -> None:
    package = build_package(
        tmp_path / "social.zip",
        extra_flows={
            "land": ("Land use, social", "Elementary flows/Social issues/unspecified"),
            "noise": ("Noise, social", "Elementary flows/Social issues/unspecified"),
        },
    )
    with pytest.raises(Invalid) as raised:
        read_background(package, NAME, foreground=frozenset())
    assert "compartment 'Social issues/unspecified' (2 rows)" in str(raised.value)


def test_two_paths_placed_together_refuse_the_import(tmp_path: Path) -> None:
    package = build_package(
        tmp_path / "smoke.zip",
        extra_flows={
            "smoke_emission": ("Smoke", "Elementary flows/emission/air/troposphere/rural"),
            "smoke_air": ("Smoke", "Elementary flows/air/troposphere, rural"),
        },
    )
    with pytest.raises(Invalid) as raised:
        read_background(package, NAME, foreground=frozenset())
    assert "flows named 'Smoke' placed together" in str(raised.value)


def test_an_indicator_flow_whose_sub_compartment_names_no_side_refuses_the_import(
    tmp_path: Path,
) -> None:
    package = build_package(
        tmp_path / "indicator.zip",
        extra_flows={"jobs": ("Jobs", "Elementary flows/inventory indicator/unspecified")},
    )
    with pytest.raises(Invalid) as raised:
        read_background(package, NAME, foreground=frozenset())
    assert "inventory indicator flow in inventory indicator/unspecified names no side" in str(
        raised.value
    )


def test_an_elementary_flow_takes_its_type_from_its_top_category(tmp_path: Path) -> None:
    source = build_package(tmp_path / "fixture.zip")
    recategorised = tmp_path / "recategorised.zip"
    categories = {
        FLOW_IDS["co2"]: "Elementary flows/inventory indicator/waste",
        FLOW_IDS["ch4"]: "Elementary flows/economic/primary production factor",
        FLOW_IDS["water"]: "Elementary flows/natural resource/in water",
    }
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(recategorised, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            flow_id = name.removeprefix("flows/").removesuffix(".json")
            if name.startswith("flows/") and flow_id in categories:
                flow = json.loads(data)
                flow["category"] = categories[flow_id]
                data = json.dumps(flow).encode()
            dst.writestr(name, data)
    flows = read_background(recategorised, NAME, foreground=frozenset()).flows
    types = {
        key: flows[(f"{NAME}-biosphere", FLOW_IDS[key])]["type"] for key in ("co2", "ch4", "water")
    }
    assert types == {
        "co2": "inventory indicator",
        "ch4": "economic",
        "water": "natural resource",
    }


def test_methods_carry_factors_in_canonical_units(imported: Import) -> None:
    by_key = {m.key: m for m in imported.methods}
    climate = by_key[(NAME, METHOD, "climate change", "climate change")]
    assert climate.unit == "kg CO2-Eq"
    assert dict(climate.factors) == {
        (f"{NAME}-biosphere", FLOW_IDS["co2"]): pytest.approx(1.0),
        (f"{NAME}-biosphere", FLOW_IDS["ch4"]): pytest.approx(28.0),
    }
    assert dict(by_key[(NAME, METHOD, "water use", "water use")].factors) == {
        (f"{NAME}-biosphere", FLOW_IDS["water"]): pytest.approx(1.0)
    }


def test_an_openlca_category_is_both_category_and_indicator(imported: Import) -> None:
    keys = {m.key for m in imported.methods}
    assert keys == {
        (NAME, METHOD, "climate change", "climate change"),
        (NAME, METHOD, "water use", "water use"),
    }
    assert imported.weightings == []


def _category_keys() -> list[tuple[str, str, str, str]]:
    """The method key of each category the fixture's method lists, in its order."""
    return [
        (NAME, METHOD, "climate change", "climate change"),
        (NAME, METHOD, "water use", "water use"),
    ]


def test_a_family_reads_its_weighting_sets_as_the_bundle_states_them(tmp_path: Path) -> None:
    imported = read_background(
        build_package(tmp_path / "p.zip", weighting_sets=True), NAME, foreground=frozenset()
    )
    weighted, normalised, unnamed = imported.weightings
    assert (weighted.family, weighted.name, weighted.unit) == (METHOD, WEIGHTS_SET, WEIGHTS_UNIT)
    assert weighted.factors == [(key, None, WEIGHTS[key[2]]) for key in _category_keys()]
    assert (normalised.family, normalised.name, normalised.unit) == (
        METHOD,
        NORMALISATION_SET,
        None,
    )
    assert normalised.factors == [(key, NORMALISATION[key[2]], None) for key in _category_keys()]
    assert (unnamed.family, unnamed.name, unnamed.unit, unnamed.factors) == (METHOD, None, None, [])


def test_a_factor_naming_a_foreign_category_refuses_the_import(tmp_path: Path) -> None:
    package = build_package(tmp_path / "p.zip", weighting_sets=True, bad_weighting=True)
    with pytest.raises(Invalid) as refused:
        read_background(package, NAME, foreground=frozenset())
    assert str(refused.value) == (
        f"{NAME} does not fit the canonical shape: weighting set {WEIGHTS_SET!r} of "
        f"{METHOD!r} names a category the family lacks (1 rows)"
    )


def test_a_factor_naming_a_location_is_set_apart(tmp_path: Path) -> None:
    imported = read_background(
        build_package(tmp_path / "p.zip", regional=True), NAME, foreground=frozenset()
    )
    climate = {m.key: m for m in imported.methods}[
        (NAME, METHOD, "climate change", "climate change")
    ]
    assert dict(climate.factors) == {
        (f"{NAME}-biosphere", FLOW_IDS["co2"]): pytest.approx(1.0),
        (f"{NAME}-biosphere", FLOW_IDS["ch4"]): pytest.approx(28.0),
    }
    assert climate.set_apart == 1
    assert {m.key: m for m in imported.methods}[
        (NAME, METHOD, "water use", "water use")
    ].set_apart == 0


def test_a_method_without_a_family_refuses_the_import(tmp_path: Path) -> None:
    package = build_package(tmp_path / "nameless.zip", nameless_method=True)
    with pytest.raises(Invalid) as refused:
        read_background(package, NAME, foreground=frozenset())
    message = str(refused.value)
    assert "does not fit the canonical shape" in message
    assert "method without a family" in message
    assert "(1 rows)" in message


def test_a_flow_characterised_only_at_locations_is_not_supported(tmp_path: Path) -> None:
    package = build_package(tmp_path / "p.zip", regional_only=True)
    refusal = r"climate change.*only with factors that name a location"
    with pytest.raises(NotSupported, match=refusal):
        read_background(package, NAME, foreground=frozenset())


def test_refusals_name_what_was_met(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match="refinery"):
        read_background(
            build_package(tmp_path / "causal.zip", causal=True), NAME, foreground=frozenset()
        )
    with pytest.raises(NotSupported, match="furlong"):
        read_background(
            build_package(tmp_path / "odd.zip", odd_unit=True), NAME, foreground=frozenset()
        )
    with pytest.raises(NotSupported, match="Volume"):
        read_background(
            build_package(tmp_path / "prop.zip", other_property=True), NAME, foreground=frozenset()
        )


def test_exchange_refusal_names_only_a_stray_waste_input() -> None:
    waste = o.Flow(flow_type=o.FlowType.WASTE_FLOW)
    reason = "a waste input that is not its process's reference"
    assert (
        exchange_refusal(o.Exchange(is_input=True, is_quantitative_reference=True), waste) is None
    )
    assert exchange_refusal(o.Exchange(is_input=False), waste) is None
    assert (
        exchange_refusal(o.Exchange(is_input=True), o.Flow(flow_type=o.FlowType.PRODUCT_FLOW))
        is None
    )
    assert (
        exchange_refusal(o.Exchange(is_input=True), o.Flow(flow_type=o.FlowType.ELEMENTARY_FLOW))
        is None
    )
    assert exchange_refusal(o.Exchange(is_input=True), waste) == reason


def test_a_waste_input_that_is_not_the_reference_is_not_supported(tmp_path: Path) -> None:
    with pytest.raises(NotSupported, match=rf"widget production.*{FLOWS['scrap'][0]}"):
        read_background(
            build_package(tmp_path / "w.zip", stray_waste_input=True),
            NAME,
            foreground=frozenset(),
        )


def test_a_distribution_the_core_cannot_hold_names_the_process_and_the_flow(
    tmp_path: Path,
) -> None:
    with pytest.raises(Invalid, match=rf"steel production.*{FLOWS['co2'][0]}"):
        read_background(
            build_package(tmp_path / "u.zip", degenerate_uniform=True),
            NAME,
            foreground=frozenset(),
        )


def test_an_allocation_the_importer_does_not_take_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(Invalid, match=r"refinery production.*not physical, economic or causal"):
        read_background(
            build_package(tmp_path / "n.zip", no_allocation=True), NAME, foreground=frozenset()
        )


def test_a_flow_in_standard_volume_refuses_an_exchange_in_normal_volume(tmp_path: Path) -> None:
    source = build_package(tmp_path / "fixture.zip")
    crossed = tmp_path / "crossed.zip"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(crossed, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name.startswith("unit_groups/"):
                group = json.loads(data)
                if group["name"] == "Units of volume":
                    reference = next(u for u in group["units"] if u.get("isRefUnit"))
                    reference["name"] = "Sm3"
                    data = json.dumps(group).encode()
            if name == f"processes/{PROCESSES['widget']}.json":
                process = json.loads(data)
                water = next(
                    e for e in process["exchanges"] if e["flow"]["@id"] == FLOW_IDS["water"]
                )
                water["unit"] = {"@type": "Unit", "@id": "u-nm3", "name": "Nm3"}
                data = json.dumps(process).encode()
            dst.writestr(name, data)
    with pytest.raises(Invalid, match="unit of another quantity"):
        read_background(crossed, NAME, foreground=frozenset())


def test_foreground_processes_install_nothing(package: Path) -> None:
    imported = read_background(package, NAME, foreground=frozenset({PROCESSES["widget"]}))
    assert (NAME, _code("widget", "widget")) not in imported.datasets
    assert imported.processes == 4


def test_a_product_is_stored_in_the_unit_its_producer_declares(tmp_path: Path) -> None:
    imported = read_background(
        build_package(tmp_path / "kwh.zip", elec_in_kwh=True), NAME, foreground=frozenset()
    )
    elec = imported.datasets[(NAME, _code("elec", "electricity"))]
    assert elec["unit"] == "kilowatt hour"
    steel = _exchanges(imported, "steel", "steel")[(NAME, _code("elec", "electricity"))]
    # steel takes 2 kWh, the producer's own unit: nothing converts
    assert (steel["amount"], steel["unit"]) == (pytest.approx(2.0), "kilowatt hour")


def test_producers_declaring_different_units_store_the_canonical_one(tmp_path: Path) -> None:
    source = build_package(tmp_path / "kwh.zip", elec_in_kwh=True)
    twice = tmp_path / "twice.zip"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(twice, "w") as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
        other = json.loads(src.read(f"processes/{PROCESSES['elec']}.json"))
        other["@id"], other["name"] = "0e1e0000-0000-4000-8000-000000000001", "other elec"
        reference = next(e for e in other["exchanges"] if e.get("isQuantitativeReference"))
        reference["unit"] = {"@type": "Unit", "@id": "u-mj", "name": "MJ"}
        dst.writestr(f"processes/{other['@id']}.json", json.dumps(other))
    imported = read_background(twice, NAME, foreground=frozenset())
    assert imported.datasets[(NAME, _code("elec", "electricity"))]["unit"] == "megajoule"


def test_a_publication_naming_a_source_the_package_lacks_is_invalid(tmp_path: Path) -> None:
    source = build_package(tmp_path / "fixture.zip")
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(broken, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == f"processes/{PROCESSES['steel']}.json":
                process = json.loads(data)
                process["processDocumentation"] = {
                    "publication": {
                        "@type": "Source",
                        "@id": "0e1e0000-0000-4000-8000-00000000000f",
                    }
                }
                data = json.dumps(process).encode()
            dst.writestr(name, data)
    with pytest.raises(Invalid, match="0e1e0000-0000-4000-8000-00000000000f"):
        read_background(broken, NAME, foreground=frozenset())


def test_a_process_naming_a_location_the_package_lacks_is_invalid(tmp_path: Path) -> None:
    package = build_package(tmp_path / "package.zip", unknown_location=True)
    with pytest.raises(Invalid) as caught:
        read_background(package, NAME, foreground=frozenset())
    assert "steel production" in str(caught.value)
    assert MISSING_LOCATION in str(caught.value)


def test_a_process_without_a_location_is_located_unstated(tmp_path: Path) -> None:
    package = build_package(tmp_path / "package.zip", no_location=True)
    imported = read_background(package, NAME, foreground=frozenset())
    assert {str(dataset["location"]) for dataset in imported.datasets.values()} == {UNSTATED}
    assert imported.locations == {UNSTATED: UNSTATED_NAME}


def test_the_import_holds_the_locations_the_processes_name_only(tmp_path: Path) -> None:
    package = build_package(tmp_path / "package.zip", regional=True)
    imported = read_background(package, NAME, foreground=frozenset())
    assert imported.locations == {"GLO": "Global"}


def test_a_code_two_used_locations_share_refuses_the_import(tmp_path: Path) -> None:
    package = build_package(tmp_path / "package.zip", shared_code_used=True)
    with pytest.raises(Invalid) as caught:
        read_background(package, NAME, foreground=frozenset())
    assert "location code 'NA' named 'Namibia' and 'Northern Appalachia' (2 rows)" in str(
        caught.value
    )


def test_two_locations_of_one_code_no_process_names_install(tmp_path: Path) -> None:
    package = build_package(tmp_path / "package.zip", shared_code=True)
    imported = read_background(package, NAME, foreground=frozenset())
    assert imported.locations == {"GLO": "Global"}


def test_a_package_out_of_shape_is_refused_or_brought_into_it(tmp_path: Path) -> None:
    social = {"social": ("Social cost of carbon", "Elementary flows/Social issues/unspecified")}
    refused = build_package(
        tmp_path / "refused.zip",
        extra_flows=social,
        unmapped_category=True,
        no_location=True,
        cas={"co2": "000124-38-9", "ch4": "n.a."},
    )
    with pytest.raises(Invalid) as caught:
        read_background(refused, NAME, foreground=frozenset())
    assert str(caught.value) == (
        f"{NAME} does not fit the canonical shape: compartment 'Social issues/unspecified' (1 rows)"
    )
    installed = build_package(
        tmp_path / "installed.zip",
        unmapped_category=True,
        no_location=True,
        cas={"co2": "000124-38-9", "ch4": "n.a."},
    )
    imported = read_background(installed, NAME, foreground=frozenset())
    assert (NAME, METHOD, "land use", "land use") in {m.key for m in imported.methods}
    flows = {code: flow for (_, code), flow in imported.flows.items()}
    assert flows[FLOW_IDS["co2"]]["CAS number"] == "124-38-9"
    assert flows[FLOW_IDS["ch4"]]["CAS number"] is None
    assert flows[FLOW_IDS["ch4"]]["CAS as published"] == "n.a."
    assert {str(dataset["location"]) for dataset in imported.datasets.values()} == {UNSTATED}
