"""The elementary exchanges, the geographies and the unit symbols a release's MasterData
declares."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from ecosemantic.errors import Invalid
from ecosemantic.model import units
from ecosemantic.package.base_writer import BaseFlow
from ecosemantic.ports.types import FlowType

NS = "{http://www.EcoInvent.org/EcoSpold02}"
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


@dataclass(frozen=True)
class ElementaryExchange:
    """One elementary exchange of MasterData: its id, unit, compartment and CAS number."""

    id: str
    name: str
    unit: str
    compartment: str
    subcompartment: str
    cas: str | None


@dataclass(frozen=True)
class MasterData:
    """A release's elementary exchanges by id, the English name of each geography by its
    shortname, and the unit symbols the core does not know."""

    elementary: dict[str, ElementaryExchange]
    geographies: dict[str, str]
    unknown_units: dict[str, list[str]]


def unit_name(symbol: str) -> str:
    """The core's long name for a unit symbol; a symbol the core does not know raises."""
    return units.by_symbol(symbol).name


def flow_type(compartment: str) -> FlowType:
    """The flow type a compartment names, and an emission for a compartment that names none."""
    for candidate in get_args(FlowType):
        if candidate != "emission" and compartment == candidate:
            return candidate
    return "emission"


def _exchanges(path: Path, tag: str) -> list[ET.Element]:
    """The MasterData elements of one tag, in document order."""
    return ET.parse(path).getroot().findall(f"{NS}{tag}")


def _english(element: ET.Element, tag: str) -> str:
    """The English text of a localised child element, empty when the element states none."""
    for child in element.findall(f"{NS}{tag}"):
        if child.get(_LANG) in (None, "en"):
            return child.text or ""
    return ""


def _geographies(path: Path) -> dict[str, str]:
    """The English name of every geography a release's MasterData declares, by its shortname.
    Raises for a geography with no shortname or no name, and for two of one shortname named
    differently."""
    named: dict[str, str] = {}
    for element in _exchanges(path, "geography"):
        shortname = _english(element, "shortname")
        name = _english(element, "name")
        if not shortname or not name:
            raise Invalid(
                f"geography {element.get('id')!r} declares no shortname or no name in English"
            )
        first = named.setdefault(shortname, name)
        if first != name:
            raise Invalid(f"shortname {shortname!r} is named {first!r} and {name!r}")
    return named


def text(element: ET.Element, tag: str) -> str:
    """The text of a child element, empty when the child is absent or carries none."""
    return element.findtext(f"{NS}{tag}") or ""


def _compartment(element: ET.Element) -> tuple[str, str]:
    """The compartment and subcompartment an elementary exchange declares."""
    pair = element.find(f"{NS}compartment")
    if pair is None:
        raise Invalid(f"elementary exchange {element.attrib['id']!r} declares no compartment")
    return text(pair, "compartment"), text(pair, "subcompartment")


def exchange_unit(element: ET.Element, user: str, unknown_units: dict[str, list[str]]) -> str:
    """The core's name for an exchange's unit, or the symbol itself recorded under the dataset
    using it when the core lacks it."""
    symbol = text(element, "unitName")
    if not units.knows(symbol):
        unknown_units.setdefault(symbol, []).append(user)
        return symbol
    return unit_name(symbol)


def read_masterdata(ecospold: Path) -> MasterData:
    """Read a release's MasterData: its elementary exchanges, its geographies and the units it
    names."""
    masterdata = ecospold / "MasterData"
    unknown_units: dict[str, list[str]] = {}
    elementary: dict[str, ElementaryExchange] = {}
    for element in _exchanges(masterdata / "ElementaryExchanges.xml", "elementaryExchange"):
        name = text(element, "name")
        compartment, subcompartment = _compartment(element)
        exchange = ElementaryExchange(
            id=element.attrib["id"],
            name=name,
            unit=exchange_unit(element, name, unknown_units),
            compartment=compartment,
            subcompartment=subcompartment,
            cas=element.get("casNumber"),
        )
        elementary[exchange.id] = exchange
    for element in _exchanges(masterdata / "IntermediateExchanges.xml", "intermediateExchange"):
        exchange_unit(element, text(element, "name"), unknown_units)
    return MasterData(
        elementary=elementary,
        geographies=_geographies(masterdata / "Geographies.xml"),
        unknown_units=unknown_units,
    )


def read_units(ecospold: Path) -> tuple[str, ...]:
    """Every unit symbol a release's MasterData/Units.xml declares."""
    root = ET.parse(ecospold / "MasterData" / "Units.xml").getroot()
    return tuple(text(unit, "name") for unit in root.findall(f"{NS}unit"))


def base_flows(master: MasterData) -> tuple[BaseFlow, ...]:
    """Every elementary exchange of a release as one base bundle's flow."""
    return tuple(
        BaseFlow(
            code=exchange.id,
            name=exchange.name,
            unit=exchange.unit,
            categories=(exchange.compartment, exchange.subcompartment),
            type=flow_type(exchange.compartment),
            cas=exchange.cas or None,
        )
        for exchange in master.elementary.values()
    )
