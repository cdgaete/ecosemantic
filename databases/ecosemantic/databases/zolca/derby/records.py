"""Derby's records and fields, `StoredRecordHeader` and `StoredFieldHeader` as Derby writes them.

A stored page holds record portions, each behind a slot of its table: a status byte, the record's
id, and — when the record overflows or names the column its fields start at — a pointer and a
first field, then the count of fields and their headers. A row too large for one page continues
in portions on overflow pages, and a long column leaves a pointer in the row and its bytes in a
chain of them; `row` and `long_value` stitch both from the pointer that names the first page.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from ecosemantic.databases.zolca.derby import numbers, values
from ecosemantic.databases.zolca.derby.pages import Container, Page
from ecosemantic.errors import Invalid, NotSupported

CONGLOMERATE_RECORD_ID = 6

RECORD_DELETED = 0x01
RECORD_OVERFLOW = 0x02
RECORD_HAS_FIRST_FIELD = 0x04

FIELD_NULL = 0x01
FIELD_OVERFLOW = 0x02
FIELD_EXTENSIBLE = 0x08
FIELD_TAGGED = 0x10


@dataclass(frozen=True)
class Pointer:
    """Where a record or a long column continues: `RecordHandle`'s page number and record id."""

    page: int
    record_id: int


@dataclass(frozen=True)
class Field:
    """One `StoredFieldHeader` and the bytes it holds; `data` is None for a null field."""

    status: int
    data: bytes | None


@dataclass(frozen=True)
class Record:
    """One `StoredRecordHeader` and its fields: a row's portion, or one of a long column's."""

    status: int
    record_id: int
    overflow: Pointer | None
    first_field: int
    fields: tuple[Field, ...]


def records(page: Page) -> Iterator[Record]:
    """Every record a page holds, the deleted ones excluded.

    A page an overflow pointer reaches holds continuations of rows and of long columns, not
    rows, so it yields nothing: `Page.overflow` is what tells the two apart, since a
    continuation and a heap's own first record both carry `RECORD_HAS_FIRST_FIELD`. Every page
    numbers its records from 6 (`RecordHandle.FIRST_RECORD_ID`), so the record 6 of a heap's
    first page is the heap's own conglomerate descriptor and no row.
    """
    if page.overflow:
        return
    for slot in page.slots:
        record = _record(
            page.data[slot.offset : slot.offset + slot.length],
            where=f"page {page.number} slot {slot.offset}",
        )
        if record.status & RECORD_DELETED:
            continue
        yield record


def rows(container: Container) -> Iterator[tuple[Field, ...]]:
    """Every row a heap holds, its first page's conglomerate descriptor left out, stitched."""
    first = container.extents[0].start
    for page in container.live_pages():
        for record in records(page):
            if page.number == first and record.record_id == CONGLOMERATE_RECORD_ID:
                continue
            yield row(container, record)


def value(container: Container, field: Field, stored_id: int, *, where: str) -> object:
    """One field's value, decoded by its column's stored id, its chain followed when it has one."""
    if field.data is None:
        return None
    if field.status & FIELD_OVERFLOW:
        return values.decode(stored_id, long_value(container, pointer(field)), where=where)
    return values.decode(stored_id, field.data, where=where)


def pointer(field: Field) -> Pointer:
    """The `Pointer` a field's data holds at its start, which must consume the data exactly."""
    return _pointer(field)


def _pointer(field: Field) -> Pointer:
    """`CompressedNumber`'s long page and int record id, which are the whole of the field."""
    if field.data is None:
        raise Invalid("a null field holds no pointer")
    page, at = numbers.read_long(field.data, 0)
    record_id, at = numbers.read_int(field.data, at)
    if at != len(field.data):
        raise NotSupported(f"a field of {len(field.data)} bytes is no bare pointer")
    return Pointer(page=page, record_id=record_id)


def row(container: Container, head: Record) -> tuple[Field, ...]:
    """A row's fields, its portions stitched by the `first_field` each portion names."""
    fields: list[Field] = []
    portion: Record | None = head
    while portion is not None:
        if portion.first_field != len(fields):
            raise Invalid(
                f"{container.member}: a portion starts at field {portion.first_field}, "
                f"{len(fields)} are stitched"
            )
        fields.extend(portion.fields)
        portion = _at(container, portion.overflow) if portion.overflow else None
    return tuple(fields)


def long_value(container: Container, pointer: Pointer) -> bytes:
    """A long column's bytes, the chain of overflow records the pointer names joined.

    `StoredPage` writes each link as the chunk in field 0 and, when more follows, the next
    pointer in field 1, so a record of any other shape is no link of a long column's chain.
    """
    chunks: list[bytes] = []
    at: Pointer | None = pointer
    while at is not None:
        portion = _at(container, at)
        chunk = portion.fields[0] if portion.fields else None
        if chunk is None or len(portion.fields) > 2 or chunk.data is None:
            raise Invalid(
                f"{container.member}: page {at.page} record {at.record_id} is no chunk of a chain"
            )
        chunks.append(chunk.data)
        following = portion.fields[1:]
        at = _pointer(following[0]) if following and following[0].status & FIELD_OVERFLOW else None
    return b"".join(chunks)


def _at(container: Container, pointer: Pointer) -> Record:
    """The record a pointer names, read from the overflow page it lies on."""
    page = container.page(pointer.page)
    if not page.overflow:
        raise Invalid(f"{container.member}: page {pointer.page} is no overflow page")
    for slot in page.slots:
        record = _record(
            page.data[slot.offset : slot.offset + slot.length],
            where=f"{container.member} page {pointer.page}",
        )
        if record.record_id == pointer.record_id:
            return record
    raise Invalid(f"{container.member}: page {pointer.page} holds no record {pointer.record_id}")


def _record(portion: bytes, *, where: str) -> Record:
    """One `StoredRecordHeader`: its status, its id, its pointer and its field headers."""
    if not portion:
        raise Invalid(f"{where}: the slot holds no bytes")
    status = portion[0]
    record_id, at = numbers.read_int(portion, 1)
    overflow = None
    if status & RECORD_OVERFLOW:
        page, at = numbers.read_long(portion, at)
        identifier, at = numbers.read_int(portion, at)
        overflow = Pointer(page=page, record_id=identifier)
    first_field = 0
    count = 0
    if status & RECORD_HAS_FIRST_FIELD:
        first_field, at = numbers.read_int(portion, at)
    if not status & RECORD_OVERFLOW or status & RECORD_HAS_FIRST_FIELD:
        count, at = numbers.read_int(portion, at)
    fields: list[Field] = []
    for _ in range(count):
        field, at = _field(portion, at=at, where=where)
        fields.append(field)
    if at != len(portion):
        raise Invalid(f"{where}: the record leaves {len(portion) - at} bytes of its slot unread")
    return Record(
        status=status,
        record_id=record_id,
        overflow=overflow,
        first_field=first_field,
        fields=tuple(fields),
    )


def _field(portion: bytes, *, at: int, where: str) -> tuple[Field, int]:
    """One `StoredFieldHeader`: its status, and unless it is null its length and its data."""
    if at >= len(portion):
        raise Invalid(f"{where}: a field header lies past the record's end")
    status = portion[at]
    at += 1
    if status & (FIELD_EXTENSIBLE | FIELD_TAGGED):
        raise NotSupported(f"{where}: field status {status:#04x} is extensible or tagged")
    if status & FIELD_NULL:
        return Field(status=status, data=None), at
    length, at = numbers.read_int(portion, at)
    if at + length > len(portion):
        raise Invalid(f"{where}: a field of {length} bytes lies past the record's end")
    return Field(status=status, data=portion[at : at + length]), at + length
