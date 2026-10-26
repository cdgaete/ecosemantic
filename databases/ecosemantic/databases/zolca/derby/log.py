"""Derby's log: `LogToFile`'s control files and the records a cleanly closed database leaves behind.

`log.ctrl` is forty-eight bytes — `FILE_STREAM_LOG_FILE`'s format id, the checkpoint instant
(`LogCounter`: the log file in the top 32 bits, the byte position in the low 31), the engine's
version and a CRC32 of its first forty bytes — and `logmirror.ctrl` holds the same bytes. A log
file opens with a twenty-four-byte header and frames each record as its length, the record's own
instant, the `LogRecord` and the length again; the record is its format id, the group it belongs
to, the transaction and the operation. A database closed cleanly leaves exactly the checkpoint,
its checksum record and the checkpoint transaction's end at and after that instant.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Mapping

from ecosemantic.databases.zolca.derby import numbers
from ecosemantic.errors import Invalid, NotSupported

CONTROL_FORMAT_ID = 128
CONTROL_SIZE = 48
CONTROL_INSTANT = 8
CONTROL_CRC_OFFSET = 40
CONTROL = "log/log.ctrl"
MIRROR = "log/logmirror.ctrl"
LOG_FILE = "log/log{number}.dat"

FILE_HEADER_SIZE = 24
RECORD_FORMAT_ID = 129
RECORD_OVERHEAD = 16
TRANSACTION_FORMAT_ID = 147

LOGOP_CHECKPOINT = 263
LOGOP_CHECKSUM = 453
LOGOP_END_XACT = 102


def check(members: Mapping[str, bytes]) -> None:
    """Refuse a log holding, after its checkpoint instant, a record a clean shutdown leaves out."""
    control = _control(members)
    instant = struct.unpack(">q", control[CONTROL_INSTANT : CONTROL_INSTANT + 8])[0]
    number, position = instant >> 32, instant & 0x7FFFFFFF
    member = LOG_FILE.format(number=number)
    data = members.get(member)
    if data is None:
        raise Invalid(f"{member}: the control file names a log file the archive does not hold")
    first = _framed(data, at=position)
    if first is None or first[0] != instant:
        raise Invalid(f"{member}: position {position} holds no record of the checkpoint instant")
    operation, transaction = _operation(first[1], member=member, at=position)
    if operation != LOGOP_CHECKPOINT:
        raise NotSupported(
            f"{member}: position {position} holds operation {operation}, no checkpoint"
        )
    at = position + RECORD_OVERHEAD + len(first[1])
    while (found := _framed(data, at=at)) is not None:
        operation, other = _operation(found[1], member=member, at=at)
        if operation != LOGOP_CHECKSUM and not (
            operation == LOGOP_END_XACT and other == transaction
        ):
            raise NotSupported(
                f"{member}: position {at} holds operation {operation}, "
                "which a checkpoint leaves out"
            )
        at += RECORD_OVERHEAD + len(found[1])


def _control(members: Mapping[str, bytes]) -> bytes:
    """`log.ctrl`, its length, its format id and its CRC32 checked, and its mirror equal to it."""
    control = members.get(CONTROL)
    if control is None:
        raise Invalid(f"{CONTROL}: the archive holds no control file")
    if len(control) != CONTROL_SIZE:
        raise Invalid(f"{CONTROL}: {len(control)} bytes where {CONTROL_SIZE} are written")
    if struct.unpack(">i", control[0:4])[0] != CONTROL_FORMAT_ID:
        raise Invalid(f"{CONTROL}: format id {struct.unpack('>i', control[0:4])[0]}")
    if struct.unpack(">q", control[CONTROL_CRC_OFFSET:])[0] != zlib.crc32(
        control[:CONTROL_CRC_OFFSET]
    ):
        raise Invalid(f"{CONTROL}: the control file fails its CRC32")
    if members.get(MIRROR) != control:
        raise Invalid(f"{MIRROR}: the mirror differs from {CONTROL}")
    return control


def _framed(data: bytes, *, at: int) -> tuple[int, bytes] | None:
    """One record's instant and body where the stream frames it, and nothing where it ends."""
    if at + RECORD_OVERHEAD > len(data):
        return None
    length = struct.unpack(">i", data[at : at + 4])[0]
    if length <= 0 or at + RECORD_OVERHEAD + length > len(data):
        return None
    trailer = struct.unpack(">i", data[at + 12 + length : at + 16 + length])[0]
    if trailer != length:
        return None
    return struct.unpack(">q", data[at + 4 : at + 12])[0], data[at + 12 : at + 12 + length]


def _operation(record: bytes, *, member: str, at: int) -> tuple[int, int]:
    """A `LogRecord`'s operation id and its transaction id, its format id and group read past."""
    if len(record) < 4 or struct.unpack(">H", record[0:2])[0] != RECORD_FORMAT_ID:
        raise Invalid(f"{member}: the record at {at} is no log record")
    _group, cursor = numbers.read_int(record, 2)
    if cursor + 2 > len(record):
        raise Invalid(f"{member}: the record at {at} names no transaction")
    kind = struct.unpack(">H", record[cursor : cursor + 2])[0]
    cursor += 2
    transaction = 0
    if kind == TRANSACTION_FORMAT_ID:
        transaction, cursor = numbers.read_long(record, cursor)
    elif kind != 0:
        raise Invalid(f"{member}: the record at {at} names transaction format id {kind}")
    if cursor + 2 > len(record):
        raise Invalid(f"{member}: the record at {at} names no operation")
    return struct.unpack(">H", record[cursor : cursor + 2])[0], transaction
