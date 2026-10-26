"""The package an export writes: each record openLCA would write, and what it leaves out."""

from __future__ import annotations

import inspect
import json
import re
import zipfile
from pathlib import Path

import olca_schema as o
import pytest
from olca_schema.zipio import ZipReader

from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.databases.zolca.export import entities, write
from ecosemantic.databases.zolca.export.tables import Tables
from ecosemantic.errors import Conflict, Invalid, NotSupported
from ecosemantic.package.background import read_background
from tests.databases.zolca.fixture import FIXTURES, recorded

CHILE = {
    "@type": "Location",
    "@id": "00000000-0000-4000-8000-000000000031",
    "name": "Chile",
    "category": "Geography",
}
WORLD = {
    "@type": "Location",
    "@id": "00000000-0000-4000-8000-000000000032",
    "name": "Rest of World",
    "category": "Geography",
}
ANA = {"@type": "Actor", "@id": "00000000-0000-4000-8000-000000000021", "name": "Ana Soto"}
BRUNO = {"@type": "Actor", "@id": "00000000-0000-4000-8000-000000000022", "name": "Bruno Diaz"}
REPORT = {
    "@type": "Source",
    "@id": "00000000-0000-4000-8000-000000000041",
    "name": "Hydropower report",
}
MEGAJOULE = {"@type": "Unit", "@id": "00000000-0000-4000-8000-000000000051", "name": "MJ"}
KILOWATTHOUR = {"@type": "Unit", "@id": "00000000-0000-4000-8000-000000000052", "name": "kWh"}
KILOGRAM = {"@type": "Unit", "@id": "00000000-0000-4000-8000-000000000053", "name": "kg"}
ENERGY = {
    "@type": "FlowProperty",
    "@id": "00000000-0000-4000-8000-000000000071",
    "name": "Energy",
    "category": "Quantities",
    "refUnit": "MJ",
}
MASS = {
    "@type": "FlowProperty",
    "@id": "00000000-0000-4000-8000-000000000073",
    "name": "Mass",
    "category": "Quantities",
    "refUnit": "kg",
}
ELECTRICITY = {
    "@type": "Flow",
    "@id": "00000000-0000-4000-8000-000000000081",
    "name": "electricity, high voltage",
    "category": "Resources/Renewable",
    "flowType": "PRODUCT_FLOW",
    "refUnit": "MJ",
    "location": "CL",
}
WATER = {
    "@type": "Flow",
    "@id": "00000000-0000-4000-8000-000000000082",
    "name": "water, river",
    "category": "Resources",
    "flowType": "ELEMENTARY_FLOW",
    "refUnit": "kg",
}
HYDRO = {
    "@type": "Process",
    "@id": "00000000-0000-4000-8000-000000000091",
    "name": "electricity production, hydro",
    "category": "Energy/Electricity/Grid",
    "processType": "UNIT_PROCESS",
    "flowType": "PRODUCT_FLOW",
    "location": "CL",
}
SUPPLY = {
    "@type": "Process",
    "@id": "00000000-0000-4000-8000-000000000092",
    "name": "electricity supply, low voltage",
    "category": "Energy/Electricity",
    "processType": "LCI_RESULT",
    "flowType": "PRODUCT_FLOW",
    "location": "RoW",
}
PEDIGREE = {
    "@type": "DQSystem",
    "@id": "00000000-0000-4000-8000-000000000141",
    "name": "Pedigree matrix",
}
EURO = {
    "@type": "Currency",
    "@id": "00000000-0000-4000-8000-000000000151",
    "name": "Euro",
    "category": "Currencies",
}
CLIMATE = {
    "@type": "ImpactCategory",
    "@id": "00000000-0000-4000-8000-000000000111",
    "name": "Climate change",
    "category": "Climate change",
    "refUnit": "kg CO2 eq",
}
WATER_USE = {
    "@type": "ImpactCategory",
    "@id": "00000000-0000-4000-8000-000000000112",
    "name": "Water use",
    "category": "Climate change",
    "refUnit": "m3",
}
GWP_SCALE = {
    "@type": "Parameter",
    "@id": "00000000-0000-4000-8000-000000000132",
    "name": "gwp_scale",
    "category": "Parameters",
}


def tables() -> Tables:
    return Tables(Database(FIXTURES / "openlca.zip"))


def rows(name: str) -> dict[int, dict[str, object]]:
    """`rows.json`'s live rows of one table, by their `ID`."""
    return {int(row["ID"]): row for row in recorded()[name]}


def exported(into: Path) -> write.Exported:
    return write.export(FIXTURES / "openlca.zip", into / "bundle.zip")


def test_a_process_record_is_the_one_openlca_writes() -> None:
    read = tables()
    documents = rows("TBL_PROCESS_DOCS")

    assert entities.process(read, read.row("TBL_PROCESSES", 1)) == {
        "@type": "Process",
        "@id": "00000000-0000-4000-8000-000000000091",
        "name": "electricity production, hydro",
        "description": "Run-of-river plant.",
        "category": "Energy/Electricity/Grid",
        "version": "00.00.022",
        "lastChange": "2023-11-14T22:13:20.005Z",
        "tags": ["hydro;electricity"],
        "processType": "UNIT_PROCESS",
        "isInfrastructureProcess": False,
        "location": CHILE,
        "lastInternalId": 2,
        "dqSystem": PEDIGREE,
        "exchangeDqSystem": PEDIGREE,
        "processDocumentation": {
            "validFrom": "2020-01-01",
            "validUntil": "2025-12-31",
            "geographyDescription": "CL",
            "technologyDescription": documents[1]["TECHNOLOGY"],
            "completenessDescription": "",
            "intendedApplication": "Policy support",
            "creationDate": "2024-05-06T07:08:09",
            "isCopyrightProtected": True,
            "dataGenerator": ANA,
            "dataDocumentor": BRUNO,
            "publication": REPORT,
            "sources": [REPORT],
            "reviews": [
                {
                    "reviewType": "",
                    "scopes": [],
                    "assessment": [],
                    "details": "Reviewed by a third party.",
                    "report": REPORT,
                    "reviewers": [ANA, BRUNO],
                }
            ],
        },
        "parameters": [],
        "exchanges": [
            {
                "@type": "Exchange",
                "internalId": 1,
                "isInput": False,
                "isAvoidedProduct": False,
                "amount": 1.0,
                "flow": ELECTRICITY,
                "unit": MEGAJOULE,
                "flowProperty": ENERGY,
                "isQuantitativeReference": True,
            },
            {
                "@type": "Exchange",
                "internalId": 2,
                "isInput": True,
                "isAvoidedProduct": False,
                "amount": 0.5,
                "amountFormula": "0.5",
                "dqEntry": "1;2;3",
                "description": "River water input",
                "baseUncertainty": 0.1,
                "flow": WATER,
                "unit": KILOGRAM,
                "flowProperty": MASS,
                "uncertainty": {
                    "@type": "Uncertainty",
                    "distributionType": "LOG_NORMAL_DISTRIBUTION",
                    "geomMean": 0.5,
                    "geomSd": 2.0,
                },
            },
        ],
        "socialAspects": [],
        "allocationFactors": [],
    }


def test_a_second_process_carries_its_provider_its_currency_and_its_own_documentation() -> None:
    read = tables()
    documents = rows("TBL_PROCESS_DOCS")
    supply = entities.process(read, read.row("TBL_PROCESSES", 2))

    assert supply["location"] == WORLD
    assert supply["isInfrastructureProcess"] is True
    assert "lastChange" not in supply
    assert "dqSystem" not in supply
    assert supply["exchanges"][1] == {
        "@type": "Exchange",
        "internalId": 2,
        "isInput": True,
        "isAvoidedProduct": False,
        "amount": 0.9,
        "costValue": 12.5,
        "flow": ELECTRICITY,
        "unit": KILOWATTHOUR,
        "flowProperty": ENERGY,
        "defaultProvider": HYDRO,
        "currency": EURO,
    }
    assert supply["processDocumentation"]["technologyDescription"] == (documents[2]["TECHNOLOGY"])
    assert supply["processDocumentation"]["isCopyrightProtected"] is False
    assert "precedingDataSet" not in supply["processDocumentation"]


def test_a_flow_record_is_the_one_openlca_writes() -> None:
    read = tables()

    assert entities.flow(read, read.row("TBL_FLOWS", 2)) == {
        "@type": "Flow",
        "@id": "00000000-0000-4000-8000-000000000082",
        "name": "water, river",
        "category": "Resources",
        "version": "00.00.022",
        "flowType": "ELEMENTARY_FLOW",
        "cas": "7732-18-5",
        "formula": "H2O",
        "isInfrastructureFlow": False,
        "flowProperties": [
            {
                "@type": "FlowPropertyFactor",
                "isRefFlowProperty": True,
                "flowProperty": MASS,
                "conversionFactor": 1.0,
            }
        ],
    }


def test_a_flow_property_and_a_unit_group_records_are_openlcas() -> None:
    read = tables()

    assert entities.flow_property(read, read.row("TBL_FLOW_PROPERTIES", 1)) == {
        "@type": "FlowProperty",
        "@id": "00000000-0000-4000-8000-000000000071",
        "name": "Energy",
        "description": "Energy content.",
        "category": "Quantities",
        "version": "00.00.022",
        "lastChange": "2023-11-14T22:13:20.003Z",
        "flowPropertyType": "PHYSICAL_QUANTITY",
        "unitGroup": {
            "@type": "UnitGroup",
            "@id": "00000000-0000-4000-8000-000000000061",
            "name": "Units of energy",
            "category": "Units",
        },
    }
    assert entities.unit_group(read, read.row("TBL_UNIT_GROUPS", 1)) == {
        "@type": "UnitGroup",
        "@id": "00000000-0000-4000-8000-000000000061",
        "name": "Units of energy",
        "description": "Energy units.",
        "category": "Units",
        "version": "00.00.022",
        "defaultFlowProperty": ENERGY,
        "units": [
            {
                "@type": "Unit",
                "@id": "00000000-0000-4000-8000-000000000051",
                "name": "MJ",
                "description": "Megajoule",
                "conversionFactor": 1.0,
                "isRefUnit": True,
            },
            {
                "@type": "Unit",
                "@id": "00000000-0000-4000-8000-000000000052",
                "name": "kWh",
                "description": "Kilowatt hour",
                "conversionFactor": 3.6,
                "synonyms": ["kilowatt hour", "kW h"],
            },
        ],
    }


def test_a_location_record_carries_its_code_and_its_geometry() -> None:
    read = tables()
    locations = rows("TBL_LOCATIONS")
    document = json.loads((FIXTURES / "rows.json").read_text())

    assert entities.location(read, read.row("TBL_LOCATIONS", 1)) == {
        "@type": "Location",
        "@id": "00000000-0000-4000-8000-000000000031",
        "name": "Chile",
        "description": "Country in South America.",
        "category": "Geography",
        "version": "00.00.022",
        "lastChange": "2023-11-14T22:13:20.002Z",
        "tags": ["south america"],
        "code": "CL",
        "latitude": -33.4,
        "longitude": -70.6,
        "geometry": document["databases"]["openlca.zip"]["geometry"]["CL"],
    }
    assert locations[1]["CODE"] == "CL"


def test_a_source_and_an_actor_record_are_openlcas() -> None:
    read = tables()

    assert entities.source(read, read.row("TBL_SOURCES", 1)) == {
        "@type": "Source",
        "@id": "00000000-0000-4000-8000-000000000041",
        "name": "Hydropower report",
        "description": "A report on run-of-river plants.",
        "version": "00.00.022",
        "tags": ["report;hydro"],
        "url": "https://example.org/hydro.pdf",
        "textReference": "Soto, A. (2021): Hydropower in Chile. Santiago.",
        "year": 2021,
    }
    assert entities.actor(read, read.row("TBL_ACTORS", 1)) == {
        "@type": "Actor",
        "@id": "00000000-0000-4000-8000-000000000021",
        "name": "Ana Soto",
        "description": "Data generator.",
        "version": "00.00.022",
        "lastChange": "2023-11-14T22:13:20.001Z",
        "tags": ["author"],
        "address": "Av. Siempre Viva 742",
        "city": "Santiago",
        "country": "CL",
        "email": "ana@example.org",
        "telefax": "+56 2 2000 0001",
        "telephone": "+56 2 2000 0002",
        "website": "https://example.org/ana",
        "zipCode": "8320000",
    }


def test_a_currency_and_a_data_quality_system_records_are_openlcas() -> None:
    read = tables()

    assert entities.currency(read, read.row("TBL_CURRENCIES", 2)) == {
        "@type": "Currency",
        "@id": "00000000-0000-4000-8000-000000000152",
        "name": "US Dollar",
        "category": "Currencies",
        "version": "00.00.022",
        "code": "USD",
        "conversionFactor": 1.1,
        "refCurrency": EURO,
    }
    assert entities.dq_system(read, read.row("TBL_DQ_SYSTEMS", 1)) == {
        "@type": "DQSystem",
        "@id": "00000000-0000-4000-8000-000000000141",
        "name": "Pedigree matrix",
        "version": "00.00.022",
        "hasUncertainties": True,
        "source": REPORT,
        "indicators": [
            {
                "name": "Reliability",
                "position": 1,
                "scores": [
                    {
                        "position": 1,
                        "label": "1",
                        "description": "Verified data from measurements",
                        "uncertainty": 0.0,
                    },
                    {
                        "position": 5,
                        "label": "5",
                        "description": "Unverified data from a non-qualified source",
                        "uncertainty": 0.05,
                    },
                ],
            },
            {
                "name": "Completeness",
                "position": 2,
                "scores": [
                    {
                        "position": 1,
                        "label": "1",
                        "description": "Representative data from all sites",
                        "uncertainty": 0.0,
                    }
                ],
            },
        ],
    }


def test_an_impact_method_record_carries_its_categories_and_its_nw_set() -> None:
    read = tables()

    assert entities.impact_method(read, read.row("TBL_IMPACT_METHODS", 1)) == {
        "@type": "ImpactMethod",
        "@id": "00000000-0000-4000-8000-000000000101",
        "name": "Climate method",
        "description": "One method, two categories.",
        "category": "Methods",
        "version": "00.00.022",
        "lastChange": "2023-11-14T22:13:20.006Z",
        "code": "CM-1",
        "source": REPORT,
        "impactCategories": [CLIMATE, WATER_USE],
        "nwSets": [
            {
                "@type": "NwSet",
                "@id": "00000000-0000-4000-8000-000000000121",
                "name": "Points",
                "description": "Normalisation and weighting.",
                "weightedScoreUnit": "Pt",
                "factors": [
                    {
                        "impactCategory": CLIMATE,
                        "normalisationFactor": 50_000.0,
                        "weightingFactor": 1.0,
                    },
                    {
                        "impactCategory": WATER_USE,
                        "normalisationFactor": 100.0,
                        "weightingFactor": 0.5,
                    },
                ],
            }
        ],
    }


def test_an_impact_category_record_carries_its_factor_and_its_parameter() -> None:
    read = tables()

    assert entities.impact_category(read, read.row("TBL_IMPACT_CATEGORIES", 1)) == {
        "@type": "ImpactCategory",
        "@id": "00000000-0000-4000-8000-000000000111",
        "name": "Climate change",
        "description": "GWP over 100 years.",
        "category": "Climate change",
        "version": "03.00.087",
        "lastChange": "2023-11-14T22:13:20.007Z",
        "code": "GWP100",
        "refUnit": "kg CO2 eq",
        "direction": "OUTPUT",
        "parameters": [
            {
                "@type": "Parameter",
                "@id": "00000000-0000-4000-8000-000000000132",
                "name": "gwp_scale",
                "category": "Parameters",
                "version": "00.00.022",
                "parameterScope": "IMPACT_SCOPE",
                "isInputParameter": False,
                "value": 1.0,
                "formula": "global_factor * 2",
            }
        ],
        "impactFactors": [
            {
                "value": 0.5,
                "formula": "value * 1.0",
                "flow": ELECTRICITY,
                "unit": MEGAJOULE,
                "flowProperty": ENERGY,
            },
            {
                "value": 1.2,
                "flow": WATER,
                "unit": KILOGRAM,
                "flowProperty": MASS,
                "location": CHILE,
                "uncertainty": {
                    "@type": "Uncertainty",
                    "distributionType": "LOG_NORMAL_DISTRIBUTION",
                    "geomMean": 1.2,
                    "geomSd": 1.5,
                },
            },
            {
                "value": 0.8,
                "flow": WATER,
                "unit": KILOGRAM,
                "flowProperty": MASS,
            },
        ],
    }


def test_a_global_parameter_record_is_openlcas() -> None:
    read = tables()

    assert entities.parameter(read, read.row("TBL_PARAMETERS", 1)) == {
        "@type": "Parameter",
        "@id": "00000000-0000-4000-8000-000000000131",
        "name": "global_factor",
        "description": "A global parameter.",
        "category": "Parameters",
        "version": "00.00.022",
        "parameterScope": "GLOBAL_SCOPE",
        "isInputParameter": False,
        "value": 2.5,
    }


def without_types(value: object) -> object:
    """A record without its `@type` keys, which openLCA writes and the classes do not."""
    if isinstance(value, dict):
        return {key: without_types(found) for key, found in value.items() if key != "@type"}
    if isinstance(value, list):
        return [without_types(found) for found in value]
    return value


def accepted_keys(cls: type) -> set[str]:
    """The JSON keys one `olca_schema` class reads or writes, from its own two methods."""
    found: set[str] = set()
    for method in (cls.to_dict, cls.from_dict):
        source = inspect.getsource(method)
        found.update(re.findall(r"d\.get\('([^']+)'", source))
        found.update(re.findall(r"d\['([^']+)'\]", source))
        if "'@type':" in source:
            found.add("@type")
    return found


CLASSES = {
    "TBL_PROCESSES": o.Process,
    "TBL_FLOWS": o.Flow,
    "TBL_FLOW_PROPERTIES": o.FlowProperty,
    "TBL_UNIT_GROUPS": o.UnitGroup,
    "TBL_LOCATIONS": o.Location,
    "TBL_SOURCES": o.Source,
    "TBL_ACTORS": o.Actor,
    "TBL_CURRENCIES": o.Currency,
    "TBL_DQ_SYSTEMS": o.DQSystem,
    "TBL_IMPACT_METHODS": o.ImpactMethod,
    "TBL_IMPACT_CATEGORIES": o.ImpactCategory,
}


def test_every_record_of_the_package_is_the_one_its_class_holds() -> None:
    read = tables()
    written = 0
    for table, entity in write.WRITTEN.items():
        cls = CLASSES[table]
        for row in read.rows(table):
            record = entity(read, row)
            assert set(record) <= accepted_keys(cls), (cls.__name__, sorted(record))
            assert without_types(cls.from_dict(record).to_dict()) == without_types(record), (
                cls.__name__
            )
            written += 1
    assert written == 22


def test_zipreader_reads_every_record_of_the_package(tmp_path: Path) -> None:
    result = exported(tmp_path)

    with ZipReader(str(result.bundle)) as reader:
        assert len(list(reader.read_each(o.Process))) == 2
        assert len(list(reader.read_each(o.Flow))) == 2
        assert len(list(reader.read_each(o.UnitGroup))) == 2
        assert len(list(reader.read_each(o.Location))) == 4
        assert len(list(reader.read_each(o.ImpactMethod))) == 1
        assert len(list(reader.read_each(o.ImpactCategory))) == 2
        assert len(list(reader.read_each(o.Parameter))) == 1


def test_the_archive_carries_the_marker_zipwriter_writes(tmp_path: Path) -> None:
    result = exported(tmp_path)

    with zipfile.ZipFile(result.bundle) as archive:
        assert archive.read("olca-schema.json") == b'{"version": 2}'
        assert not result.bundle.with_name(result.bundle.name + ".partial").exists()
        assert sorted({name.split("/")[0] for name in archive.namelist()}) == [
            "actors",
            "currencies",
            "dq_systems",
            "flow_properties",
            "flows",
            "lcia_categories",
            "lcia_methods",
            "locations",
            "olca-schema.json",
            "parameters",
            "processes",
            "sources",
            "unit_groups",
        ]


def test_the_report_counts_the_records_by_folder(tmp_path: Path) -> None:
    result = exported(tmp_path)

    assert result.records == {
        "processes": 2,
        "flows": 2,
        "flow_properties": 2,
        "unit_groups": 2,
        "locations": 4,
        "sources": 1,
        "actors": 2,
        "currencies": 2,
        "dq_systems": 1,
        "lcia_methods": 1,
        "lcia_categories": 2,
        "parameters": 1,
    }


def test_the_report_names_the_rows_the_package_does_not_carry(tmp_path: Path) -> None:
    result = exported(tmp_path)
    named = {(entry.table, entry.rows) for entry in result.not_carried}

    assert named == {
        ("OPENLCA_VERSION", 1),
        ("SEQUENCE", 1),
        ("TBL_CATEGORIES", 12),
        ("TBL_FLOW_PROPERTIES", 1),
        ("TBL_LOCATIONS.OTHER_PROPERTIES", 1),
        ("TBL_MAPPING_FILES", 1),
        ("TBL_PROCESS_DOCS.PRECEDING_DATASET", 1),
    }
    assert all(entry.reason for entry in result.not_carried)


def test_the_core_imports_the_package(tmp_path: Path) -> None:
    result = exported(tmp_path)
    imported = read_background(result.bundle, "fixture", foreground=frozenset())

    assert imported.processes == 2
    assert {link.flow for link in imported.unlinked} == set()
    by_category = {(m.key[1], m.key[2]): m for m in imported.methods}
    assert by_category[("Climate method", "Climate change")].set_apart == 1


def test_a_destination_that_exists_is_a_conflict(tmp_path: Path) -> None:
    destination = tmp_path / "bundle.zip"
    destination.write_bytes(b"")

    with pytest.raises(Conflict):
        write.export(FIXTURES / "openlca.zip", destination)


class _Rows:
    """A double of `Tables` holding one row of each table a written record reaches."""

    def __init__(self, rows: dict[str, list[dict[str, object]]]) -> None:
        self.rows_of = rows

    def rows(self, table: str) -> tuple[dict[str, object], ...]:
        """Every row of one table this double holds."""
        return tuple(self.rows_of.get(table, ()))

    def row(self, table: str, row_id: int) -> dict[str, object]:
        """The row of one table whose `ID` is `row_id`."""
        return {row["ID"]: row for row in self.rows(table)}[row_id]

    def children(self, table: str, column: str, value: int) -> tuple[dict[str, object], ...]:
        """The rows of one table that name `value` in `column`."""
        return tuple(row for row in self.rows(table) if row.get(column) == value)


def a_stub(broken: dict[tuple[str, str], object] | None = None) -> _Rows:
    """A double of `Tables` with one row of every table a written record reaches."""
    rows: dict[str, list[dict[str, object]]] = {
        "TBL_PROCESSES": [
            {
                "ID": 1,
                "REF_ID": "p",
                "NAME": "process",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "PROCESS_TYPE": "UNIT_PROCESS",
                "DEFAULT_ALLOCATION_METHOD": None,
                "INFRASTRUCTURE_PROCESS": 0,
                "F_LOCATION": None,
                "F_PROCESS_DOC": 1,
                "F_QUANTITATIVE_REFERENCE": 1,
                "LAST_INTERNAL_ID": 1,
                "F_DQ_SYSTEM": None,
                "F_EXCHANGE_DQ_SYSTEM": None,
                "F_SOCIAL_DQ_SYSTEM": None,
                "DQ_ENTRY": None,
            }
        ],
        "TBL_PROCESS_DOCS": [
            {
                "ID": 1,
                "VALID_FROM": None,
                "VALID_UNTIL": None,
                "TIME": None,
                "GEOGRAPHY": None,
                "TECHNOLOGY": None,
                "INVENTORY_METHOD": None,
                "MODELING_CONSTANTS": None,
                "DATA_COMPLETENESS": None,
                "DATA_SELECTION": None,
                "DATA_TREATMENT": None,
                "SAMPLING_PROCEDURE": None,
                "DATA_COLLECTION_PERIOD": None,
                "USE_ADVICE": None,
                "FLOW_COMPLETENESS": None,
                "INTENDED_APPLICATION": None,
                "PROJECT": None,
                "F_DATA_GENERATOR": None,
                "F_DATA_DOCUMENTOR": None,
                "CREATION_DATE": None,
                "F_PUBLICATION": None,
                "F_DATA_OWNER": None,
                "COPYRIGHT": 0,
                "ACCESS_RESTRICTIONS": None,
                "PRECEDING_DATASET": None,
            }
        ],
        "TBL_EXCHANGES": [
            {
                "ID": 1,
                "F_OWNER": 1,
                "INTERNAL_ID": 1,
                "F_FLOW": 1,
                "F_UNIT": 1,
                "IS_INPUT": 0,
                "F_FLOW_PROPERTY_FACTOR": 1,
                "RESULTING_AMOUNT_VALUE": 1.0,
                "RESULTING_AMOUNT_FORMULA": None,
                "AVOIDED_PRODUCT": 0,
                "F_DEFAULT_PROVIDER": 0,
                "DEFAULT_PROVIDER_TYPE": 0,
                "F_LOCATION": None,
                "DESCRIPTION": None,
                "COST_VALUE": None,
                "COST_FORMULA": None,
                "F_CURRENCY": None,
                "DISTRIBUTION_TYPE": None,
                "PARAMETER1_VALUE": None,
                "PARAMETER2_VALUE": None,
                "PARAMETER3_VALUE": None,
                "DQ_ENTRY": None,
                "BASE_UNCERTAINTY": None,
            }
        ],
        "TBL_REVIEWS": [
            {
                "ID": 1,
                "F_OWNER": 1,
                "REVIEW_TYPE": None,
                "SCOPES": None,
                "DETAILS": None,
                "ASSESSMENT": None,
                "F_REPORT": None,
            }
        ],
        "TBL_FLOW_PROPERTY_FACTORS": [
            {"ID": 1, "CONVERSION_FACTOR": 1.0, "F_FLOW": 1, "F_FLOW_PROPERTY": 1}
        ],
        "TBL_FLOWS": [
            {
                "ID": 1,
                "REF_ID": "f",
                "NAME": "flow",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "SYNONYMS": None,
                "FLOW_TYPE": "PRODUCT_FLOW",
                "CAS_NUMBER": None,
                "FORMULA": None,
                "INFRASTRUCTURE_FLOW": 0,
                "F_REFERENCE_FLOW_PROPERTY": 1,
                "F_LOCATION": None,
            }
        ],
        "TBL_FLOW_PROPERTIES": [
            {
                "ID": 1,
                "REF_ID": "fp",
                "NAME": "property",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "F_UNIT_GROUP": None,
                "FLOW_PROPERTY_TYPE": "1",
            }
        ],
        "TBL_UNITS": [
            {
                "ID": 1,
                "REF_ID": "u",
                "NAME": "kg",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "CONVERSION_FACTOR": 1.0,
                "SYNONYMS": None,
                "F_UNIT_GROUP": 1,
            }
        ],
        "TBL_ACTORS": [{"ID": 1, "REF_ID": "a", "NAME": "actor", "F_CATEGORY": None}],
        "TBL_ACTOR_LINKS": [{"ID": 1, "F_OWNER": 1, "F_ACTOR": 1}],
        "TBL_SOURCES": [{"ID": 1, "REF_ID": "s", "NAME": "source", "F_CATEGORY": None}],
        "TBL_SOURCE_LINKS": [{"ID": 1, "F_OWNER": 1, "F_SOURCE": 1}],
        "TBL_IMPACT_CATEGORIES": [
            {
                "ID": 1,
                "REF_ID": "c",
                "NAME": "category",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "CODE": None,
                "REFERENCE_UNIT": "kg",
                "DIRECTION": None,
                "F_SOURCE": None,
            }
        ],
        "TBL_IMPACT_METHODS": [
            {
                "ID": 1,
                "REF_ID": "m",
                "NAME": "method",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "CODE": None,
                "F_SOURCE": None,
            }
        ],
        "TBL_UNIT_GROUPS": [
            {
                "ID": 1,
                "REF_ID": "g",
                "NAME": "group",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "F_DEFAULT_FLOW_PROPERTY": None,
                "F_REFERENCE_UNIT": 1,
            }
        ],
        "TBL_DQ_SYSTEMS": [
            {
                "ID": 1,
                "REF_ID": "q",
                "NAME": "system",
                "DESCRIPTION": None,
                "F_CATEGORY": None,
                "VERSION": 0,
                "LAST_CHANGE": 0,
                "TAGS": None,
                "HAS_UNCERTAINTIES": 0,
                "F_SOURCE": None,
            }
        ],
        "TBL_DQ_INDICATORS": [{"ID": 1, "F_DQ_SYSTEM": 1, "NAME": "indicator", "POSITION": 1}],
    }
    for (table, column), value in (broken or {}).items():
        rows[table][0][column] = value
    return _Rows(rows)


def a_process(
    broken: dict[tuple[str, str], object] | None = None,
) -> tuple[_Rows, dict[str, object]]:
    """A double of `Tables` and the one process row it holds, with the columns a test breaks."""
    stub = a_stub(broken)
    return stub, stub.rows_of["TBL_PROCESSES"][0]


def test_an_uncertainty_of_an_unknown_distribution_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        entities.process(*a_process({("TBL_EXCHANGES", "DISTRIBUTION_TYPE"): 9}))


def test_an_aspect_map_is_not_one_the_reader_takes() -> None:
    with pytest.raises(NotSupported):
        entities.process(*a_process({("TBL_REVIEWS", "SCOPES"): "reliability:1"}))
    with pytest.raises(NotSupported):
        entities.process(*a_process({("TBL_REVIEWS", "ASSESSMENT"): "reliability:1"}))


def test_a_flow_completeness_that_is_filled_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        entities.process(*a_process({("TBL_PROCESS_DOCS", "FLOW_COMPLETENESS"): "0.9"}))


def test_a_validity_boundary_or_a_creation_date_of_another_shape_is_invalid() -> None:
    with pytest.raises(Invalid):
        entities.process(*a_process({("TBL_PROCESS_DOCS", "VALID_FROM"): "2020-01-01"}))
    with pytest.raises(Invalid):
        entities.process(*a_process({("TBL_PROCESS_DOCS", "CREATION_DATE"): "2024-05-06"}))


def test_a_row_of_another_id_or_a_key_that_names_no_row_is_invalid() -> None:
    with pytest.raises(Invalid):
        entities.process(*a_process({("TBL_PROCESSES", "ID"): "one"}))
    with pytest.raises(Invalid):
        entities.process(*a_process({("TBL_EXCHANGES", "F_FLOW"): None}))


def test_a_flow_property_or_a_parameter_of_an_unknown_kind_is_not_supported() -> None:
    stub = a_stub()
    stub.rows_of["TBL_FLOW_PROPERTIES"][0]["FLOW_PROPERTY_TYPE"] = "7"
    with pytest.raises(NotSupported):
        entities.flow_property(stub, stub.row("TBL_FLOW_PROPERTIES", 1))
    parameter = {
        "ID": 1,
        "REF_ID": "q",
        "NAME": "p",
        "DESCRIPTION": None,
        "F_CATEGORY": None,
        "VERSION": 0,
        "LAST_CHANGE": 0,
        "TAGS": None,
        "SCOPE": "ELSEWHERE",
        "IS_INPUT_PARAM": 0,
        "VALUE": 1.0,
        "FORMULA": None,
        "DISTRIBUTION_TYPE": None,
        "PARAMETER1_VALUE": None,
        "PARAMETER2_VALUE": None,
        "PARAMETER3_VALUE": None,
    }
    with pytest.raises(NotSupported):
        entities.parameter(stub, parameter)

    parameter["SCOPE"] = "GLOBAL"
    parameter["DISTRIBUTION_TYPE"] = 1
    parameter["PARAMETER1_VALUE"] = 2.5
    parameter["PARAMETER2_VALUE"] = 2.0
    assert entities.parameter(stub, parameter)["uncertainty"] == {
        "@type": "Uncertainty",
        "distributionType": "LOG_NORMAL_DISTRIBUTION",
        "geomMean": 2.5,
        "geomSd": 2.0,
    }


def test_a_parameter_whose_scope_is_no_text_is_invalid() -> None:
    stub = a_stub()
    parameter = {
        "ID": 1,
        "REF_ID": "q",
        "NAME": "p",
        "DESCRIPTION": None,
        "F_CATEGORY": None,
        "VERSION": 0,
        "LAST_CHANGE": 0,
        "TAGS": None,
        "SCOPE": 7,
        "IS_INPUT_PARAM": 0,
        "VALUE": 1.0,
        "FORMULA": None,
        "DISTRIBUTION_TYPE": None,
        "PARAMETER1_VALUE": None,
        "PARAMETER2_VALUE": None,
        "PARAMETER3_VALUE": None,
    }
    with pytest.raises(Invalid):
        entities.parameter(stub, parameter)


def test_a_category_with_no_factor_and_a_method_with_no_link_or_nw_set_write_no_such_key() -> None:
    stub = a_stub()

    category = entities.impact_category(stub, stub.row("TBL_IMPACT_CATEGORIES", 1))
    method = entities.impact_method(stub, stub.row("TBL_IMPACT_METHODS", 1))

    assert category["parameters"] == []
    assert "impactFactors" not in category
    assert "impactCategories" not in method
    assert "nwSets" not in method


def test_a_document_with_no_source_link_and_no_review_writes_neither_key() -> None:
    stub, row = a_process()
    stub.rows_of["TBL_SOURCE_LINKS"] = []
    stub.rows_of["TBL_REVIEWS"] = []

    documentation = entities.process(stub, row)["processDocumentation"]

    assert "sources" not in documentation
    assert "reviews" not in documentation


def test_a_review_with_no_actor_link_writes_no_reviewers() -> None:
    stub, row = a_process()
    with_link = entities.process(stub, row)["processDocumentation"]["reviews"][0]
    stub.rows_of["TBL_ACTOR_LINKS"] = []
    without_link = entities.process(stub, row)["processDocumentation"]["reviews"][0]

    assert [reviewer["@id"] for reviewer in with_link["reviewers"]] == ["a"]
    assert "reviewers" not in without_link


def test_a_nw_set_with_no_name_and_a_factor_with_no_value_write_none_of_them() -> None:
    stub = a_stub()
    stub.rows_of["TBL_NW_SETS"] = [
        {
            "ID": 1,
            "REF_ID": "n",
            "NAME": None,
            "DESCRIPTION": None,
            "F_IMPACT_METHOD": 1,
            "WEIGHTED_SCORE_UNIT": None,
        }
    ]
    stub.rows_of["TBL_NW_FACTORS"] = [
        {
            "ID": 1,
            "F_NW_SET": 1,
            "F_IMPACT_CATEGORY": 1,
            "NORMALISATION_FACTOR": None,
            "WEIGHTING_FACTOR": None,
        }
    ]

    nw_set = entities.impact_method(stub, stub.row("TBL_IMPACT_METHODS", 1))["nwSets"][0]
    factor = nw_set["factors"][0]

    assert "name" not in nw_set
    assert "weightedScoreUnit" not in nw_set
    assert "normalisationFactor" not in factor
    assert "weightingFactor" not in factor
    assert factor["impactCategory"]["@id"] == "c"


def test_a_process_with_no_child_row_still_writes_the_empty_lists_openlca_writes() -> None:
    stub, row = a_process()
    stub.rows_of["TBL_EXCHANGES"] = []

    record = entities.process(stub, row)

    assert record["parameters"] == []
    assert record["exchanges"] == []
    assert record["socialAspects"] == []
    assert record["allocationFactors"] == []


def test_a_nw_set_with_no_factor_still_writes_an_empty_list() -> None:
    stub = a_stub()
    stub.rows_of["TBL_NW_SETS"] = [
        {
            "ID": 1,
            "REF_ID": "n",
            "NAME": "set",
            "DESCRIPTION": None,
            "F_IMPACT_METHOD": 1,
            "WEIGHTED_SCORE_UNIT": None,
        }
    ]

    nw_set = entities.impact_method(stub, stub.row("TBL_IMPACT_METHODS", 1))["nwSets"][0]

    assert nw_set["factors"] == []


def test_a_name_that_is_null_writes_no_name_key() -> None:
    stub = a_stub()
    for table in (
        "TBL_IMPACT_CATEGORIES",
        "TBL_IMPACT_METHODS",
        "TBL_UNIT_GROUPS",
        "TBL_DQ_SYSTEMS",
        "TBL_DQ_INDICATORS",
        "TBL_UNITS",
    ):
        stub.rows_of[table][0]["NAME"] = None
    stub.rows_of["TBL_NW_SETS"] = [
        {
            "ID": 1,
            "REF_ID": "n",
            "NAME": None,
            "DESCRIPTION": None,
            "F_IMPACT_METHOD": 1,
            "WEIGHTED_SCORE_UNIT": None,
        }
    ]

    category = entities.impact_category(stub, stub.row("TBL_IMPACT_CATEGORIES", 1))
    method = entities.impact_method(stub, stub.row("TBL_IMPACT_METHODS", 1))
    group = entities.unit_group(stub, stub.row("TBL_UNIT_GROUPS", 1))
    system = entities.dq_system(stub, stub.row("TBL_DQ_SYSTEMS", 1))

    assert "name" not in category
    assert "name" not in method
    assert "name" not in group
    assert "name" not in group["units"][0]
    assert "name" not in system["indicators"][0]
    assert "name" not in method["nwSets"][0]


def test_a_flow_writes_its_synonyms_as_the_text_the_writer_is_given() -> None:
    stub = a_stub()
    stub.rows_of["TBL_FLOWS"][0]["SYNONYMS"] = "grid power; high voltage"

    assert entities.flow(stub, stub.row("TBL_FLOWS", 1))["synonyms"] == "grid power; high voltage"


def test_a_unit_writes_its_synonyms_split_and_an_empty_list_for_separators_only() -> None:
    stub = a_stub()
    assert "synonyms" not in entities.unit_group(stub, stub.row("TBL_UNIT_GROUPS", 1))["units"][0]

    stub.rows_of["TBL_UNITS"][0]["SYNONYMS"] = " ; "
    units = entities.unit_group(stub, stub.row("TBL_UNIT_GROUPS", 1))["units"]

    assert units[0]["synonyms"] == []
