"""Derby's container header, its allocation extents and a stored page's slots, from the bytes."""

from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from ecosemantic.databases.zolca.derby import pages
from ecosemantic.errors import Invalid, NotSupported

FIXTURES = Path(__file__).parent / "fixtures"
CONTAINER_INFO = slice(109, 189)
CONTAINER_CRC = slice(72, 80)
EXTENT_AT = 189


def members() -> dict[str, bytes]:
    """Every container of the openLCA-schema fixture, by its member in the archive."""
    with zipfile.ZipFile(FIXTURES / "openlca.zip") as archive:
        return {
            name: archive.read(name)
            for name in archive.namelist()
            if name.startswith("seg0/") and name.endswith(".dat")
        }


def containers() -> list[pages.Container]:
    return [pages.Container(member=name, data=data) for name, data in members().items()]


def page_size(data: bytes) -> int:
    return struct.unpack(">i", data[CONTAINER_INFO.start + 8 : CONTAINER_INFO.start + 12])[0]


def checksum(data: bytes, number: int, *, borrowed: bool = True) -> int:
    """A page's checksum as `StoredPage` computes it, page 0's borrowed record blanked."""
    size = page_size(data)
    base = number * size
    body = bytearray(data[base : base + size - 8])
    if borrowed and number == 0 and data[base + 108]:
        body[109 : 109 + data[base + 108]] = bytes(data[base + 108])
    return zlib.crc32(body)


def seal_container(damaged: bytearray) -> None:
    """Recompute page 0's container CRC and its checksum, as `AllocPage` writes them."""
    record = bytearray(damaged[CONTAINER_INFO])
    record[CONTAINER_CRC] = struct.pack(">q", zlib.crc32(record[: CONTAINER_CRC.start]))
    damaged[CONTAINER_INFO] = record
    size = page_size(damaged)
    damaged[size - 8 : size] = struct.pack(">q", checksum(damaged, 0))


def seal_page(damaged: bytearray, number: int) -> None:
    size = page_size(damaged)
    base = number * size
    damaged[base + size - 8 : base + size] = struct.pack(">q", checksum(damaged, number))


def a_container() -> tuple[str, bytes]:
    """The largest container of the fixture, whose heap spans two allocation extents."""
    name, data = max(members().items(), key=lambda member: len(member[1]))
    return name, data


def a_live_page(data: bytes) -> pages.Page:
    """A page of the container that holds records and that its extent leaves free of."""
    for page in pages.Container(member="an unnamed member", data=data).live_pages():
        if page.slots:
            return page
    raise AssertionError("the container holds no live page with slots")


def test_every_container_of_the_fixture_reads_its_header() -> None:
    read = containers()
    assert len(read) == 197
    assert {container.info.format_id for container in read} == {116}
    assert {container.info.page_size for container in read} == {4096, 32768}
    assert {container.info.first_alloc_page_number for container in read} == {0}
    assert {container.info.first_alloc_page_offset for container in read} == {0}


def test_the_container_record_carries_derbys_crc32_of_its_first_seventy_two_bytes() -> None:
    name, data = a_container()
    read = pages.Container(member=name, data=data)
    record = data[CONTAINER_INFO]
    assert read.info.crc == zlib.crc32(record[: CONTAINER_CRC.start])


def test_a_container_whose_crc_is_changed_is_invalid() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    damaged[CONTAINER_INFO.start + 40] ^= 0xFF
    with pytest.raises(Invalid) as raised:
        pages.Container(member=name, data=bytes(damaged))
    assert name in str(raised.value)


def test_a_page_whose_checksum_is_changed_is_invalid_naming_the_file_and_the_page() -> None:
    name, data = a_container()
    page = a_live_page(data)
    damaged = bytearray(data)
    damaged[page.number * page_size(data) + 200] ^= 0xFF
    with pytest.raises(Invalid) as raised:
        pages.Container(member=name, data=bytes(damaged)).page(page.number)
    assert name in str(raised.value)
    assert str(page.number) in str(raised.value)


def test_page_0_passes_only_with_its_borrowed_record_zeroed() -> None:
    name, data = a_container()
    size = page_size(data)
    stored = struct.unpack(">q", data[size - 8 : size])[0]

    assert pages.Container(member=name, data=data).page(0).format_id == 118
    assert zlib.crc32(data[: size - 8]) != stored
    assert checksum(data, 0) == stored


def test_the_multi_extent_heap_chains_a_second_allocation_page() -> None:
    name, data = a_container()
    read = pages.Container(member=name, data=data)
    first, second = read.extents

    assert [(extent.start, extent.end, extent.length) for extent in read.extents] == [
        (1, 10216, 10216),
        (10218, 20641, 2451),
    ]
    assert [extent.offset for extent in read.extents] == [
        extent.start * read.info.page_size for extent in read.extents
    ]
    assert second.start == first.end + 2
    assert (len(first.free), len(second.free)) == (10215, 2451)
    assert read.page(second.start).format_id == 117


def test_a_page_whose_status_is_invalid_is_not_live_though_its_slots_are_intact() -> None:
    name, data = a_container()
    page = a_live_page(data)
    damaged = bytearray(data)
    damaged[page.number * page_size(data) + 5] = 2
    seal_page(damaged, page.number)
    changed = pages.Container(member=name, data=bytes(damaged))

    assert changed.page(page.number).slots == page.slots
    assert page.number not in {live.number for live in changed.live_pages()}


def test_a_page_format_id_the_reader_does_not_know_is_not_supported() -> None:
    name, data = a_container()
    page = a_live_page(data)
    damaged = bytearray(data)
    base = page.number * page_size(data)
    damaged[base : base + 2] = struct.pack(">H", 116)
    seal_page(damaged, page.number)
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged)).page(page.number)


def test_a_container_format_id_the_reader_does_not_know_is_not_supported() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    damaged[CONTAINER_INFO.start : CONTAINER_INFO.start + 4] = struct.pack(">i", 115)
    seal_container(damaged)
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged))


def test_a_dropped_container_is_not_supported() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    damaged[CONTAINER_INFO.start + 4 : CONTAINER_INFO.start + 8] = struct.pack(">i", 1)
    seal_container(damaged)
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged))


def test_a_retired_extent_is_not_supported() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    status_at = EXTENT_AT + 28
    status = struct.unpack(">i", damaged[status_at : status_at + 4])[0]
    damaged[status_at : status_at + 4] = struct.pack(">i", status | 0x8)
    seal_container(damaged)
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged))


def test_a_page_past_the_end_of_the_container_is_invalid() -> None:
    name, data = a_container()
    read = pages.Container(member=name, data=data)
    with pytest.raises(Invalid):
        read.page(len(data) // read.info.page_size + 1)


def test_a_container_shorter_than_its_record_is_invalid() -> None:
    name, data = a_container()
    with pytest.raises(Invalid):
        pages.Container(member=name, data=data[:100])


def test_a_container_record_of_another_length_is_not_supported() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    damaged[108] = 64
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged))


def test_a_first_allocation_page_past_the_end_is_invalid() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    past = len(data) // page_size(data) + 5
    damaged[CONTAINER_INFO.start + 24 : CONTAINER_INFO.start + 32] = struct.pack(">q", past)
    damaged[CONTAINER_INFO.start + 32 : CONTAINER_INFO.start + 40] = struct.pack(">q", past)
    seal_container(damaged)
    with pytest.raises(Invalid):
        pages.Container(member=name, data=bytes(damaged))


def test_a_first_page_that_is_no_allocation_page_is_not_supported() -> None:
    name, data = a_container()
    damaged = bytearray(data)
    damaged[0:2] = struct.pack(">H", 117)
    size = page_size(damaged)
    damaged[size - 8 : size] = struct.pack(">q", checksum(damaged, 0, borrowed=False))
    with pytest.raises(NotSupported):
        pages.Container(member=name, data=bytes(damaged))


def test_a_page_claiming_more_slots_than_it_has_room_for_is_invalid() -> None:
    name, data = a_container()
    page = a_live_page(data)
    damaged = bytearray(data)
    base = page.number * page_size(data)
    damaged[base + 14 : base + 16] = struct.pack(">H", 0xFFFF)
    seal_page(damaged, page.number)
    with pytest.raises(Invalid):
        pages.Container(member=name, data=bytes(damaged)).page(page.number)
