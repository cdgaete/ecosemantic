"""Create the synthetic Derby databases the zolca reader's tests read.

Run on a development machine with the JVM and the Derby jars openLCA 2.7 ships::

    python scripts/zolca/make_fixtures.py \\
        --java ~/openLCA/jre/bin/java \\
        --derby ~/openLCA/plugins/olca-app_2.7.0/libs \\
        --schema <scratch>/current_schema_derby.sql \\
        --out <scratch>/fixtures

`--schema` is the member `org/openlca/core/database/internal/current_schema_derby.sql`
of `olca-core-2.7.0.jar`, extracted beside the run and never into the repository.
The JVM is the `lib/server/libjvm.so` of the JRE `--java` names, and Derby is
10.17.1.0 (`derby-10.17.1.0.jar`, `derbyshared-10.17.1.0.jar`), driven through
JPype from an environment outside the repository. Nothing here is a dependency of
a distribution, and no test runs Java.

The run writes `openlca.zip`, `types.zip`, `encrypted.zip` and `unclean.zip`, each
zipped as openLCA zips a backup — the database directory's members at the zip's
root — and `rows.json`, which holds every live row of the first two, the emptied
heap as a template and its count, and the GeoJSON of each location whose `GEODATA`
the run writes. The schema's own `INSERT` statements leave one row in `SEQUENCE`
and one in `OPENLCA_VERSION`; `rows.json` records both.

Derby 10.17 opens a container's second allocation page only after 10,216 pages at
4096 bytes, its least page size, so the emptied heap is `TBL_IMPACT_FACTORS` filled
with 38,000 rows of a 1,000-character formula and then deleted: the container keeps
its two extents, its deleted records and its free pages, and the archive stays small.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import json
import struct
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import jpype
import jpype.imports

if TYPE_CHECKING:
    from java.sql import Connection, PreparedStatement

Value = str | int | float | bytes | datetime.date | None

DERBY_SHUTDOWN_SQLSTATE = "08006"
FILLED_FIRST_ID = 100_000
FILLED_COUNT = 38_000
DELETE_FILLED_FACTORS = "DELETE FROM TBL_IMPACT_FACTORS WHERE ID >= 100000"
DELETE_THE_SUPERSEDED_SOURCES = "DELETE FROM TBL_SOURCES WHERE ID IN (2, 3)"


def _ref(number: int) -> str:
    """A deterministic UUID, so a regenerated fixture keeps the same references."""
    return f"00000000-0000-4000-8000-{number:012d}"


def _varint(value: int) -> bytes:
    """One protobuf base-128 varint."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if not value:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _delimited(number: int, payload: bytes) -> bytes:
    """One length-delimited protobuf field, the wire type every `geo.proto` message uses."""
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def _point(x: float, y: float) -> bytes:
    """A `Point`: two fixed-64 doubles, `x` in field 1 and `y` in field 2."""
    return _varint(1 << 3 | 1) + struct.pack("<d", x) + _varint(2 << 3 | 1) + struct.pack("<d", y)


def _line_string(points: list[list[float]]) -> bytes:
    """A `LineString`: its points in repeated field 1."""
    return b"".join(_delimited(1, _point(point[0], point[1])) for point in points)


def _feature_collection(geometry: bytes) -> bytes:
    """The gzip member `GeoJSON` writes: one `Feature` holding one `Geometry`."""
    return gzip.compress(_delimited(1, _delimited(1, geometry)))


def _polygon_geodata(rings: list[list[list[float]]]) -> bytes:
    """The gzipped `FeatureCollection` of a GeoJSON polygon: a `Polygon` of `LineString`s."""
    polygon = b"".join(_delimited(1, _line_string(ring)) for ring in rings)
    return _feature_collection(_delimited(5, polygon))


def _point_geodata(*, x: float, y: float) -> bytes:
    """The gzipped `FeatureCollection` of a GeoJSON point."""
    return _feature_collection(_delimited(1, _point(x, y)))


CL_RING: list[list[float]] = [
    [-70.65, -33.45],
    [-70.45, -33.41],
    [-70.52, -33.27],
    [-70.68, -33.31],
    [-70.65, -33.45],
]
PT_POINT: list[float] = [8.0, 47.0]
GEOMETRY: dict[str, dict[str, object]] = {
    "CL": {"type": "Polygon", "coordinates": [CL_RING]},
    "PT": {"type": "Point", "coordinates": PT_POINT},
}

LONG_TECHNOLOGY = ("The plant diverts the river through a penstock into a Francis turbine; " * 900)[
    :60_000
]
LONG_SYNONYMS = ("high voltage electricity;grid power;power from the grid;" * 1_000)[:32_672]
LONG_CSV = ("old_id;new_id;name\n" * 6_000)[:100_000].encode()
OVERFLOW_TIME = ("Dataset valid for the operating years 2020 to 2025. " * 200)[:7_000]
OVERFLOW_GEOGRAPHY = ("Geography: Chile, central grid, latitude -33.4. " * 200)[:7_000]
OVERFLOW_TECHNOLOGY = ("Technology: run-of-river plant with a Francis turbine. " * 200)[:7_000]
OVERFLOW_INVENTORY = (
    "Inventory: foreground data from the operator, background from ecoinvent. " * 150
)[:7_000]
OVERFLOW_CONSTANTS = ("Modelling constants: no allocation, no substitution, cut-off 0. " * 150)[
    :7_000
]

INSERTS: dict[str, str] = {
    "TBL_CATEGORIES": (
        "INSERT INTO TBL_CATEGORIES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, "
        "TAGS, LIBRARY, DESCRIPTION, OTHER_PROPERTIES, MODEL_TYPE) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_ACTORS": (
        "INSERT INTO TBL_ACTORS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, TELEFAX, WEBSITE, ADDRESS, ZIP_CODE, EMAIL, "
        "TELEPHONE, COUNTRY, CITY) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_LOCATIONS": (
        "INSERT INTO TBL_LOCATIONS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, LONGITUDE, LATITUDE, CODE, GEODATA) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_SOURCES": (
        "INSERT INTO TBL_SOURCES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, SOURCE_YEAR, TEXT_REFERENCE, URL, "
        "EXTERNAL_FILE) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_UNITS": (
        "INSERT INTO TBL_UNITS (ID, REF_ID, NAME, DESCRIPTION, CONVERSION_FACTOR, SYNONYMS, "
        "F_UNIT_GROUP) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_UNIT_GROUPS": (
        "INSERT INTO TBL_UNIT_GROUPS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, F_REFERENCE_UNIT, F_DEFAULT_FLOW_PROPERTY) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_FLOW_PROPERTIES": (
        "INSERT INTO TBL_FLOW_PROPERTIES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, "
        "TAGS, LIBRARY, DESCRIPTION, OTHER_PROPERTIES, FLOW_PROPERTY_TYPE, F_UNIT_GROUP) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_FLOWS": (
        "INSERT INTO TBL_FLOWS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, LIBRARY, "
        "DESCRIPTION, OTHER_PROPERTIES, SYNONYMS, FLOW_TYPE, INFRASTRUCTURE_FLOW, CAS_NUMBER, "
        "FORMULA, F_REFERENCE_FLOW_PROPERTY, F_LOCATION) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_FLOW_PROPERTY_FACTORS": (
        "INSERT INTO TBL_FLOW_PROPERTY_FACTORS (ID, CONVERSION_FACTOR, F_FLOW, F_FLOW_PROPERTY) "
        "VALUES (?, ?, ?, ?)"
    ),
    "TBL_PROCESSES": (
        "INSERT INTO TBL_PROCESSES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, PROCESS_TYPE, DEFAULT_ALLOCATION_METHOD, "
        "INFRASTRUCTURE_PROCESS, F_QUANTITATIVE_REFERENCE, F_LOCATION, F_PROCESS_DOC, F_DQ_SYSTEM, "
        "DQ_ENTRY, F_EXCHANGE_DQ_SYSTEM, F_SOCIAL_DQ_SYSTEM, LAST_INTERNAL_ID) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_PROCESS_DOCS": (
        "INSERT INTO TBL_PROCESS_DOCS (ID, VALID_FROM, VALID_UNTIL, TIME, GEOGRAPHY, TECHNOLOGY, "
        "INVENTORY_METHOD, MODELING_CONSTANTS, DATA_COMPLETENESS, DATA_SELECTION, DATA_TREATMENT, "
        "SAMPLING_PROCEDURE, DATA_COLLECTION_PERIOD, USE_ADVICE, FLOW_COMPLETENESS, "
        "INTENDED_APPLICATION, PROJECT, F_DATA_GENERATOR, F_DATA_DOCUMENTOR, CREATION_DATE, "
        "PRECEDING_DATASET, F_PUBLICATION, F_DATA_OWNER, COPYRIGHT, ACCESS_RESTRICTIONS) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_EXCHANGES": (
        "INSERT INTO TBL_EXCHANGES (ID, F_OWNER, INTERNAL_ID, F_FLOW, F_UNIT, IS_INPUT, "
        "F_FLOW_PROPERTY_FACTOR, RESULTING_AMOUNT_VALUE, RESULTING_AMOUNT_FORMULA, "
        "AVOIDED_PRODUCT, F_DEFAULT_PROVIDER, DEFAULT_PROVIDER_TYPE, F_LOCATION, DESCRIPTION, "
        "COST_VALUE, "
        "COST_FORMULA, F_CURRENCY, DISTRIBUTION_TYPE, PARAMETER1_VALUE, PARAMETER2_VALUE, "
        "PARAMETER3_VALUE, DQ_ENTRY, BASE_UNCERTAINTY) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_REVIEWS": (
        "INSERT INTO TBL_REVIEWS (ID, F_OWNER, REVIEW_TYPE, SCOPES, DETAILS, ASSESSMENT, F_REPORT) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_SOURCE_LINKS": "INSERT INTO TBL_SOURCE_LINKS (F_OWNER, F_SOURCE) VALUES (?, ?)",
    "TBL_ACTOR_LINKS": "INSERT INTO TBL_ACTOR_LINKS (F_OWNER, F_ACTOR) VALUES (?, ?)",
    "TBL_IMPACT_METHODS": (
        "INSERT INTO TBL_IMPACT_METHODS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, CODE, F_SOURCE) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_IMPACT_CATEGORIES": (
        "INSERT INTO TBL_IMPACT_CATEGORIES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, "
        "TAGS, LIBRARY, DESCRIPTION, OTHER_PROPERTIES, DIRECTION, CODE, REFERENCE_UNIT, F_SOURCE) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_IMPACT_LINKS": (
        "INSERT INTO TBL_IMPACT_LINKS (F_IMPACT_METHOD, F_IMPACT_CATEGORY) VALUES (?, ?)"
    ),
    "TBL_IMPACT_FACTORS": (
        "INSERT INTO TBL_IMPACT_FACTORS (ID, F_IMPACT_CATEGORY, F_FLOW, F_FLOW_PROPERTY_FACTOR, "
        "F_UNIT, VALUE, FORMULA, F_LOCATION, DISTRIBUTION_TYPE, PARAMETER1_VALUE, "
        "PARAMETER2_VALUE, PARAMETER3_VALUE) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_NW_SETS": (
        "INSERT INTO TBL_NW_SETS (ID, REF_ID, NAME, DESCRIPTION, F_IMPACT_METHOD, "
        "WEIGHTED_SCORE_UNIT) VALUES (?, ?, ?, ?, ?, ?)"
    ),
    "TBL_NW_FACTORS": (
        "INSERT INTO TBL_NW_FACTORS (ID, WEIGHTING_FACTOR, NORMALISATION_FACTOR, "
        "F_IMPACT_CATEGORY, F_NW_SET) VALUES (?, ?, ?, ?, ?)"
    ),
    "TBL_PARAMETERS": (
        "INSERT INTO TBL_PARAMETERS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, IS_INPUT_PARAM, F_OWNER, SCOPE, VALUE, FORMULA, "
        "DISTRIBUTION_TYPE, PARAMETER1_VALUE, PARAMETER2_VALUE, PARAMETER3_VALUE) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_DQ_SYSTEMS": (
        "INSERT INTO TBL_DQ_SYSTEMS (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, F_SOURCE, HAS_UNCERTAINTIES) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_DQ_INDICATORS": (
        "INSERT INTO TBL_DQ_INDICATORS (ID, NAME, POSITION, F_DQ_SYSTEM) VALUES (?, ?, ?, ?)"
    ),
    "TBL_DQ_SCORES": (
        "INSERT INTO TBL_DQ_SCORES (ID, POSITION, DESCRIPTION, LABEL, UNCERTAINTY, F_DQ_INDICATOR) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    ),
    "TBL_CURRENCIES": (
        "INSERT INTO TBL_CURRENCIES (ID, REF_ID, NAME, VERSION, LAST_CHANGE, F_CATEGORY, TAGS, "
        "LIBRARY, DESCRIPTION, OTHER_PROPERTIES, CODE, CONVERSION_FACTOR, F_REFERENCE_CURRENCY) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ),
    "TBL_MAPPING_FILES": (
        "INSERT INTO TBL_MAPPING_FILES (ID, FILE_NAME, CONTENT) VALUES (?, ?, ?)"
    ),
}

ROWS: dict[str, tuple[dict[str, Value], ...]] = {
    "TBL_CATEGORIES": (
        {
            "ID": 1,
            "REF_ID": _ref(1),
            "NAME": "Energy",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_000,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "Energy carriers.",
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "PROCESS",
        },
        {
            "ID": 2,
            "REF_ID": _ref(2),
            "NAME": "Electricity",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 1,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "PROCESS",
        },
        {
            "ID": 3,
            "REF_ID": _ref(3),
            "NAME": "Grid",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 2,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "PROCESS",
        },
        {
            "ID": 4,
            "REF_ID": _ref(4),
            "NAME": "Resources",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "FLOW",
        },
        {
            "ID": 5,
            "REF_ID": _ref(5),
            "NAME": "Renewable",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 4,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "FLOW",
        },
        {
            "ID": 6,
            "REF_ID": _ref(6),
            "NAME": "Geography",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "LOCATION",
        },
        {
            "ID": 7,
            "REF_ID": _ref(7),
            "NAME": "Quantities",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "FLOW_PROPERTY",
        },
        {
            "ID": 8,
            "REF_ID": _ref(8),
            "NAME": "Units",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "UNIT_GROUP",
        },
        {
            "ID": 9,
            "REF_ID": _ref(9),
            "NAME": "Methods",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "IMPACT_METHOD",
        },
        {
            "ID": 10,
            "REF_ID": _ref(10),
            "NAME": "Climate change",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "IMPACT_CATEGORY",
        },
        {
            "ID": 11,
            "REF_ID": _ref(11),
            "NAME": "Currencies",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "CURRENCY",
        },
        {
            "ID": 12,
            "REF_ID": _ref(12),
            "NAME": "Parameters",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "MODEL_TYPE": "PARAMETER",
        },
    ),
    "TBL_ACTORS": (
        {
            "ID": 1,
            "REF_ID": _ref(21),
            "NAME": "Ana Soto",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_001,
            "F_CATEGORY": None,
            "TAGS": "author",
            "LIBRARY": None,
            "DESCRIPTION": "Data generator.",
            "OTHER_PROPERTIES": None,
            "TELEFAX": "+56 2 2000 0001",
            "WEBSITE": "https://example.org/ana",
            "ADDRESS": "Av. Siempre Viva 742",
            "ZIP_CODE": "8320000",
            "EMAIL": "ana@example.org",
            "TELEPHONE": "+56 2 2000 0002",
            "COUNTRY": "CL",
            "CITY": "Santiago",
        },
        {
            "ID": 2,
            "REF_ID": _ref(22),
            "NAME": "Bruno Diaz",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "TELEFAX": None,
            "WEBSITE": "https://example.org/bruno",
            "ADDRESS": None,
            "ZIP_CODE": None,
            "EMAIL": "bruno@example.org",
            "TELEPHONE": None,
            "COUNTRY": "CL",
            "CITY": "Valparaiso",
        },
    ),
    "TBL_LOCATIONS": (
        {
            "ID": 1,
            "REF_ID": _ref(31),
            "NAME": "Chile",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_002,
            "F_CATEGORY": 6,
            "TAGS": "south america",
            "LIBRARY": None,
            "DESCRIPTION": "Country in South America.",
            "OTHER_PROPERTIES": b"openlca:other-props:0001",
            "LONGITUDE": -70.6,
            "LATITUDE": -33.4,
            "CODE": "CL",
            "GEODATA": _polygon_geodata([CL_RING]),
        },
        {
            "ID": 2,
            "REF_ID": _ref(32),
            "NAME": "Rest of World",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 6,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "",
            "OTHER_PROPERTIES": None,
            "LONGITUDE": None,
            "LATITUDE": None,
            "CODE": "RoW",
            "GEODATA": None,
        },
        {
            "ID": 3,
            "REF_ID": _ref(33),
            "NAME": "Zero\x00Width \U0001f600",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 6,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "LONGITUDE": None,
            "LATITUDE": None,
            "CODE": "ZZ",
            "GEODATA": None,
        },
        {
            "ID": 4,
            "REF_ID": _ref(34),
            "NAME": "Point Land",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 6,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "LONGITUDE": 8.0,
            "LATITUDE": 47.0,
            "CODE": "PT",
            "GEODATA": _point_geodata(x=PT_POINT[0], y=PT_POINT[1]),
        },
    ),
    "TBL_SOURCES": (
        {
            "ID": 1,
            "REF_ID": _ref(41),
            "NAME": "Hydropower report",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": "report;hydro",
            "LIBRARY": None,
            "DESCRIPTION": "A report on run-of-river plants.",
            "OTHER_PROPERTIES": None,
            "SOURCE_YEAR": 2021,
            "TEXT_REFERENCE": "Soto, A. (2021): Hydropower in Chile. Santiago.",
            "URL": "https://example.org/hydro.pdf",
            "EXTERNAL_FILE": None,
        },
        {
            "ID": 2,
            "REF_ID": _ref(42),
            "NAME": "Superseded source",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "SOURCE_YEAR": 2010,
            "TEXT_REFERENCE": None,
            "URL": None,
            "EXTERNAL_FILE": None,
        },
        {
            "ID": 3,
            "REF_ID": _ref(43),
            "NAME": "Withdrawn source",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "SOURCE_YEAR": 2012,
            "TEXT_REFERENCE": None,
            "URL": None,
            "EXTERNAL_FILE": None,
        },
    ),
    "TBL_UNITS": (
        {
            "ID": 1,
            "REF_ID": _ref(51),
            "NAME": "MJ",
            "DESCRIPTION": "Megajoule",
            "CONVERSION_FACTOR": 1.0,
            "SYNONYMS": None,
            "F_UNIT_GROUP": 1,
        },
        {
            "ID": 2,
            "REF_ID": _ref(52),
            "NAME": "kWh",
            "DESCRIPTION": "Kilowatt hour",
            "CONVERSION_FACTOR": 3.6,
            "SYNONYMS": "kilowatt hour;kW h",
            "F_UNIT_GROUP": 1,
        },
        {
            "ID": 3,
            "REF_ID": _ref(53),
            "NAME": "kg",
            "DESCRIPTION": "Kilogram",
            "CONVERSION_FACTOR": 1.0,
            "SYNONYMS": None,
            "F_UNIT_GROUP": 2,
        },
        {
            "ID": 4,
            "REF_ID": _ref(54),
            "NAME": "t",
            "DESCRIPTION": "Tonne",
            "CONVERSION_FACTOR": 1000.0,
            "SYNONYMS": "tonne;metric ton",
            "F_UNIT_GROUP": 2,
        },
    ),
    "TBL_UNIT_GROUPS": (
        {
            "ID": 1,
            "REF_ID": _ref(61),
            "NAME": "Units of energy",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 8,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "Energy units.",
            "OTHER_PROPERTIES": None,
            "F_REFERENCE_UNIT": 1,
            "F_DEFAULT_FLOW_PROPERTY": 1,
        },
        {
            "ID": 2,
            "REF_ID": _ref(62),
            "NAME": "Units of mass",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 8,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "F_REFERENCE_UNIT": 3,
            "F_DEFAULT_FLOW_PROPERTY": 3,
        },
    ),
    "TBL_FLOW_PROPERTIES": (
        {
            "ID": 1,
            "REF_ID": _ref(71),
            "NAME": "Energy",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_003,
            "F_CATEGORY": 7,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "Energy content.",
            "OTHER_PROPERTIES": None,
            "FLOW_PROPERTY_TYPE": "1",
            "F_UNIT_GROUP": 1,
        },
        {
            "ID": 2,
            "REF_ID": _ref(72),
            "NAME": "Market value",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 7,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "FLOW_PROPERTY_TYPE": "0",
            "F_UNIT_GROUP": None,
        },
        {
            "ID": 3,
            "REF_ID": _ref(73),
            "NAME": "Mass",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 7,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "FLOW_PROPERTY_TYPE": "1",
            "F_UNIT_GROUP": 2,
        },
    ),
    "TBL_FLOWS": (
        {
            "ID": 1,
            "REF_ID": _ref(81),
            "NAME": "electricity, high voltage",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_004,
            "F_CATEGORY": 5,
            "TAGS": "electricity;grid",
            "LIBRARY": None,
            "DESCRIPTION": "Electricity delivered to the grid.",
            "OTHER_PROPERTIES": None,
            "SYNONYMS": LONG_SYNONYMS,
            "FLOW_TYPE": "PRODUCT_FLOW",
            "INFRASTRUCTURE_FLOW": 0,
            "CAS_NUMBER": None,
            "FORMULA": None,
            "F_REFERENCE_FLOW_PROPERTY": 1,
            "F_LOCATION": 1,
        },
        {
            "ID": 2,
            "REF_ID": _ref(82),
            "NAME": "water, river",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 4,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "SYNONYMS": None,
            "FLOW_TYPE": "ELEMENTARY_FLOW",
            "INFRASTRUCTURE_FLOW": 0,
            "CAS_NUMBER": "7732-18-5",
            "FORMULA": "H2O",
            "F_REFERENCE_FLOW_PROPERTY": 3,
            "F_LOCATION": None,
        },
    ),
    "TBL_FLOW_PROPERTY_FACTORS": (
        {"ID": 1, "CONVERSION_FACTOR": 1.0, "F_FLOW": 1, "F_FLOW_PROPERTY": 1},
        {"ID": 2, "CONVERSION_FACTOR": 1.0, "F_FLOW": 2, "F_FLOW_PROPERTY": 3},
    ),
    "TBL_PROCESSES": (
        {
            "ID": 1,
            "REF_ID": _ref(91),
            "NAME": "electricity production, hydro",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_005,
            "F_CATEGORY": 3,
            "TAGS": "hydro;electricity",
            "LIBRARY": None,
            "DESCRIPTION": "Run-of-river plant.",
            "OTHER_PROPERTIES": None,
            "PROCESS_TYPE": "UNIT_PROCESS",
            "DEFAULT_ALLOCATION_METHOD": None,
            "INFRASTRUCTURE_PROCESS": 0,
            "F_QUANTITATIVE_REFERENCE": 1,
            "F_LOCATION": 1,
            "F_PROCESS_DOC": 1,
            "F_DQ_SYSTEM": 1,
            "DQ_ENTRY": None,
            "F_EXCHANGE_DQ_SYSTEM": 1,
            "F_SOCIAL_DQ_SYSTEM": None,
            "LAST_INTERNAL_ID": 2,
        },
        {
            "ID": 2,
            "REF_ID": _ref(92),
            "NAME": "electricity supply, low voltage",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 2,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "PROCESS_TYPE": "LCI_RESULT",
            "DEFAULT_ALLOCATION_METHOD": None,
            "INFRASTRUCTURE_PROCESS": 1,
            "F_QUANTITATIVE_REFERENCE": 3,
            "F_LOCATION": 2,
            "F_PROCESS_DOC": 2,
            "F_DQ_SYSTEM": None,
            "DQ_ENTRY": None,
            "F_EXCHANGE_DQ_SYSTEM": None,
            "F_SOCIAL_DQ_SYSTEM": None,
            "LAST_INTERNAL_ID": 2,
        },
    ),
    "TBL_PROCESS_DOCS": (
        {
            "ID": 1,
            "VALID_FROM": datetime.date(2020, 1, 1),
            "VALID_UNTIL": datetime.date(2025, 12, 31),
            "TIME": None,
            "GEOGRAPHY": "CL",
            "TECHNOLOGY": LONG_TECHNOLOGY,
            "INVENTORY_METHOD": None,
            "MODELING_CONSTANTS": None,
            "DATA_COMPLETENESS": "",
            "DATA_SELECTION": None,
            "DATA_TREATMENT": None,
            "SAMPLING_PROCEDURE": None,
            "DATA_COLLECTION_PERIOD": None,
            "USE_ADVICE": None,
            "FLOW_COMPLETENESS": None,
            "INTENDED_APPLICATION": "Policy support",
            "PROJECT": None,
            "F_DATA_GENERATOR": 1,
            "F_DATA_DOCUMENTOR": 2,
            "CREATION_DATE": datetime.datetime(2024, 5, 6, 7, 8, 9),
            "PRECEDING_DATASET": None,
            "F_PUBLICATION": 1,
            "F_DATA_OWNER": None,
            "COPYRIGHT": 1,
            "ACCESS_RESTRICTIONS": None,
        },
        {
            "ID": 2,
            "VALID_FROM": None,
            "VALID_UNTIL": None,
            "TIME": OVERFLOW_TIME,
            "GEOGRAPHY": OVERFLOW_GEOGRAPHY,
            "TECHNOLOGY": OVERFLOW_TECHNOLOGY,
            "INVENTORY_METHOD": OVERFLOW_INVENTORY,
            "MODELING_CONSTANTS": OVERFLOW_CONSTANTS,
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
            "PRECEDING_DATASET": "dataset-v1",
            "F_PUBLICATION": None,
            "F_DATA_OWNER": None,
            "COPYRIGHT": 0,
            "ACCESS_RESTRICTIONS": None,
        },
    ),
    "TBL_EXCHANGES": (
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
        },
        {
            "ID": 2,
            "F_OWNER": 1,
            "INTERNAL_ID": 2,
            "F_FLOW": 2,
            "F_UNIT": 3,
            "IS_INPUT": 1,
            "F_FLOW_PROPERTY_FACTOR": 2,
            "RESULTING_AMOUNT_VALUE": 0.5,
            "RESULTING_AMOUNT_FORMULA": "0.5",
            "AVOIDED_PRODUCT": 0,
            "F_DEFAULT_PROVIDER": 0,
            "DEFAULT_PROVIDER_TYPE": 0,
            "F_LOCATION": None,
            "DESCRIPTION": "River water input",
            "COST_VALUE": None,
            "COST_FORMULA": None,
            "F_CURRENCY": None,
            "DISTRIBUTION_TYPE": 1,
            "PARAMETER1_VALUE": 0.5,
            "PARAMETER2_VALUE": 2.0,
            "PARAMETER3_VALUE": 0.0,
            "DQ_ENTRY": "1;2;3",
            "BASE_UNCERTAINTY": 0.1,
        },
        {
            "ID": 3,
            "F_OWNER": 2,
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
        },
        {
            "ID": 4,
            "F_OWNER": 2,
            "INTERNAL_ID": 2,
            "F_FLOW": 1,
            "F_UNIT": 2,
            "IS_INPUT": 1,
            "F_FLOW_PROPERTY_FACTOR": 1,
            "RESULTING_AMOUNT_VALUE": 0.9,
            "RESULTING_AMOUNT_FORMULA": None,
            "AVOIDED_PRODUCT": 0,
            "F_DEFAULT_PROVIDER": 1,
            "DEFAULT_PROVIDER_TYPE": 1,
            "F_LOCATION": None,
            "DESCRIPTION": None,
            "COST_VALUE": 12.5,
            "COST_FORMULA": None,
            "F_CURRENCY": 1,
            "DISTRIBUTION_TYPE": None,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
            "DQ_ENTRY": None,
            "BASE_UNCERTAINTY": None,
        },
    ),
    "TBL_REVIEWS": (
        {
            "ID": 1,
            "F_OWNER": 1,
            "REVIEW_TYPE": None,
            "SCOPES": None,
            "DETAILS": "Reviewed by a third party.",
            "ASSESSMENT": None,
            "F_REPORT": 1,
        },
    ),
    "TBL_SOURCE_LINKS": ({"F_OWNER": 1, "F_SOURCE": 1},),
    "TBL_ACTOR_LINKS": ({"F_OWNER": 1, "F_ACTOR": 1}, {"F_OWNER": 1, "F_ACTOR": 2}),
    "TBL_IMPACT_METHODS": (
        {
            "ID": 1,
            "REF_ID": _ref(101),
            "NAME": "Climate method",
            "VERSION": 22,
            "LAST_CHANGE": 1_700_000_000_006,
            "F_CATEGORY": 9,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "One method, two categories.",
            "OTHER_PROPERTIES": None,
            "CODE": "CM-1",
            "F_SOURCE": 1,
        },
    ),
    "TBL_IMPACT_CATEGORIES": (
        {
            "ID": 1,
            "REF_ID": _ref(111),
            "NAME": "Climate change",
            "VERSION": 12_884_901_975,
            "LAST_CHANGE": 1_700_000_000_007,
            "F_CATEGORY": 10,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "GWP over 100 years.",
            "OTHER_PROPERTIES": None,
            "DIRECTION": "OUTPUT",
            "CODE": "GWP100",
            "REFERENCE_UNIT": "kg CO2 eq",
            "F_SOURCE": None,
        },
        {
            "ID": 2,
            "REF_ID": _ref(112),
            "NAME": "Water use",
            "VERSION": 0,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 10,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "DIRECTION": "INPUT",
            "CODE": "WU",
            "REFERENCE_UNIT": "m3",
            "F_SOURCE": 1,
        },
    ),
    "TBL_IMPACT_LINKS": (
        {"F_IMPACT_METHOD": 1, "F_IMPACT_CATEGORY": 1},
        {"F_IMPACT_METHOD": 1, "F_IMPACT_CATEGORY": 2},
    ),
    "TBL_IMPACT_FACTORS": (
        {
            "ID": 1,
            "F_IMPACT_CATEGORY": 1,
            "F_FLOW": 1,
            "F_FLOW_PROPERTY_FACTOR": 1,
            "F_UNIT": 1,
            "VALUE": 0.5,
            "FORMULA": "value * 1.0",
            "F_LOCATION": None,
            "DISTRIBUTION_TYPE": 0,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
        },
        {
            "ID": 2,
            "F_IMPACT_CATEGORY": 1,
            "F_FLOW": 2,
            "F_FLOW_PROPERTY_FACTOR": 2,
            "F_UNIT": 3,
            "VALUE": 1.2,
            "FORMULA": None,
            "F_LOCATION": 1,
            "DISTRIBUTION_TYPE": 1,
            "PARAMETER1_VALUE": 1.2,
            "PARAMETER2_VALUE": 1.5,
            "PARAMETER3_VALUE": 0.0,
        },
        {
            "ID": 3,
            "F_IMPACT_CATEGORY": 2,
            "F_FLOW": 2,
            "F_FLOW_PROPERTY_FACTOR": 2,
            "F_UNIT": 3,
            "VALUE": 0.0,
            "FORMULA": "gwp_scale * 0.5",
            "F_LOCATION": None,
            "DISTRIBUTION_TYPE": None,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
        },
        {
            "ID": 4,
            "F_IMPACT_CATEGORY": 1,
            "F_FLOW": 2,
            "F_FLOW_PROPERTY_FACTOR": 2,
            "F_UNIT": 3,
            "VALUE": 0.8,
            "FORMULA": None,
            "F_LOCATION": None,
            "DISTRIBUTION_TYPE": 0,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
        },
    ),
    "TBL_NW_SETS": (
        {
            "ID": 1,
            "REF_ID": _ref(121),
            "NAME": "Points",
            "DESCRIPTION": "Normalisation and weighting.",
            "F_IMPACT_METHOD": 1,
            "WEIGHTED_SCORE_UNIT": "Pt",
        },
    ),
    "TBL_NW_FACTORS": (
        {
            "ID": 1,
            "WEIGHTING_FACTOR": 1.0,
            "NORMALISATION_FACTOR": 50_000.0,
            "F_IMPACT_CATEGORY": 1,
            "F_NW_SET": 1,
        },
        {
            "ID": 2,
            "WEIGHTING_FACTOR": 0.5,
            "NORMALISATION_FACTOR": 100.0,
            "F_IMPACT_CATEGORY": 2,
            "F_NW_SET": 1,
        },
    ),
    "TBL_PARAMETERS": (
        {
            "ID": 1,
            "REF_ID": _ref(131),
            "NAME": "global_factor",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 12,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": "A global parameter.",
            "OTHER_PROPERTIES": None,
            "IS_INPUT_PARAM": 0,
            "F_OWNER": None,
            "SCOPE": "GLOBAL",
            "VALUE": 2.5,
            "FORMULA": None,
            "DISTRIBUTION_TYPE": None,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
        },
        {
            "ID": 2,
            "REF_ID": _ref(132),
            "NAME": "gwp_scale",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 12,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "IS_INPUT_PARAM": 0,
            "F_OWNER": 1,
            "SCOPE": "IMPACT",
            "VALUE": 1.0,
            "FORMULA": "global_factor * 2",
            "DISTRIBUTION_TYPE": None,
            "PARAMETER1_VALUE": None,
            "PARAMETER2_VALUE": None,
            "PARAMETER3_VALUE": None,
        },
    ),
    "TBL_DQ_SYSTEMS": (
        {
            "ID": 1,
            "REF_ID": _ref(141),
            "NAME": "Pedigree matrix",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": None,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "F_SOURCE": 1,
            "HAS_UNCERTAINTIES": 1,
        },
    ),
    "TBL_DQ_INDICATORS": (
        {"ID": 1, "NAME": "Reliability", "POSITION": 1, "F_DQ_SYSTEM": 1},
        {"ID": 2, "NAME": "Completeness", "POSITION": 2, "F_DQ_SYSTEM": 1},
    ),
    "TBL_DQ_SCORES": (
        {
            "ID": 1,
            "POSITION": 1,
            "DESCRIPTION": "Verified data from measurements",
            "LABEL": "1",
            "UNCERTAINTY": 0.0,
            "F_DQ_INDICATOR": 1,
        },
        {
            "ID": 2,
            "POSITION": 5,
            "DESCRIPTION": "Unverified data from a non-qualified source",
            "LABEL": "5",
            "UNCERTAINTY": 0.05,
            "F_DQ_INDICATOR": 1,
        },
        {
            "ID": 3,
            "POSITION": 1,
            "DESCRIPTION": "Representative data from all sites",
            "LABEL": "1",
            "UNCERTAINTY": 0.0,
            "F_DQ_INDICATOR": 2,
        },
    ),
    "TBL_CURRENCIES": (
        {
            "ID": 1,
            "REF_ID": _ref(151),
            "NAME": "Euro",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 11,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "CODE": "EUR",
            "CONVERSION_FACTOR": 1.0,
            "F_REFERENCE_CURRENCY": None,
        },
        {
            "ID": 2,
            "REF_ID": _ref(152),
            "NAME": "US Dollar",
            "VERSION": 22,
            "LAST_CHANGE": 0,
            "F_CATEGORY": 11,
            "TAGS": None,
            "LIBRARY": None,
            "DESCRIPTION": None,
            "OTHER_PROPERTIES": None,
            "CODE": "USD",
            "CONVERSION_FACTOR": 1.1,
            "F_REFERENCE_CURRENCY": 1,
        },
    ),
    "TBL_MAPPING_FILES": ({"ID": 1, "FILE_NAME": "EcoSpold1_Import.csv", "CONTENT": LONG_CSV},),
}

FILLED_TEMPLATE: dict[str, Value] = {
    "F_IMPACT_CATEGORY": 1,
    "F_FLOW": 1,
    "F_FLOW_PROPERTY_FACTOR": 1,
    "F_UNIT": 1,
    "VALUE": 0.25,
    "FORMULA": ("0.25 * base_amount * conversion_factor / 1.0; " * 25)[:1_000],
    "F_LOCATION": None,
    "DISTRIBUTION_TYPE": 0,
    "PARAMETER1_VALUE": None,
    "PARAMETER2_VALUE": None,
    "PARAMETER3_VALUE": None,
}

TYPES_INSERTS: dict[str, str] = {
    "TYPES": "INSERT INTO TYPES (ID, CODE, FLAG) VALUES (?, ?, ?)",
}

TYPES_ROWS: dict[str, tuple[dict[str, Value], ...]] = {
    "TYPES": (
        {"ID": 1, "CODE": "alpha-01", "FLAG": True},
        {"ID": 2, "CODE": "beta-002", "FLAG": False},
    ),
}

ROWS_THE_SCHEMA_WRITES: dict[str, tuple[dict[str, Value], ...]] = {
    "SEQUENCE": ({"SEQ_NAME": "entity_seq", "SEQ_COUNT": 0},),
    "OPENLCA_VERSION": ({"VERSION": 15},),
}

DELETED: dict[str, tuple[dict[str, object], ...]] = {
    "TBL_SOURCES": (
        {"count": 1, "template": dict(ROWS["TBL_SOURCES"][1])},
        {"count": 1, "template": dict(ROWS["TBL_SOURCES"][2])},
    ),
    "TBL_IMPACT_FACTORS": (
        {"count": FILLED_COUNT, "template": {"ID": FILLED_FIRST_ID, **FILLED_TEMPLATE}},
    ),
}


def _start_jvm(*, java: Path, derby: Path, out: Path) -> None:
    """Start the JVM the Derby jars run on, with its log beside the databases it writes."""
    jvm = java.resolve().parent.parent / "lib" / "server" / "libjvm.so"
    if not jvm.is_file():
        raise FileNotFoundError(f"{java} has no lib/server/libjvm.so beside it")
    jpype.startJVM(
        str(jvm),
        f"-Dderby.system.home={out}",
        f"-Dderby.stream.error.file={out / 'derby.log'}",
        classpath=[str(jar) for jar in sorted(derby.glob("derby*.jar"))],
        convertStrings=True,
    )


def _connect(url: str) -> Connection:
    """Open a database the URL names, with the credentials Derby expects on an embedded run."""
    from java.sql import DriverManager

    return DriverManager.getConnection(url, "", "")


def _shut_down(path: Path) -> None:
    """Shut a database down; Derby answers a clean shutdown with SQLState 08006."""
    try:
        _connect(f"jdbc:derby:{path};shutdown=true")
    except jpype.JException as error:
        if error.getSQLState() != DERBY_SHUTDOWN_SQLSTATE:
            raise


def _statements(schema: Path) -> list[str]:
    """The schema's statements, its whole-line comments dropped."""
    lines = [line for line in schema.read_text().splitlines() if not line.strip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def _create(*, path: Path, schema: Path) -> Connection:
    connection = _connect(f"jdbc:derby:{path};create=true")
    statement = connection.createStatement()
    for sql in _statements(schema):
        statement.executeUpdate(sql)
    statement.close()
    connection.commit()
    return connection


def _prepared(
    connection: Connection, *, table: str, columns: tuple[str, ...], inserts: dict[str, str]
) -> PreparedStatement:
    """A prepared insert of `table`, its placeholders checked against the row's columns."""
    insert = inserts[table]
    if insert.count("?") != len(columns) or any(column not in insert for column in columns):
        raise ValueError(f"{table}: the insert statement does not place {columns}")
    return connection.prepareStatement(insert)


def _bind(statement: PreparedStatement, index: int, value: Value) -> None:
    """Bind one row value to its placeholder, by the Python type the column's value holds."""
    if value is None:
        statement.setObject(index, None)
    elif isinstance(value, bool):
        statement.setBoolean(index, value)
    elif isinstance(value, int):
        statement.setLong(index, value)
    elif isinstance(value, float):
        statement.setDouble(index, value)
    elif isinstance(value, str):
        statement.setString(index, value)
    elif isinstance(value, bytes):
        statement.setBytes(index, value)
    elif isinstance(value, datetime.datetime):
        from java.sql import Timestamp

        statement.setTimestamp(index, Timestamp.valueOf(value.isoformat(sep=" ")))
    elif isinstance(value, datetime.date):
        from java.sql import Date

        statement.setDate(index, Date.valueOf(value.isoformat()))
    else:
        raise TypeError(f"{type(value).__name__} is not a value a fixture column holds")


def _insert(connection: Connection, *, table: str, rows: Sequence[dict[str, Value]]) -> None:
    """Insert the rows of one table, its statement taken from `INSERTS`."""
    columns = tuple(rows[0])
    statement = _prepared(connection, table=table, columns=columns, inserts=INSERTS)
    for row in rows:
        for index, column in enumerate(columns, start=1):
            _bind(statement, index, row[column])
        statement.executeUpdate()
    statement.close()
    connection.commit()


def _fill(
    connection: Connection, *, table: str, first_id: int, template: dict[str, Value], count: int
) -> None:
    """Insert `count` rows that differ only in ID, so `rows.json` records a template and a count."""
    columns = ("ID", *template)
    statement = _prepared(connection, table=table, columns=columns, inserts=INSERTS)
    for offset in range(count):
        statement.setLong(1, first_id + offset)
        for index, column in enumerate(template, start=2):
            _bind(statement, index, template[column])
        statement.executeUpdate()
    statement.close()
    connection.commit()


def _delete(connection: Connection, sql: str) -> None:
    """Run one DELETE this script writes literally."""
    statement = connection.createStatement()
    statement.executeUpdate(sql)
    statement.close()
    connection.commit()


def _zip(database: Path, destination: Path) -> None:
    """Zip a database as openLCA zips a backup: the directory's members at the archive's root."""
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(database.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(database).as_posix())


def _json_value(value: Value) -> object:
    """One row value as `rows.json` holds it: dates as ISO strings, BLOBs as hex."""
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep="T")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _json_rows(rows: Sequence[dict[str, Value]]) -> list[dict[str, object]]:
    return [{column: _json_value(value) for column, value in row.items()} for row in rows]


def _recorded_tables() -> dict[str, list[dict[str, object]]]:
    """The fixture's live rows by table, the rows this run deletes after inserting left out."""
    rows = {**ROWS, **ROWS_THE_SCHEMA_WRITES}
    found: dict[str, list[dict[str, object]]] = {}
    for table, table_rows in rows.items():
        deleted = {entry["template"].get("ID") for entry in DELETED.get(table, ())}
        found[table] = _json_rows([row for row in table_rows if row.get("ID") not in deleted])
    return found


def _write_openlca(*, out: Path, schema: Path) -> dict[str, object]:
    """Create, fill, empty and zip the openLCA-schema database, and return what it records."""
    path = out / "openlca"
    if str(FILLED_FIRST_ID) not in DELETE_FILLED_FACTORS:
        raise ValueError("the delete statement does not name the ids the fill writes")
    connection = _create(path=path, schema=schema)
    for table, rows in ROWS.items():
        _insert(connection, table=table, rows=rows)
    _fill(
        connection,
        table="TBL_IMPACT_FACTORS",
        first_id=FILLED_FIRST_ID,
        template=FILLED_TEMPLATE,
        count=FILLED_COUNT,
    )
    _delete(connection, DELETE_FILLED_FACTORS)
    _delete(connection, DELETE_THE_SUPERSEDED_SOURCES)
    connection.close()
    _shut_down(path)
    _zip(path, out / "openlca.zip")
    return {"tables": _recorded_tables(), "deleted": DELETED, "geometry": GEOMETRY}


def _write_types(*, out: Path) -> dict[str, object]:
    """Create and zip the database whose one table holds a `CHAR` and a `BOOLEAN` column."""
    path = out / "types"
    connection = _connect(f"jdbc:derby:{path};create=true")
    statement = connection.createStatement()
    statement.executeUpdate(
        "CREATE TABLE TYPES (ID BIGINT NOT NULL, CODE CHAR(8), FLAG BOOLEAN, PRIMARY KEY (ID))"
    )
    statement.close()
    connection.commit()
    columns = tuple(TYPES_ROWS["TYPES"][0])
    prepared = _prepared(connection, table="TYPES", columns=columns, inserts=TYPES_INSERTS)
    for row in TYPES_ROWS["TYPES"]:
        for index, column in enumerate(columns, start=1):
            _bind(prepared, index, row[column])
        prepared.executeUpdate()
    prepared.close()
    connection.commit()
    connection.close()
    _shut_down(path)
    _zip(path, out / "types.zip")
    return {"tables": {table: _json_rows(rows) for table, rows in TYPES_ROWS.items()}}


def _write_encrypted(*, out: Path) -> None:
    """Create and zip a database whose `service.properties` names `data_encryption`."""
    path = out / "encrypted"
    connection = _connect(
        f"jdbc:derby:{path};create=true;dataEncryption=true;bootPassword=zolca-fixture"
        ";derby.storage.logSwitchInterval=131072"
    )
    statement = connection.createStatement()
    statement.executeUpdate(
        "CREATE TABLE TYPES (ID BIGINT NOT NULL, CODE VARCHAR(8), PRIMARY KEY (ID))"
    )
    statement.executeUpdate("INSERT INTO TYPES (ID, CODE) VALUES (1, 'alpha-01')")
    statement.close()
    connection.commit()
    connection.close()
    _shut_down(path)
    _zip(path, out / "encrypted.zip")


def _write_unclean(*, out: Path) -> None:
    """Zip a database while it is open, so its log holds work after its last checkpoint."""
    path = out / "unclean"
    copy = out / "unclean-open"
    connection = _connect(f"jdbc:derby:{path};create=true")
    statement = connection.createStatement()
    statement.executeUpdate(
        "CREATE TABLE TYPES (ID BIGINT NOT NULL, CODE VARCHAR(8), PRIMARY KEY (ID))"
    )
    statement.executeUpdate("INSERT INTO TYPES (ID, CODE) VALUES (1, 'open-01')")
    statement.executeUpdate("CALL SYSCS_UTIL.SYSCS_CHECKPOINT_DATABASE()")
    statement.executeUpdate("INSERT INTO TYPES (ID, CODE) VALUES (2, 'open-02')")
    statement.close()
    connection.commit()
    _copy(path, copy)
    connection.close()
    _shut_down(path)
    _zip(copy, out / "unclean.zip")


def _copy(source: Path, destination: Path) -> None:
    """Copy a database directory file by file, the lock files Derby holds left behind."""
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix != ".lck":
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def main(argv: list[str] | None = None) -> None:
    """Write the four zipped databases and `rows.json` into `--out`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", required=True, type=Path, help="the java executable")
    parser.add_argument("--derby", required=True, type=Path, help="the directory of Derby's jars")
    parser.add_argument("--schema", required=True, type=Path, help="current_schema_derby.sql")
    parser.add_argument("--out", required=True, type=Path, help="the directory to write into")
    arguments = parser.parse_args(argv)
    arguments.out.mkdir(parents=True, exist_ok=True)
    _start_jvm(java=arguments.java, derby=arguments.derby, out=arguments.out)
    fixtures = {
        "databases": {
            "openlca.zip": _write_openlca(out=arguments.out, schema=arguments.schema),
            "types.zip": _write_types(out=arguments.out),
        }
    }
    _write_encrypted(out=arguments.out)
    _write_unclean(out=arguments.out)
    jpype.shutdownJVM()
    (arguments.out / "rows.json").write_text(json.dumps(fixtures, indent=2) + "\n")


if __name__ == "__main__":
    main()
