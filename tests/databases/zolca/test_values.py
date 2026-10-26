"""Each SQL type's stored form, and the long values whose chains the fixture carries."""

from __future__ import annotations

import datetime
import struct

import pytest

from ecosemantic.databases.zolca.derby import records, values
from ecosemantic.errors import Invalid, NotSupported
from tests.databases.zolca.fixture import recorded, row_of, value


def test_a_boolean_reads_its_byte() -> None:
    assert values.decode(77, b"\x01", where="BOOLEAN") is True
    assert values.decode(77, b"\x00", where="BOOLEAN") is False


def test_the_four_numbers_read_their_bytes() -> None:
    assert values.decode(84, struct.pack(">q", -(2**63)), where="BIGINT") == -(2**63)
    assert values.decode(80, struct.pack(">i", -7), where="INTEGER") == -7
    assert values.decode(83, struct.pack(">h", -2), where="SMALLINT") == -2
    assert values.decode(79, struct.pack(">d", 0.125), where="DOUBLE") == 0.125


def test_a_value_of_another_width_than_its_type_holds_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.decode(77, b"\x00\x00", where="BOOLEAN")
    with pytest.raises(Invalid):
        values.decode(84, b"\x00\x01", where="BIGINT")


def test_a_char_and_a_varchar_read_a_two_byte_length_and_derbys_text() -> None:
    assert values.decode(78, b"\x00\x03abc", where="CHAR") == "abc"
    assert values.decode(85, b"\x00\x00", where="VARCHAR") == ""


def test_a_date_reads_its_parts() -> None:
    stored = struct.pack(">i", (2020 << 16) | (1 << 8) | 1)
    assert values.decode(298, stored, where="DATE") == datetime.date(2020, 1, 1)


def test_a_date_the_calendar_does_not_hold_is_invalid() -> None:
    stored = struct.pack(">i", (2023 << 16) | (2 << 8) | 30)
    with pytest.raises(Invalid):
        values.decode(298, stored, where="DATE")


def test_a_timestamp_reads_its_date_its_time_and_its_nanos() -> None:
    stored = struct.pack(">i", (2024 << 16) | (5 << 8) | 6)
    stored += struct.pack(">i", (7 << 16) | (8 << 8) | 9)
    stored += struct.pack(">i", 500_000)
    assert values.decode(31, stored, where="TIMESTAMP") == datetime.datetime(
        2024, 5, 6, 7, 8, 9, 500
    )


def test_a_timestamp_of_finer_precision_than_a_microsecond_is_not_supported() -> None:
    stored = struct.pack(">i", (2024 << 16) | (5 << 8) | 6)
    stored += struct.pack(">i", (7 << 16) | (8 << 8) | 9)
    stored += struct.pack(">i", 1_500)
    with pytest.raises(NotSupported):
        values.decode(31, stored, where="TIMESTAMP")


def test_a_timestamp_the_calendar_does_not_hold_is_invalid() -> None:
    stored = struct.pack(">i", (2024 << 16) | (13 << 8) | 6)
    stored += struct.pack(">i", (7 << 16) | (8 << 8) | 9)
    stored += struct.pack(">i", 0)
    with pytest.raises(Invalid):
        values.decode(31, stored, where="TIMESTAMP")


def test_a_character_of_one_byte_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.decode(85, b"\x00", where="VARCHAR")


def test_a_character_of_unknown_length_without_its_marker_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.decode(85, b"\x00\x00abc", where="VARCHAR")


def test_derbys_modified_utf_8_reads_a_nul_a_three_byte_character_and_a_supplementary_one() -> None:
    assert values.modified_utf8(b"C\xc0\x80\xe2\x98\x83\xed\xa0\xbd\xed\xb8\x80") == (
        "C\x00\u2603\U0001f600"
    )
    assert values.modified_utf8(b"") == ""


def test_modified_utf_8_of_a_shape_derby_does_not_write_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.modified_utf8(b"\xf0\x9f\x98\x80")
    with pytest.raises(Invalid):
        values.modified_utf8(b"\xc3x")


def test_a_clob_reads_its_five_byte_header_and_its_text() -> None:
    assert values.decode(447, b"\x00\x00\xf0\x00\x03abc", where="CLOB") == "abc"
    assert values.decode(447, b"\x00\x00\xf0\x00\x00", where="CLOB") == ""


def test_a_clob_of_the_two_byte_header_ends_at_its_marker_or_at_its_count() -> None:
    assert values.decode(447, b"\x00\x00text\xe0\x00\x00", where="CLOB") == "text"
    assert values.decode(447, b"\x00\x04text", where="CLOB") == "text"
    assert values.decode(447, b"\x00\x00\xe0\x00\x00", where="CLOB") == ""


def test_a_clob_whose_header_states_another_count_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.decode(447, b"\x00\x00\xf0\x00\x04abc", where="CLOB")
    with pytest.raises(Invalid):
        values.decode(447, b"\x00\x09text", where="CLOB")


def test_a_clob_header_of_another_format_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        values.decode(447, b"\x00\x00\xf1\x00\x03abc", where="CLOB")


def test_a_blob_reads_each_of_its_length_headers() -> None:
    assert values.decode(443, bytes([0x80 | 3]) + b"abc", where="BLOB") == b"abc"
    assert values.decode(443, b"\xa0" + struct.pack(">H", 300) + bytes(300), where="BLOB") == bytes(
        300
    )
    five = b"\xc0" + struct.pack(">i", 70_000) + bytes(70_000)
    assert values.decode(443, five, where="BLOB") == bytes(70_000)


def test_a_blob_of_the_four_byte_bit_count_reads_its_bytes() -> None:
    assert values.decode(443, struct.pack(">i", 24) + b"abc", where="BLOB") == b"abc"


def test_a_blob_whose_stated_length_is_not_its_bytes_is_invalid() -> None:
    with pytest.raises(Invalid):
        values.decode(443, b"\x80\x03ab", where="BLOB")
    with pytest.raises(Invalid):
        values.decode(443, b"", where="BLOB")


def test_a_blob_length_header_derby_does_not_write_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        values.decode(443, b"\xe0\x00\x00\x01abc", where="BLOB")


def test_a_stored_format_id_the_reader_does_not_know_is_not_supported() -> None:
    with pytest.raises(NotSupported) as raised:
        values.decode(266, b"", where="TBL_ACTORS.NAME")
    assert "TBL_ACTORS.NAME" in str(raised.value)


def test_the_chained_clob_reads_whole_and_equals_the_fixture() -> None:
    container, _, record = row_of(25, holding="Policy support")
    technology = records.row(container, record)[5]

    assert technology.status & records.FIELD_OVERFLOW
    assert (
        value(container, technology, 447, where="TBL_PROCESS_DOCS.TECHNOLOGY")
        == (recorded()["TBL_PROCESS_DOCS"][0]["TECHNOLOGY"])
    )


def test_the_chained_blob_reads_whole_and_equals_the_fixture() -> None:
    container, _, record = row_of(3, holding="EcoSpold1_Import.csv")
    content = records.row(container, record)[2]

    assert content.status & records.FIELD_OVERFLOW
    assert value(container, content, 443, where="TBL_MAPPING_FILES.CONTENT") == bytes.fromhex(
        str(recorded()["TBL_MAPPING_FILES"][0]["CONTENT"])
    )


def test_a_varchar_chained_behind_its_pointer_reads_whole() -> None:
    container, _, record = row_of(17, holding="electricity, high voltage")
    synonyms = records.row(container, record)[10]

    assert synonyms.status & records.FIELD_OVERFLOW
    assert (
        value(container, synonyms, 85, where="TBL_FLOWS.SYNONYMS")
        == (recorded()["TBL_FLOWS"][0]["SYNONYMS"])
    )


def test_an_empty_clob_reads_as_no_characters() -> None:
    container, _, record = row_of(14, holding="Rest of World")
    description = records.row(container, record)[8]

    assert description.data == b"\x00\x00\xf0\x00\x00"
    assert value(container, description, 447, where="TBL_LOCATIONS.DESCRIPTION") == ""


def test_a_blob_under_its_one_byte_header_reads_its_bytes() -> None:
    container, _, record = row_of(14, holding="Chile")
    properties = records.row(container, record)[9]

    assert properties.data is not None and properties.data[0] == 0x80 | 24
    expected = recorded()["TBL_LOCATIONS"][0]["OTHER_PROPERTIES"]
    assert value(container, properties, 443, where="TBL_LOCATIONS.OTHER_PROPERTIES") == (
        bytes.fromhex(str(expected))
    )


def test_a_nul_and_a_supplementary_character_read_back() -> None:
    container, _, record = row_of(14, holding="Width")
    name = records.row(container, record)[2]

    assert name.data is not None and b"\xc0\x80" in name.data
    assert value(container, name, 85, where="TBL_LOCATIONS.NAME") == "Zero\x00Width \U0001f600"


def test_a_date_and_a_timestamp_read_the_fixture() -> None:
    container, _, record = row_of(25, holding="Policy support")
    fields = records.row(container, record)
    expected = recorded()["TBL_PROCESS_DOCS"][0]

    assert value(container, fields[1], 298, where="TBL_PROCESS_DOCS.VALID_FROM") == (
        datetime.date.fromisoformat(str(expected["VALID_FROM"]))
    )
    assert value(container, fields[19], 31, where="TBL_PROCESS_DOCS.CREATION_DATE") == (
        datetime.datetime.fromisoformat(str(expected["CREATION_DATE"]))
    )
    assert value(container, fields[0], 84, where="TBL_PROCESS_DOCS.ID") == expected["ID"]
