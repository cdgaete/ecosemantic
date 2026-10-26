"""The database a zolca holds: its catalogs' tables, its rows, its log, and what it refuses."""

from __future__ import annotations

import datetime
import struct
import zipfile
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from ecosemantic.databases.zolca.derby import catalog, log, pages, records
from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.errors import Invalid, NotSupported
from tests.databases.zolca.fixture import FIXTURES, containers, recorded

CHECKPOINT = b"\x00\x81\x41\x00\x00\x93\x40\x01\x36\xe6\x01\x07"
CHECKSUM = b"\x00\x81\x49\x00\x00\x00\x01\xc5"
END_XACT = b"\x00\x81\x41\x12\x00\x93\x40\x01\x36\xe6\x00\x66"
OTHER_END_XACT = b"\x00\x81\x41\x12\x00\x93\x40\x01\x36\xe7\x00\x66"
BEGIN_XACT = b"\x00\x81\x41\x01\x00\x93\x40\x01\x36\xe7\x00\xa9"


def control(*, file: int, position: int) -> bytes:
    """A `log.ctrl` naming one checkpoint instant, its CRC32 written as `LogToFile` writes it."""
    body = struct.pack(">iiqiii", 128, 9, (file << 32) | position, 10, 17, 1_913_217)
    body += b"\x00" * 4 + struct.pack(">q", 0)
    return body + struct.pack(">q", zlib.crc32(body))


def a_log(*bodies: bytes) -> dict[str, bytes]:
    """A log whose file frames each record body at its own position, and its two control files."""
    at = 24
    frames = b""
    instants: list[int] = []
    for body in bodies:
        instants.append(at)
        frame = struct.pack(">i", len(body)) + struct.pack(">q", (1 << 32) | at) + body
        frames += frame + struct.pack(">i", len(body))
        at += 16 + len(body)
    named = control(file=1, position=instants[0])
    return {
        "log/log.ctrl": named,
        "log/logmirror.ctrl": named,
        "log/log1.dat": b"\x00" * 24 + frames,
    }


def as_value(column: catalog.Column, value: object) -> object:
    """One `rows.json` value as the reader answers it, by the column's SQL type."""
    if value is None:
        return None
    match column.type.name:
        case "BLOB":
            return bytes.fromhex(str(value))
        case "DATE":
            return datetime.date.fromisoformat(str(value))
        case "TIMESTAMP":
            return datetime.datetime.fromisoformat(str(value))
        case _:
            return value


def in_order(
    rows: list[dict[str, object]], columns: Sequence[catalog.Column]
) -> list[dict[str, object]]:
    """The rows in one order, so a comparison does not lean on the heap's slot order."""
    return sorted(rows, key=lambda row: tuple(repr(row[column.name]) for column in columns))


def rewritten(destination: Path, *, member: str, edit: Callable[[bytearray], None]) -> Path:
    """The fixture's archive written again with one member edited in memory."""
    with zipfile.ZipFile(FIXTURES / "openlca.zip") as reading:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as writing:
            for name in reading.namelist():
                data = bytearray(reading.read(name))
                if name == member:
                    edit(data)
                writing.writestr(name, bytes(data))
    return destination


def name_field() -> tuple[str, int]:
    """The member and offset of the status byte of the fixture's `Chile` name field."""
    with zipfile.ZipFile(FIXTURES / "openlca.zip") as archive:
        for name in archive.namelist():
            if not (name.startswith("seg0/") and name.endswith(".dat")):
                continue
            at = archive.read(name).find(b"\x00\x07\x00\x05Chile")
            if at >= 0:
                return name, at
    raise AssertionError("the fixture holds no `Chile` name field")


def resealed(data: bytearray, at: int) -> None:
    """Recompute the checksum of the page `at` lies on, as `StoredPage` computes it."""
    size = struct.unpack(">i", data[117:121])[0]
    start = at // size * size
    data[start + size - 8 : start + size] = struct.pack(
        ">q", zlib.crc32(data[start : start + size - 8])
    )


def extensible(data: bytearray, at: int) -> None:
    """Flip one field's status to extensible and reseal the page's checksum."""
    data[at] = 0x08
    resealed(data, at)


def app_schema() -> tuple[str, int]:
    """The member and offset of the `SYS.SYSSCHEMAS` row that names `APP`, schema and owner both."""
    for member, container in containers().items():
        at = container.data.find(b"\x00\x03APP\x00\x05\x00\x03APP")
        if at >= 0:
            return member, at
    raise AssertionError("the fixture holds no APP schema row")


def renamed_apq(data: bytearray, at: int) -> None:
    """Rename one schema row's `APP` to a schema the database does not hold."""
    data[at + 2 : at + 5] = b"APQ"
    resealed(data, at)


def fewer_columns(data: bytearray, conglomerate: int) -> None:
    """Drop a heap conglomerate's column count by one and reseal the page it lies on."""
    at = data.index(b"\x01\xd3\x00\x00\x00\x00" + struct.pack(">q", conglomerate))
    count = struct.unpack(">i", data[at + 14 : at + 18])[0]
    data[at + 14 : at + 18] = struct.pack(">i", count - 1)
    resealed(data, at)


def test_the_database_answers_the_schemas_forty_nine_tables() -> None:
    database = Database(FIXTURES / "openlca.zip")
    tables = database.tables()

    assert len(tables) == 49
    assert set(recorded()) <= set(tables)
    assert all(table.name == name for name, table in tables.items())


def test_a_tables_columns_are_the_ones_rows_json_records() -> None:
    tables = Database(FIXTURES / "openlca.zip").tables()

    for name, rows in recorded().items():
        assert [column.name for column in tables[name].columns] == list(rows[0]), name
        assert [column.number for column in tables[name].columns] == list(
            range(1, len(rows[0]) + 1)
        )


def test_a_columns_sql_type_and_stored_id_are_the_ones_derby_holds() -> None:
    tables = Database(FIXTURES / "openlca.zip").tables()
    locations = {column.name: column for column in tables["TBL_LOCATIONS"].columns}
    documents = {column.name: column for column in tables["TBL_PROCESS_DOCS"].columns}
    exchanges = {column.name: column for column in tables["TBL_EXCHANGES"].columns}

    assert (locations["ID"].type.name, locations["ID"].stored_id) == ("BIGINT", 84)
    assert (locations["NAME"].type.name, locations["NAME"].type.width) == ("VARCHAR", 2048)
    assert (locations["DESCRIPTION"].type.name, locations["DESCRIPTION"].stored_id) == ("CLOB", 447)
    assert (locations["GEODATA"].type.name, locations["GEODATA"].type.width) == ("BLOB", 32 * 2**20)
    assert (documents["VALID_FROM"].type.name, documents["VALID_FROM"].stored_id) == ("DATE", 298)
    assert (documents["CREATION_DATE"].type.name, documents["CREATION_DATE"].stored_id) == (
        "TIMESTAMP",
        31,
    )
    assert (exchanges["IS_INPUT"].type.name, exchanges["IS_INPUT"].stored_id) == ("SMALLINT", 83)
    assert (exchanges["INTERNAL_ID"].type.name, exchanges["INTERNAL_ID"].stored_id) == (
        "INTEGER",
        80,
    )
    assert (
        exchanges["RESULTING_AMOUNT_VALUE"].type.name,
        exchanges["RESULTING_AMOUNT_VALUE"].stored_id,
    ) == ("DOUBLE", 79)


def test_every_row_of_every_recorded_table_equals_rows_json() -> None:
    database = Database(FIXTURES / "openlca.zip")
    tables = database.tables()

    for name, expected in recorded().items():
        table = tables[name]
        columns = {column.name: column for column in table.columns}
        wanted = [
            {column: as_value(columns[column], value) for column, value in row.items()}
            for row in expected
        ]
        assert in_order(list(database.rows(name)), table.columns) == in_order(
            wanted, table.columns
        ), name


def test_a_table_answers_its_own_rows_when_it_is_named() -> None:
    database = Database(FIXTURES / "openlca.zip")
    table = database.tables()["TBL_UNITS"]

    assert [row["NAME"] for row in database.rows(table)] == ["MJ", "kWh", "kg", "t"]


def test_types_zip_reads_a_char_and_a_boolean_column() -> None:
    database = Database(FIXTURES / "types.zip")
    columns = {column.name: column for column in database.tables()["TYPES"].columns}

    assert (columns["CODE"].type.name, columns["CODE"].type.width) == ("CHAR", 8)
    assert columns["FLAG"].type.name == "BOOLEAN"
    assert list(database.rows("TYPES")) == [
        {"ID": 1, "CODE": "alpha-01", "FLAG": True},
        {"ID": 2, "CODE": "beta-002", "FLAG": False},
    ]


def test_an_encrypted_database_is_not_supported() -> None:
    with pytest.raises(NotSupported) as raised:
        Database(FIXTURES / "encrypted.zip")
    assert "encrypted" in str(raised.value)


def test_a_database_whose_log_holds_work_after_its_checkpoint_is_not_supported() -> None:
    with pytest.raises(NotSupported) as raised:
        Database(FIXTURES / "unclean.zip")
    assert "log1.dat" in str(raised.value)
    assert "169" in str(raised.value)


def test_a_field_status_flipped_to_extensible_is_not_supported(tmp_path: Path) -> None:
    member, at = name_field()
    path = rewritten(
        tmp_path / "extensible.zip", member=member, edit=lambda data: extensible(data, at)
    )

    with pytest.raises(NotSupported):
        list(Database(path).rows("TBL_LOCATIONS"))


def test_a_clean_log_is_accepted() -> None:
    with zipfile.ZipFile(FIXTURES / "openlca.zip") as archive:
        members = {
            name: archive.read(name)
            for name in archive.namelist()
            if name.startswith("log/") and name.endswith((".ctrl", ".dat"))
        }

    assert log.check(members) is None


def test_a_log_of_three_records_is_accepted() -> None:
    assert log.check(a_log(CHECKPOINT, CHECKSUM, END_XACT)) is None


def test_a_log_whose_first_record_is_no_checkpoint_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        log.check(a_log(CHECKSUM, END_XACT))


def test_a_log_whose_end_belongs_to_another_transaction_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        log.check(a_log(CHECKPOINT, CHECKSUM, OTHER_END_XACT))


def test_a_log_whose_later_record_is_no_checksum_or_end_is_not_supported() -> None:
    with pytest.raises(NotSupported) as raised:
        log.check(a_log(CHECKPOINT, CHECKSUM, END_XACT, BEGIN_XACT))
    assert "169" in str(raised.value)


def test_a_log_whose_checkpoint_instant_names_no_record_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    members["log/log.ctrl"] = control(file=1, position=30)
    members["log/logmirror.ctrl"] = control(file=1, position=30)

    with pytest.raises(Invalid):
        log.check(members)


def test_a_log_whose_control_file_crc_fails_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    damaged = bytearray(members["log/log.ctrl"])
    damaged[16] ^= 0xFF
    members["log/log.ctrl"] = bytes(damaged)

    with pytest.raises(Invalid):
        log.check(members)


def test_a_log_whose_mirror_differs_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    mirror = bytearray(members["log/logmirror.ctrl"])
    mirror[16] ^= 0xFF
    members["log/logmirror.ctrl"] = bytes(mirror)

    with pytest.raises(Invalid):
        log.check(members)


def test_the_tables_are_read_once() -> None:
    database = Database(FIXTURES / "openlca.zip")

    assert database.tables() is database.tables()


def test_a_database_without_schema_app_is_not_supported(tmp_path: Path) -> None:
    member, at = app_schema()
    path = rewritten(
        tmp_path / "no-app.zip", member=member, edit=lambda data: renamed_apq(data, at)
    )

    with pytest.raises(NotSupported):
        Database(path).tables()


def test_a_heap_whose_column_count_disagrees_with_the_catalog_is_invalid(tmp_path: Path) -> None:
    conglomerate = Database(FIXTURES / "openlca.zip").tables()["TBL_UNITS"].conglomerate
    member = f"seg0/c{conglomerate:x}.dat"
    path = rewritten(
        tmp_path / "fewer.zip",
        member=member,
        edit=lambda data: fewer_columns(data, conglomerate),
    )

    with pytest.raises(Invalid):
        Database(path).tables()


def test_a_row_whose_fields_are_not_the_tables_columns_is_invalid() -> None:
    database = Database(FIXTURES / "openlca.zip")
    table = database.tables()["TBL_UNITS"]
    shorter = catalog.Table(
        name=table.name, conglomerate=table.conglomerate, columns=table.columns[:2]
    )

    with pytest.raises(Invalid):
        list(database.rows(shorter))


def test_an_archive_without_a_container_is_invalid(tmp_path: Path) -> None:
    conglomerate = Database(FIXTURES / "openlca.zip").tables()["TBL_UNITS"].conglomerate
    member = f"seg0/c{conglomerate:x}.dat"
    destination = tmp_path / "short.zip"
    with zipfile.ZipFile(FIXTURES / "openlca.zip") as reading:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as writing:
            for name in reading.namelist():
                if name != member:
                    writing.writestr(name, reading.read(name))

    with pytest.raises(Invalid):
        list(Database(destination).rows("TBL_UNITS"))


def test_a_conglomerate_of_another_format_is_not_supported() -> None:
    with pytest.raises(NotSupported):
        catalog._heap_descriptor(records.Field(status=0, data=b"\x01\xd2" + bytes(16)), member="a")
    with pytest.raises(Invalid):
        catalog._heap_descriptor(records.Field(status=0, data=None), member="a")
    with pytest.raises(Invalid):
        catalog._heap_descriptor(
            records.Field(status=0, data=b"\x01\xd3" + bytes(12) + struct.pack(">i", 4)),
            member="a",
        )


def test_a_type_descriptor_the_reader_does_not_know_is_not_supported() -> None:
    with pytest.raises(Invalid):
        catalog.column_type(records.Field(status=0, data=None), where="T")
    with pytest.raises(NotSupported):
        catalog.column_type(records.Field(status=0, data=b"\x00\x0f" + bytes(20)), where="T")
    with pytest.raises(Invalid):
        catalog.column_type(
            records.Field(status=0, data=b"\x00\x0e\x00\x11\x00\x04CHAR"), where="T"
        )
    with pytest.raises(NotSupported):
        catalog.column_type(
            records.Field(
                status=0,
                data=b"\x00\x0e\x00\xb2\x00\x05OTHER" + struct.pack(">iiBi", 0, 0, 1, 0),
            ),
            where="T",
        )


def test_the_catalogs_need_their_properties() -> None:
    def unused(number: int) -> pages.Container:
        raise AssertionError(f"no container is read for {number}")

    with pytest.raises(Invalid):
        catalog.tables(container_of=unused, properties={})


def test_a_log_whose_control_file_names_no_log_file_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    with pytest.raises(Invalid):
        log.check({name: data for name, data in members.items() if not name.endswith(".dat")})


def test_a_log_without_its_control_file_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    with pytest.raises(Invalid):
        log.check({name: data for name, data in members.items() if not name.endswith(".ctrl")})


def test_a_log_whose_control_file_is_of_another_size_or_format_is_invalid() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    members["log/log.ctrl"] = members["log/log.ctrl"][:47]
    members["log/logmirror.ctrl"] = members["log/log.ctrl"]
    with pytest.raises(Invalid):
        log.check(members)

    damaged = bytearray(a_log(CHECKPOINT, CHECKSUM, END_XACT)["log/log.ctrl"])
    damaged[0:4] = struct.pack(">i", 127)
    damaged[40:48] = struct.pack(">q", zlib.crc32(damaged[:40]))
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    members["log/log.ctrl"] = bytes(damaged)
    members["log/logmirror.ctrl"] = bytes(damaged)
    with pytest.raises(Invalid):
        log.check(members)


def test_a_record_whose_trailer_does_not_frame_ends_the_stream() -> None:
    members = a_log(CHECKPOINT, CHECKSUM, END_XACT)
    log_file = bytearray(members["log/log1.dat"])
    log_file[-4:] = struct.pack(">i", 999)
    members["log/log1.dat"] = bytes(log_file)

    assert log.check(members) is None


def test_a_record_that_is_no_log_record_or_names_no_operation_is_invalid() -> None:
    for body in (
        b"\x01\x02\x00\x01",
        b"\x00\x81\x41\x00",
        b"\x00\x81\x41\x00\x00\x05\x01\x07",
        b"\x00\x81\x41\x00\x00\x93\x40\x01\x36\xe6",
    ):
        with pytest.raises(Invalid):
            log.check(a_log(CHECKPOINT, CHECKSUM, END_XACT, body))
