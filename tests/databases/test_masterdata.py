"""MasterData is read as the release states it, and a unit the core lacks is collected."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ecosemantic.databases.ecoinvent.masterdata import (
    base_flows,
    flow_type,
    read_masterdata,
    read_units,
    unit_name,
)
from ecosemantic.errors import Invalid, NotSupported
from tests.databases.spold_fixture import CO2, IRON, NS, UNUSED, build_release


def test_elementary_exchanges_carry_their_compartment_and_core_unit(tmp_path: Path) -> None:
    master = read_masterdata(build_release(tmp_path).ecospold)
    co2 = master.elementary[CO2]
    assert (co2.name, co2.unit, co2.compartment, co2.subcompartment) == (
        "Carbon dioxide, fossil",
        "kilogram",
        "air",
        "unspecified",
    )


def test_a_flow_takes_its_type_from_its_compartment() -> None:
    assert flow_type("natural resource") == "natural resource"
    assert flow_type("inventory indicator") == "inventory indicator"
    assert flow_type("economic") == "economic"
    assert flow_type("air") == "emission"


def test_an_unknown_unit_is_collected_not_guessed(tmp_path: Path) -> None:
    master = read_masterdata(build_release(tmp_path, steel_unit="furlong").ecospold)
    assert "furlong" in master.unknown_units


def test_a_known_unit_symbol_answers_the_name_the_core_uses() -> None:
    assert unit_name("kg") == "kilogram"
    assert unit_name("kWh") == "kilowatt hour"


def test_units_xml_declares_every_unit_symbol_of_the_release(tmp_path: Path) -> None:
    release = build_release(tmp_path)
    assert read_units(release.ecospold) == ("kg", "kWh", "hogshead")


def test_a_unit_the_core_does_not_know_is_named_and_kept(tmp_path: Path) -> None:
    with pytest.raises(NotSupported, match="furlong"):
        unit_name("furlong")
    master = read_masterdata(build_release(tmp_path, steel_unit="furlong").ecospold)
    assert master.unknown_units == {"furlong": ["steel"]}


def test_every_elementary_exchange_becomes_a_flow_with_its_categories(tmp_path: Path) -> None:
    master = read_masterdata(build_release(tmp_path).ecospold)
    flows = {flow.code: flow for flow in base_flows(master)}
    assert set(flows) == {CO2, IRON, UNUSED}
    co2 = flows[CO2]
    assert (co2.name, co2.unit, co2.categories, co2.type, co2.cas) == (
        "Carbon dioxide, fossil",
        "kilogram",
        ("air", "unspecified"),
        "emission",
        "000124-38-9",
    )
    iron = flows[IRON]
    assert (iron.name, iron.categories, iron.type, iron.cas) == (
        "Iron",
        ("natural resource", "in ground"),
        "natural resource",
        "007439-89-6",
    )
    argon = flows[UNUSED]
    assert (argon.name, argon.categories, argon.type) == (
        "Argon",
        ("air", "unspecified"),
        "emission",
    )


def test_a_missing_compartment_element_stops_the_read(tmp_path: Path) -> None:
    masterdata = tmp_path / "MasterData"
    masterdata.mkdir()
    root = ET.Element(f"{{{NS}}}validElementaryExchanges")
    exchange = ET.SubElement(root, f"{{{NS}}}elementaryExchange", {"id": CO2, "unitId": "unit"})
    ET.SubElement(exchange, f"{{{NS}}}name").text = "Carbon dioxide, fossil"
    ET.SubElement(exchange, f"{{{NS}}}unitName").text = "kg"
    ET.ElementTree(root).write(masterdata / "ElementaryExchanges.xml", encoding="utf-8")
    empty = ET.ElementTree(ET.Element(f"{{{NS}}}validIntermediateExchanges"))
    empty.write(masterdata / "IntermediateExchanges.xml", encoding="utf-8")
    with pytest.raises(Invalid, match=CO2):
        read_masterdata(tmp_path)
