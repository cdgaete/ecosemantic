"""openLCA's renderings, references and geometry, read off the fixture's tables and off bytes."""

from __future__ import annotations

import json
import struct

import pytest

from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.databases.zolca.export import geometry, refs, render
from ecosemantic.databases.zolca.export.tables import Tables, foreign
from ecosemantic.errors import Invalid, NotFound, NotSupported
from tests.databases.zolca.fixture import FIXTURES, recorded


def tables() -> Tables:
    return Tables(Database(FIXTURES / "openlca.zip"))


def recorded_geometry(code: str) -> dict[str, object]:
    """The GeoJSON `rows.json` records for one location of the fixture."""
    document = json.loads((FIXTURES / "rows.json").read_text())
    return document["databases"]["openlca.zip"]["geometry"][code]


def varint(value: int) -> bytes:
    """One base-128 varint, the only integer width `proto3` writes."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if not value:
            return bytes(out + bytes([byte]))
        out.append(byte | 0x80)


def field(number: int, payload: bytes) -> bytes:
    """One length-delimited field of the message `geo.proto` defines."""
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def point(x: float, y: float) -> bytes:
    """A `Point`: `x` as field 1 and `y` as field 2, fixed 64-bit doubles."""
    return b"\x09" + struct.pack("<d", x) + b"\x11" + struct.pack("<d", y)


def collected(geometry_payload: bytes) -> bytes:
    """A `FeatureCollection` holding one `Feature` that holds one `Geometry`."""
    return field(1, field(1, geometry_payload))


def test_a_version_renders_its_three_sixteen_bit_fields() -> None:
    assert render.version(0) == "00.00.000"
    assert render.version(22) == "00.00.022"
    assert render.version(3) == "00.00.003"
    assert render.version(0x0001_0002_0003) == "01.02.003"
    assert render.version(12_884_901_975) == "03.00.087"


def test_an_instant_is_none_at_zero_and_carries_three_digits_of_milliseconds() -> None:
    assert render.instant(0) is None
    assert render.instant(1_700_000_000_000) == "2023-11-14T22:13:20Z"
    assert render.instant(1_700_000_000_465) == "2023-11-14T22:13:20.465Z"
    assert render.instant(1) == "1970-01-01T00:00:00.001Z"


def test_tags_are_split_trimmed_and_blank_ones_dropped() -> None:
    assert render.tags("hydro, electricity ,,grid ") == ["hydro", "electricity", "grid"]
    assert render.tags(None) == []
    assert render.tags("") == []


def test_synonyms_are_split_on_semicolons_trimmed_and_blank_ones_dropped() -> None:
    assert render.synonyms("kilowatt hour; kW h ;") == ["kilowatt hour", "kW h"]
    assert render.synonyms(None) == []


def test_a_category_path_walks_the_parent_chain_to_its_root() -> None:
    read = tables()

    assert render.category_path(read, 3) == "Energy/Electricity/Grid"
    assert render.category_path(read, 1) == "Energy"
    assert render.category_path(read, None) is None


class _Rows:
    """A double of `Tables` holding the rows one test gives it."""

    def __init__(self, rows: dict[str, dict[int, dict[str, object]]]) -> None:
        self.rows = rows

    def row(self, table: str, row_id: int) -> dict[str, object]:
        """One row of one table."""
        return self.rows[table][row_id]


def test_a_category_chain_that_returns_to_itself_is_invalid() -> None:
    looping = _Rows(
        {
            "TBL_CATEGORIES": {
                1: {"ID": 1, "NAME": " A ", "F_CATEGORY": 2},
                2: {"ID": 2, "NAME": "B", "F_CATEGORY": 1},
            }
        }
    )

    with pytest.raises(Invalid):
        render.category_path(looping, 1)


def test_the_tables_answer_row_of_a_table_by_its_id() -> None:
    read = tables()

    assert read.row("TBL_PROCESSES", 1)["NAME"] == "electricity production, hydro"
    assert [row["ID"] for row in read.rows("TBL_UNITS")] == [1, 2, 3, 4]
    with pytest.raises(NotFound):
        read.row("TBL_PROCESSES", 99)


def test_the_children_of_a_foreign_key_are_the_rows_that_name_it() -> None:
    read = tables()

    assert read.rows("TBL_UNITS") is read.rows("TBL_UNITS")
    assert read.children("TBL_EXCHANGES", "F_LOCATION", 1) == ()
    assert [row["ID"] for row in read.children("TBL_EXCHANGES", "F_OWNER", 1)] == [1, 2]
    assert [row["ID"] for row in read.children("TBL_EXCHANGES", "F_OWNER", 2)] == [3, 4]
    assert [row["F_SOURCE"] for row in read.children("TBL_SOURCE_LINKS", "F_OWNER", 1)] == [1]
    assert read.children("TBL_EXCHANGES", "F_OWNER", 99) == ()


def test_a_foreign_key_of_null_is_none_and_the_providers_zero_is_none_too() -> None:
    read = tables()
    without_provider = read.row("TBL_EXCHANGES", 1)
    with_provider = read.row("TBL_EXCHANGES", 4)

    assert without_provider["F_DEFAULT_PROVIDER"] == 0
    assert foreign(without_provider, "F_DEFAULT_PROVIDER") is None
    assert foreign(with_provider, "F_DEFAULT_PROVIDER") == 1
    assert foreign(without_provider, "F_LOCATION") is None
    assert foreign(with_provider, "F_CURRENCY") == 1


def test_a_flow_reference_carries_its_type_its_location_code_and_its_reference_unit() -> None:
    read = tables()
    flow = read.row("TBL_FLOWS", 1)

    assert refs.ref(read, "Flow", 1) == {
        "@type": "Flow",
        "@id": flow["REF_ID"],
        "name": "electricity, high voltage",
        "category": "Resources/Renewable",
        "flowType": "PRODUCT_FLOW",
        "refUnit": "MJ",
        "location": "CL",
    }


def test_a_flow_without_a_location_writes_no_location_key() -> None:
    read = tables()
    found = refs.ref(read, "Flow", 2)

    assert found["refUnit"] == "kg"
    assert found["category"] == "Resources"
    assert "location" not in found


def test_a_process_reference_carries_its_type_its_flows_type_and_its_location_code() -> None:
    read = tables()
    process = read.row("TBL_PROCESSES", 1)

    assert refs.ref(read, "Process", 1) == {
        "@type": "Process",
        "@id": process["REF_ID"],
        "name": "electricity production, hydro",
        "category": "Energy/Electricity/Grid",
        "processType": "UNIT_PROCESS",
        "flowType": "PRODUCT_FLOW",
        "location": "CL",
    }


def test_a_flow_property_and_an_impact_category_carry_their_reference_unit() -> None:
    read = tables()

    assert refs.ref(read, "FlowProperty", 1)["refUnit"] == "MJ"
    assert refs.ref(read, "FlowProperty", 3)["refUnit"] == "kg"
    assert refs.ref(read, "ImpactCategory", 1)["refUnit"] == "kg CO2 eq"


def test_a_unit_reference_carries_only_its_type_its_id_and_its_name() -> None:
    read = tables()
    unit = read.row("TBL_UNITS", 1)

    assert refs.ref(read, "Unit", 1) == {"@type": "Unit", "@id": unit["REF_ID"], "name": "MJ"}


def test_a_reference_of_a_row_without_a_category_writes_no_category_key() -> None:
    read = tables()

    assert "category" not in refs.ref(read, "Source", 1)
    assert "category" not in refs.ref(read, "Actor", 1)
    assert refs.ref(read, "Parameter", 1)["category"] == "Parameters"


def test_a_flow_property_without_a_unit_group_carries_no_reference_unit() -> None:
    assert "refUnit" not in refs.ref(tables(), "FlowProperty", 2)


def test_a_process_reference_whose_exchange_is_null_is_not_supported() -> None:
    without_reference = _Rows(
        {
            "TBL_PROCESSES": {
                1: {
                    "ID": 1,
                    "REF_ID": "a",
                    "NAME": "p",
                    "PROCESS_TYPE": "UNIT_PROCESS",
                    "F_QUANTITATIVE_REFERENCE": None,
                    "F_LOCATION": None,
                    "F_CATEGORY": None,
                }
            }
        }
    )

    with pytest.raises(NotSupported):
        refs.ref(without_reference, "Process", 1)


def test_a_reference_whose_location_or_unit_group_is_null_writes_neither() -> None:
    without_location = _Rows(
        {
            "TBL_PROCESSES": {
                1: {
                    "ID": 1,
                    "REF_ID": "a",
                    "NAME": "p",
                    "PROCESS_TYPE": "UNIT_PROCESS",
                    "F_QUANTITATIVE_REFERENCE": 1,
                    "F_LOCATION": None,
                    "F_CATEGORY": None,
                }
            },
            "TBL_EXCHANGES": {1: {"ID": 1, "F_FLOW": 1}},
            "TBL_FLOWS": {1: {"ID": 1, "FLOW_TYPE": "PRODUCT_FLOW"}},
        }
    )
    without_unit_group = _Rows(
        {
            "TBL_FLOWS": {
                1: {
                    "ID": 1,
                    "REF_ID": "f",
                    "NAME": "flow",
                    "FLOW_TYPE": "PRODUCT_FLOW",
                    "F_REFERENCE_FLOW_PROPERTY": 2,
                    "F_LOCATION": None,
                    "F_CATEGORY": None,
                }
            },
            "TBL_FLOW_PROPERTIES": {2: {"ID": 2, "F_UNIT_GROUP": None}},
        }
    )

    assert "location" not in refs.ref(without_location, "Process", 1)
    assert "refUnit" not in refs.ref(without_unit_group, "Flow", 1)


def test_a_foreign_key_or_an_id_that_is_no_number_is_invalid() -> None:
    class _OddRows:
        """A table whose one row's id is no number."""

        def rows(self, table: str) -> tuple[dict[str, object], ...]:
            """The one row."""
            return ({"ID": "one"},)

    with pytest.raises(Invalid):
        foreign({"F_FLOW": "one"}, "F_FLOW")
    with pytest.raises(Invalid):
        Tables(_OddRows()).by_id("TBL_UNITS")


def test_a_reference_to_a_row_the_database_does_not_hold_is_not_found() -> None:
    read = tables()

    with pytest.raises(NotFound):
        refs.ref(read, "Process", 99)
    with pytest.raises(NotSupported):
        refs.ref(read, "Exchange", 1)


def test_a_locations_geometry_is_the_geojson_the_fixture_records() -> None:
    written = {row["CODE"]: row["GEODATA"] for row in recorded()["TBL_LOCATIONS"]}

    for code in ("CL", "PT"):
        blob = written[code]
        assert geometry.geojson(bytes.fromhex(str(blob))) == recorded_geometry(code)


def test_a_point_reads_its_two_doubles() -> None:
    assert geometry.geojson(collected(field(1, point(1.5, -2.5)))) == {
        "type": "Point",
        "coordinates": [1.5, -2.5],
    }


def test_each_geometry_geo_proto_defines_reads_its_coordinates() -> None:
    points = field(1, point(1.0, 2.0)) + field(1, point(3.0, 4.0))
    lines = field(1, points)
    polygons = field(1, lines)
    expected = [[1.0, 2.0], [3.0, 4.0]]

    assert geometry.geojson(collected(field(2, points))) == {
        "type": "MultiPoint",
        "coordinates": expected,
    }
    assert geometry.geojson(collected(field(3, points))) == {
        "type": "LineString",
        "coordinates": expected,
    }
    assert geometry.geojson(collected(field(4, lines))) == {
        "type": "MultiLineString",
        "coordinates": [expected],
    }
    assert geometry.geojson(collected(field(5, lines))) == {
        "type": "Polygon",
        "coordinates": [expected],
    }
    assert geometry.geojson(collected(field(6, polygons))) == {
        "type": "MultiPolygon",
        "coordinates": [[expected]],
    }
    assert geometry.geojson(collected(field(7, field(1, field(1, point(1.0, 2.0)))))) == {
        "type": "GeometryCollection",
        "geometries": [{"type": "Point", "coordinates": [1.0, 2.0]}],
    }


def test_a_geometry_blob_with_no_feature_or_no_geometry_is_none() -> None:
    assert geometry.geojson(b"") is None
    assert geometry.geojson(field(1, field(2, b""))) is None
    assert geometry.geojson(collected(b"")) is None


def test_a_features_properties_are_no_geometry() -> None:
    properties = field(2, b"")
    feature = properties + field(1, field(1, point(1.0, 2.0)))

    assert geometry.geojson(field(1, feature)) == {"type": "Point", "coordinates": [1.0, 2.0]}


def test_a_message_that_ends_inside_a_field_is_invalid() -> None:
    with pytest.raises(Invalid):
        geometry.geojson(b"\x0a\x05ab")
    with pytest.raises(Invalid):
        geometry.geojson(collected(field(1, b"\x09\x00\x00\x00\x00")))
    with pytest.raises(Invalid):
        geometry.geojson(b"\x80")


def test_a_field_or_wire_type_geo_proto_does_not_define_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        geometry.geojson(field(2, b""))
    with pytest.raises(NotSupported):
        geometry.geojson(field(1, field(9, b"")))
    with pytest.raises(NotSupported):
        geometry.geojson(field(1, field(1, b"\x0d\x00\x00\x00\x00")))
