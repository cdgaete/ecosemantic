"""Each SQL type's stored form, as `SQLChar`, `SQLBinary`, `SQLClob` and the rest write it.

The bytes handed here are a field's own data — or, for a long column, the chain its pointer names
joined. Derby's text is Java's modified UTF-8, its dates and timestamps are packed integers, and a
CLOB's and a BLOB's first bytes state how much follows.
"""

from __future__ import annotations

import datetime
import struct

from ecosemantic.errors import Invalid, NotSupported

BIGINT = struct.Struct(">q")
INTEGER = struct.Struct(">i")
SMALLINT = struct.Struct(">h")
DOUBLE = struct.Struct(">d")

CLOB_HEADER_SIZE = 5
CLOB_MARKER = 0xF0
CLOB_MARKER_MASK = 0xF0
CLOB_FORMAT_MASK = 0x0F
CLOB_EMPTY = b"\x00\x00\xf0\x00\x00"
CHARACTER_END = b"\xe0\x00\x00"
NANOS_IN_MICROSECOND = 1_000


def decode(stored_id: int, data: bytes, *, where: str) -> object:
    """Decode one field by the stored format id its column's heap conglomerate names.

    The ids are the stored format ids of `SQLBoolean`, `SQLChar`, `SQLDouble`, `SQLInteger`,
    `SQLSmallint`, `SQLLongint`, `SQLDate`, `SQLTimestamp`, `SQLClob` and `SQLBinary`.
    """
    match stored_id:
        case 77:
            _wide(data, width=1, where=where)
            return data[0] != 0
        case 78 | 85:
            return _char(data, where=where)
        case 79:
            return _real(data, where=where)
        case 80:
            return _integer(INTEGER, data, where=where)
        case 83:
            return _integer(SMALLINT, data, where=where)
        case 84:
            return _integer(BIGINT, data, where=where)
        case 298:
            return _date(data, where=where)
        case 31:
            return _timestamp(data, where=where)
        case 447:
            return _clob(data, where=where)
        case 443:
            return _blob(data, where=where)
        case _:
            raise NotSupported(f"{where}: stored format id {stored_id}")


def modified_utf8(data: bytes) -> str:
    """Java's modified UTF-8 as `SQLChar` writes it: `C0 80` for NUL, surrogates paired here."""
    units: list[int] = []
    at = 0
    while at < len(data):
        first = data[at]
        if not first & 0x80:
            units.append(first)
            at += 1
        elif first & 0xE0 == 0xC0:
            units.append(((first & 0x1F) << 6) | _continuation(data, at + 1))
            at += 2
        elif first & 0xF0 == 0xE0:
            second = _continuation(data, at + 1)
            third = _continuation(data, at + 2)
            units.append(((first & 0x0F) << 12) | (second << 6) | third)
            at += 3
        else:
            raise Invalid(f"byte {at:#04x} of {first:#04x} is no modified UTF-8 lead byte")
    taken: list[str] = []
    at = 0
    while at < len(units):
        unit = units[at]
        if 0xD800 <= unit <= 0xDBFF and at + 1 < len(units) and 0xDC00 <= units[at + 1] <= 0xDFFF:
            taken.append(chr(0x10000 + ((unit - 0xD800) << 10) + (units[at + 1] - 0xDC00)))
            at += 2
        else:
            taken.append(chr(unit))
            at += 1
    return "".join(taken)


def _continuation(data: bytes, at: int) -> int:
    """One continuation byte of a multi-byte character, its low six bits."""
    if at >= len(data) or data[at] & 0xC0 != 0x80:
        raise Invalid(f"byte {at:#04x} of the value is no continuation byte")
    return data[at] & 0x3F


def _wide(data: bytes, *, width: int, where: str) -> None:
    """Refuse a value whose stored width is not the one its type holds."""
    if len(data) != width:
        raise Invalid(f"{where}: {len(data)} bytes where {width} are stored")


def _integer(code: struct.Struct, data: bytes, *, where: str) -> int:
    """A fixed-width signed integer, as `SQLLongint`, `SQLInteger` and `SQLSmallint` store one."""
    _wide(data, width=code.size, where=where)
    return int(code.unpack(data)[0])


def _real(data: bytes, *, where: str) -> float:
    """`SQLDouble`'s IEEE double."""
    _wide(data, width=DOUBLE.size, where=where)
    return float(DOUBLE.unpack(data)[0])


def _date(data: bytes, *, where: str) -> datetime.date:
    """`SQLDate`'s `(year << 16) | (month << 8) | day` as a date."""
    value = _integer(INTEGER, data, where=where)
    year, month, day = value >> 16, value >> 8 & 0xFF, value & 0xFF
    try:
        return datetime.date(year, month, day)
    except ValueError as error:
        raise Invalid(f"{where}: {year}-{month}-{day} is no date") from error


def _timestamp(data: bytes, *, where: str) -> datetime.datetime:
    """`SQLTimestamp`'s date int, time int and nanos int as a naive timestamp."""
    _wide(data, width=3 * INTEGER.size, where=where)
    date, time, nanos = struct.unpack(">iii", data)
    if nanos % NANOS_IN_MICROSECOND:
        raise NotSupported(f"{where}: {nanos} nanoseconds is finer than a microsecond")
    try:
        return datetime.datetime(
            date >> 16,
            date >> 8 & 0xFF,
            date & 0xFF,
            time >> 16,
            time >> 8 & 0xFF,
            time & 0xFF,
            nanos // NANOS_IN_MICROSECOND,
        )
    except ValueError as error:
        raise Invalid(f"{where}: {date:#010x} {time:#010x} is no timestamp") from error


def _char(data: bytes, *, where: str) -> str:
    """`SQLChar`'s two-byte byte count, then modified UTF-8; a count of zero is the unknown form."""
    if len(data) < 2:
        raise Invalid(f"{where}: {len(data)} bytes is shorter than a character header")
    length = struct.unpack(">H", data[:2])[0]
    if not length:
        if len(data) == 2:
            return ""
        if not data.endswith(CHARACTER_END):
            raise Invalid(f"{where}: a character of unknown length does not end at its marker")
        return modified_utf8(data[2:-3])
    if 2 + length != len(data):
        raise Invalid(f"{where}: the header states {length} bytes, the field holds {len(data) - 2}")
    return modified_utf8(data[2:])


def _clob(data: bytes, *, where: str) -> str:
    """`SQLClob.investigateHeader`: a five-byte character count, or the two-byte older form."""
    if len(data) >= CLOB_HEADER_SIZE and data[2] & CLOB_MARKER_MASK == CLOB_MARKER:
        if data[2] & CLOB_FORMAT_MASK:
            raise NotSupported(f"{where}: CLOB header format {data[2] & CLOB_FORMAT_MASK}")
        if data[:CLOB_HEADER_SIZE] == CLOB_EMPTY:
            return ""
        characters = (data[0] << 24) | (data[1] << 16) | (data[3] << 8) | data[4]
        text = modified_utf8(data[CLOB_HEADER_SIZE:])
        if len(text) != characters:
            raise Invalid(
                f"{where}: the header states {characters} characters, the bytes hold {len(text)}"
            )
        return text
    return _char(data, where=where)


def _blob(data: bytes, *, where: str) -> bytes:
    """`SQLBinary.readBinaryLength`: the stored byte count, then the bytes it counts."""
    if not data:
        raise Invalid(f"{where}: a BLOB field holds no length")
    first = data[0]
    if first == 0xC0:
        length, header = _integer(INTEGER, data[1:5], where=where), 5
    elif first == 0xA0:
        _wide(data[1:3], width=2, where=where)
        length, header = struct.unpack(">H", data[1:3])[0], 3
    elif first & 0xE0 == 0x80:
        length, header = first & 0x1F, 1
    elif not first & 0x80:
        length, header = _integer(INTEGER, data[0:4], where=where) // 8, 4
    else:
        raise NotSupported(f"{where}: BLOB length header {first:#04x}")
    if header + length != len(data):
        raise Invalid(
            f"{where}: the header states {length} bytes, the field holds {len(data) - header}"
        )
    return data[header:]
