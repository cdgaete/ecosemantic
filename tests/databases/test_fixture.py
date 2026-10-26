"""The synthetic release parses, and each override changes the one thing it names."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from python_calamine import CalamineWorkbook

from tests.databases.spold_fixture import (
    AIR,
    AIR_ACTIVITY,
    AIR_PRODUCT,
    CO2,
    ECOQUERY_INDEX,
    ELEC,
    ELEC_ACTIVITY,
    ELEC_PRODUCT,
    IRON,
    NS,
    STEEL,
    STEEL_ACTIVITY,
    STEEL_PRODUCT,
    TREAT,
    TREAT_ACTIVITY,
    TREAT_PRODUCT,
    UNUSED,
    build_release,
)


def _dataset(root: Path, native: str) -> ET.Element:
    return ET.parse(root / "ecospold" / "datasets" / f"{native}.spold").getroot()


def _exchanges(root: Path, native: str, tag: str) -> list[ET.Element]:
    found = _dataset(root, native).findall(
        f"{{{NS}}}childActivityDataset/{{{NS}}}flowData/{{{NS}}}{tag}"
    )
    return found


def _reference(root: Path, native: str) -> ET.Element:
    return next(
        exchange
        for exchange in _exchanges(root, native, "intermediateExchange")
        if exchange.findtext(f"{{{NS}}}outputGroup") == "0"
    )


def _sheet(path: Path, name: str) -> list[list[object]]:
    return CalamineWorkbook.from_path(str(path)).get_sheet_by_name(name).to_python()


def test_build_release_writes_the_five_files_a_ecoinvent_release_carries(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    assert release.version == "3.10"
    assert release.system_model == "cutoff"
    assert release.ecospold.is_dir()
    assert release.matrix.is_dir()
    assert release.lcia.is_file()
    assert release.cumulative_lcia.is_file()
    assert release.overview.is_file()
    assert sorted(p.name for p in (release.ecospold / "datasets").glob("*.spold")) == sorted(
        [f"{STEEL}.spold", f"{ELEC}.spold", f"{TREAT}.spold", f"{AIR}.spold"]
    )
    assert (release.ecospold / "MasterData" / "ElementaryExchanges.xml").is_file()
    assert (release.ecospold / "MasterData" / "IntermediateExchanges.xml").is_file()


def test_every_dataset_parses_in_the_ecospold_namespace(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    for path in sorted((release.ecospold / "datasets").glob("*.spold")):
        root = ET.parse(path).getroot()
        assert root.tag == f"{{{NS}}}ecoSpold"
        assert root.find(f"{{{NS}}}childActivityDataset/{{{NS}}}flowData") is not None


def test_steel_declares_the_geography_the_release_gives_it(tmp_path: Path) -> None:
    build_release(tmp_path)
    shortname = _dataset(tmp_path, STEEL).find(
        f"{{{NS}}}childActivityDataset/{{{NS}}}activityDescription/{{{NS}}}geography/{{{NS}}}shortname"
    )
    assert shortname is not None
    assert shortname.text == "NA"


def test_the_elementary_masterdata_holds_every_flow_it_declares(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    root = ET.parse(release.ecospold / "MasterData" / "ElementaryExchanges.xml").getroot()
    assert {e.get("id") for e in root.findall(f"{{{NS}}}elementaryExchange")} == {
        CO2,
        IRON,
        UNUSED,
    }
    carbon = next(e for e in root.findall(f"{{{NS}}}elementaryExchange") if e.get("id") == CO2)
    compartment = carbon.find(f"{{{NS}}}compartment")
    assert compartment is not None
    assert compartment.findtext(f"{{{NS}}}compartment") == "air"
    assert compartment.findtext(f"{{{NS}}}subcompartment") == "unspecified"
    iron = next(e for e in root.findall(f"{{{NS}}}elementaryExchange") if e.get("id") == IRON)
    resource = iron.find(f"{{{NS}}}compartment")
    assert resource is not None
    assert resource.findtext(f"{{{NS}}}compartment") == "natural resource"
    assert resource.findtext(f"{{{NS}}}subcompartment") == "in ground"


def test_the_intermediate_masterdata_holds_the_four_products(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    root = ET.parse(release.ecospold / "MasterData" / "IntermediateExchanges.xml").getroot()
    assert {e.get("id") for e in root.findall(f"{{{NS}}}intermediateExchange")} == {
        STEEL_PRODUCT,
        ELEC_PRODUCT,
        TREAT_PRODUCT,
        AIR_PRODUCT,
    }


def test_steel_links_its_electricity_input_to_the_electricity_dataset(tmp_path: Path) -> None:
    build_release(tmp_path)
    electricity = next(
        exchange
        for exchange in _exchanges(tmp_path, STEEL, "intermediateExchange")
        if exchange.get("intermediateExchangeId") == ELEC_PRODUCT
    )
    assert electricity.get("activityLinkId") == ELEC_ACTIVITY
    assert electricity.get("amount") == "2.0"
    assert electricity.findtext(f"{{{NS}}}inputGroup") == "5"
    lognormal = electricity.find(f"{{{NS}}}uncertainty/{{{NS}}}lognormal")
    assert lognormal is not None
    assert lognormal.get("variance") == "0.04"
    assert lognormal.get("varianceWithPedigreeUncertainty") == "0.04"


def test_steel_emits_carbon_dioxide_and_takes_iron(tmp_path: Path) -> None:
    build_release(tmp_path)
    carbon = next(
        exchange
        for exchange in _exchanges(tmp_path, STEEL, "elementaryExchange")
        if exchange.get("elementaryExchangeId") == CO2
    )
    assert carbon.get("amount") == "1.5"
    assert carbon.findtext(f"{{{NS}}}outputGroup") == "4"
    iron = next(
        exchange
        for exchange in _exchanges(tmp_path, STEEL, "elementaryExchange")
        if exchange.get("elementaryExchangeId") == IRON
    )
    assert iron.get("amount") == "0.5"
    assert iron.findtext(f"{{{NS}}}inputGroup") == "4"


def test_steel_hands_waste_to_the_treatment_dataset(tmp_path: Path) -> None:
    build_release(tmp_path)
    waste = next(
        exchange
        for exchange in _exchanges(tmp_path, STEEL, "intermediateExchange")
        if exchange.get("activityLinkId") == TREAT_ACTIVITY
    )
    assert waste.get("amount") == "-0.2"
    assert waste.findtext(f"{{{NS}}}inputGroup") == "5"


def test_the_treatment_dataset_references_minus_one_of_its_waste(tmp_path: Path) -> None:
    build_release(tmp_path)
    assert _reference(tmp_path, TREAT).get("amount") == "-1.0"


def test_the_compressed_air_dataset_consumes_part_of_its_own_product(tmp_path: Path) -> None:
    build_release(tmp_path)
    assert _reference(tmp_path, AIR).get("amount") == "1.0"
    self_input = next(
        exchange
        for exchange in _exchanges(tmp_path, AIR, "intermediateExchange")
        if exchange.get("activityLinkId") == AIR_ACTIVITY
        and exchange.get("intermediateExchangeId") == AIR_PRODUCT
    )
    assert self_input.get("amount") == "0.1"
    assert self_input.findtext(f"{{{NS}}}inputGroup") == "5"


def test_the_lcia_workbook_has_the_two_sheets_the_release_names(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    workbook = CalamineWorkbook.from_path(str(release.lcia))
    assert workbook.sheet_names == ["CFs", "Indicators"]
    factors = _sheet(release.lcia, "CFs")
    assert factors[0] == [
        "Method",
        "Category",
        "Indicator",
        "Name",
        "Compartment",
        "Subcompartment",
        "CF",
    ]
    assert factors[1] == [
        "IPCC 2021",
        "climate change",
        "GWP100",
        "Carbon dioxide, fossil",
        "air",
        "unspecified",
        1.0,
    ]
    indicators = _sheet(release.lcia, "Indicators")
    assert indicators[0] == ["Method", "Category", "Indicator", "Indicator Unit"]
    assert indicators[1] == ["IPCC 2021", "climate change", "GWP100", "kg CO2-Eq"]


def test_the_overview_carries_a_row_and_an_ecoquery_url_per_dataset(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    rows = _sheet(release.overview, "Cut-Off AO")
    assert rows[0] == [
        "Activity UUID & Product UUID",
        "Activity UUID",
        "ecoQuery URL",
        "Activity Name",
        "Geography",
    ]
    by_native = {row[0]: row for row in rows[1:]}
    assert set(by_native) == {STEEL, ELEC, TREAT, AIR}
    for native in (STEEL, ELEC, TREAT, AIR):
        assert (
            by_native[native][2]
            == f"https://ecoquery.ecoinvent.org/3.10/cutoff/dataset/{ECOQUERY_INDEX[native]}/documentation"
        )
    assert by_native[STEEL][1] == STEEL_ACTIVITY
    assert by_native[STEEL][4] == "NA"


def test_the_matrix_export_carries_the_fixtures_own_numbers(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    assert sorted(path.name for path in release.matrix.iterdir()) == [
        "A_public.csv",
        "B_public.csv",
        "C.csv",
        "LCIA_index.csv",
        "ee_index.csv",
        "ie_index.csv",
    ]
    assert (release.matrix / "A_public.csv").read_text().splitlines()[0] == (
        "row;column;coefficient;uncertainty type;varianceWithPedigreeUncertainty;"
        "minValue;mostLikelyValue;maxValue"
    )
    rows = _sheet(release.cumulative_lcia, "LCIA")
    assert rows[0][5] == "Method" and rows[0][6] == "IPCC 2021"
    assert rows[3][0] == "Activity UUID_Product UUID"
    by_native = {row[0]: row for row in rows[4:]}
    # the treatment's reference amount is -1, so its score is the credit's positive value
    assert by_native[TREAT][5] == -1.0 and by_native[TREAT][6] == pytest.approx(0.35)


def test_the_steel_unit_override_changes_the_unit_in_both_files(tmp_path: Path) -> None:
    build_release(tmp_path, steel_unit="guest night")
    reference = _reference(tmp_path, STEEL)
    assert reference.findtext(f"{{{NS}}}name") == "steel"
    assert reference.findtext(f"{{{NS}}}unitName") == "guest night"
    root = ET.parse(tmp_path / "ecospold" / "MasterData" / "IntermediateExchanges.xml").getroot()
    steel = next(
        e for e in root.findall(f"{{{NS}}}intermediateExchange") if e.get("id") == STEEL_PRODUCT
    )
    assert steel.findtext(f"{{{NS}}}unitName") == "guest night"


def test_the_steel_geography_override_changes_the_dataset_and_the_overview(tmp_path: Path) -> None:
    release = build_release(tmp_path, steel_geography="RER")
    shortname = _dataset(tmp_path, STEEL).find(
        f"{{{NS}}}childActivityDataset/{{{NS}}}activityDescription/{{{NS}}}geography/{{{NS}}}shortname"
    )
    assert shortname is not None
    assert shortname.text == "RER"
    rows = _sheet(release.overview, "Cut-Off AO")
    assert {row[0]: row for row in rows[1:]}[STEEL][4] == "RER"


def test_the_lognormal_variance_override_changes_the_uncertainty(tmp_path: Path) -> None:
    build_release(tmp_path, lognormal_variance=0.25)
    electricity = next(
        exchange
        for exchange in _exchanges(tmp_path, STEEL, "intermediateExchange")
        if exchange.get("intermediateExchangeId") == ELEC_PRODUCT
    )
    lognormal = electricity.find(f"{{{NS}}}uncertainty/{{{NS}}}lognormal")
    assert lognormal is not None
    assert lognormal.get("variance") == "0.25"
    assert lognormal.get("varianceWithPedigreeUncertainty") == "0.25"


def test_the_extra_factor_row_names_a_flow_the_masterdata_lacks(tmp_path: Path) -> None:
    release = build_release(tmp_path, extra_factor_row=True)
    names = [row[3] for row in _sheet(release.lcia, "CFs")[1:]]
    assert names == ["Carbon dioxide, fossil", "Unobtainium", "Argon"]
    assert _sheet(release.lcia, "CFs")[2][6] == 5.0


def test_the_overview_missing_override_omits_electricity(tmp_path: Path) -> None:
    release = build_release(tmp_path, overview_missing=True)
    rows = _sheet(release.overview, "Cut-Off AO")
    assert {row[0] for row in rows[1:]} == {STEEL, TREAT, AIR}


def test_an_unknown_override_refuses(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="stel_unit"):
        build_release(tmp_path, stel_unit="kg")
