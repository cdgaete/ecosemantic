"""Derby's record and field headers, and the chains a row and a long column are read from."""

from __future__ import annotations

import pytest

from ecosemantic.databases.zolca.derby import pages, records
from ecosemantic.errors import Invalid, NotSupported
from tests.databases.zolca.fixture import containers, row_of


def page_of(*bodies: bytes, overflow: bool = False) -> pages.Page:
    """A stored page whose slots hold the record bytes given."""
    slots: list[pages.Slot] = []
    at = 0
    for body in bodies:
        slots.append(pages.Slot(offset=at, length=len(body), reserved=0))
        at += len(body)
    return pages.Page(
        number=1,
        format_id=117,
        overflow=overflow,
        status=1,
        slots=tuple(slots),
        data=b"".join(bodies),
    )


def test_a_record_reads_its_id_and_its_fields() -> None:
    (read,) = records.records(page_of(b"\x00\x07\x02\x00\x02hi\x01"))
    assert read == records.Record(
        status=0,
        record_id=7,
        overflow=None,
        first_field=0,
        fields=(records.Field(status=0, data=b"hi"), records.Field(status=1, data=None)),
    )


def test_a_deleted_record_is_not_read() -> None:
    assert list(records.records(page_of(b"\x01\x08\x01\x01"))) == []


def test_a_record_that_overflows_and_names_no_first_field_stores_no_field_count() -> None:
    (read,) = records.records(page_of(b"\x02\x09\x00\x01\x41\x2c"))
    assert read.overflow == records.Pointer(page=1, record_id=300)
    assert read.first_field == 0
    assert read.fields == ()


def test_a_field_status_that_is_extensible_or_tagged_is_not_supported() -> None:
    for status in (0x08, 0x10):
        with pytest.raises(NotSupported):
            list(records.records(page_of(bytes([0x00, 0x07, 0x01, status]))))


def test_a_nonexistent_field_reads_as_null() -> None:
    (read,) = records.records(page_of(b"\x00\x07\x01\x05"))
    assert read.fields == (records.Field(status=5, data=None),)


def test_a_field_running_past_its_record_is_invalid() -> None:
    with pytest.raises(Invalid):
        list(records.records(page_of(b"\x00\x07\x01\x00\x09abc")))


def test_a_record_naming_more_fields_than_it_holds_is_invalid() -> None:
    with pytest.raises(Invalid):
        list(records.records(page_of(b"\x00\x07\x02\x01")))


def test_a_record_whose_fields_do_not_fill_its_slot_is_invalid() -> None:
    with pytest.raises(Invalid):
        list(records.records(page_of(b"\x00\x07\x00\x00")))
    with pytest.raises(Invalid):
        list(records.records(page_of(b"")))


def test_the_records_of_an_overflow_page_are_no_rows() -> None:
    body = b"\x04\x06\x00\x01\x00\x03abc"
    assert list(records.records(page_of(body, overflow=True))) == []
    assert len(list(records.records(page_of(body)))) == 1


def test_a_field_holding_a_four_byte_pointer_reads_page_1_record_300() -> None:
    field = records.Field(status=records.FIELD_OVERFLOW, data=b"\x00\x01\x41\x2c")
    assert records.pointer(field) == records.Pointer(page=1, record_id=300)


def test_a_field_that_is_not_a_bare_pointer_is_not_supported() -> None:
    for data in (b"\x00\x01\x41\x2c\x00", b"\x00\x01\x05\x00"):
        with pytest.raises(NotSupported):
            records.pointer(records.Field(status=records.FIELD_OVERFLOW, data=data))


def test_a_field_shorter_than_a_pointer_is_invalid() -> None:
    for data in (b"", b"\x02", b"\x00\x01\x41"):
        with pytest.raises(Invalid):
            records.pointer(records.Field(status=records.FIELD_OVERFLOW, data=data))


def test_a_null_field_holds_no_pointer() -> None:
    with pytest.raises(Invalid):
        records.pointer(records.Field(status=records.FIELD_NULL, data=None))


def test_a_row_continued_on_an_overflow_page_reads_whole() -> None:
    container, page, head = row_of(25, holding="run-of-river plant")
    fields = records.row(container, head)

    assert head.overflow is not None
    assert len(head.fields) == 7
    assert len(fields) == 25
    assert fields[: len(head.fields)] == head.fields
    assert container.page(head.overflow.page).overflow is True
    assert head.record_id in {record.record_id for record in records.records(page)}


def test_a_pointer_that_names_a_page_which_is_no_overflow_page_is_invalid() -> None:
    container, _, head = row_of(25, holding="Policy support")
    stray = records.Record(
        status=records.RECORD_OVERFLOW | records.RECORD_HAS_FIRST_FIELD,
        record_id=head.record_id,
        overflow=records.Pointer(page=1, record_id=6),
        first_field=0,
        fields=head.fields[:1],
    )
    with pytest.raises(Invalid):
        records.row(container, stray)


def test_a_pointer_to_a_row_continuation_is_no_link_of_a_long_columns_chain() -> None:
    container, _, head = row_of(25, holding="run-of-river plant")
    assert head.overflow is not None
    with pytest.raises(Invalid):
        records.long_value(container, head.overflow)


def test_a_pointer_to_a_record_the_page_does_not_hold_is_invalid() -> None:
    container, _, head = row_of(25, holding="run-of-river plant")
    assert head.overflow is not None
    stray = records.Record(
        status=records.RECORD_OVERFLOW | records.RECORD_HAS_FIRST_FIELD,
        record_id=head.record_id,
        overflow=records.Pointer(page=head.overflow.page, record_id=999),
        first_field=0,
        fields=head.fields[:1],
    )
    with pytest.raises(Invalid):
        records.row(container, stray)


def test_a_row_whose_portions_do_not_meet_is_invalid() -> None:
    container, _, head = row_of(25, holding="Policy support")
    stray = records.Record(
        status=records.RECORD_HAS_FIRST_FIELD,
        record_id=head.record_id,
        overflow=None,
        first_field=3,
        fields=head.fields[:2],
    )
    with pytest.raises(Invalid):
        records.row(container, stray)


def test_deleted_records_are_not_read() -> None:
    _, page, _ = row_of(14, holding="Hydropower report")
    assert len(page.slots) == 4
    assert len(list(records.records(page))) == 2


def test_the_emptied_heap_reads_only_the_records_its_pages_left_live() -> None:
    container = max(containers().values(), key=lambda one: len(one.data))
    live = [record for page in container.live_pages() for record in records.records(page)]

    assert len(container.extents) == 2
    assert sum(len(page.slots) for page in container.live_pages()) == 8
    assert len(live) == 5
    assert not any(record.status & records.RECORD_DELETED for record in live)
