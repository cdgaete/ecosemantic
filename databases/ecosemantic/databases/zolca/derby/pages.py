"""Derby's container header, its allocation pages and extents, and its stored pages.

Every layout here is the one Apache Derby 10.17 writes, and each function that decodes one
names the class it follows. A container file is a `FileContainer`: a record of eighty bytes
held in page 0's borrowed space, then allocation pages chained through
`nextAllocPageNumber` and `nextAllocPageOffset`, each managing one `AllocExtent` of pages.
A page is a `StoredPage`: a header, the records' portions, a slot table and a checksum.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass

from ecosemantic.errors import Invalid, NotSupported

CONTAINER_FORMAT_ID = 116
STORED_PAGE_FORMAT_ID = 117
ALLOC_PAGE_FORMAT_ID = 118

CONTAINER_INFO_SIZE = 80
CONTAINER_CRC_OFFSET = 72
CONTAINER_STATUS_DROPPED = 0x1
CONTAINER_STATUS_COMMITTED_DROP = 0x2

NEXT_ALLOC_PAGE_OFFSET = 60
NEXT_ALLOC_PAGE_PHYSICAL_OFFSET = 68
BORROWED_SPACE_OFFSET = 108
BORROWED_SPACE_START = 109

EXTENT_SIZE = 56
EXTENT_RETIRED = 0x8

PAGE_HEADER_SIZE = 60
PAGE_OVERFLOW_OFFSET = 4
PAGE_STATUS_OFFSET = 5
PAGE_SLOTS_IN_USE_OFFSET = 14
PAGE_VALID = 1
SLOT_WIDTH_LIMIT = 0x10000


@dataclass(frozen=True)
class ContainerInfo:
    """A container's `FileContainer` record: its format, its status, its page size and its pages."""

    format_id: int
    status: int
    page_size: int
    spare_space_per_record: int
    minimum_record_size: int
    initial_pages: int
    prealloc_size: int
    first_alloc_page_number: int
    first_alloc_page_offset: int
    container_version: int
    estimated_rows: int
    reusable_record_id: int
    crc: int


@dataclass(frozen=True)
class Extent:
    """One `AllocExtent`: the pages an allocation page manages and the ones it leaves free.

    `end` is the last page the extent can ever manage (`MAX_RANGE`), not the last one it has
    allocated: it equals `start + length - 1` only once the extent is full.
    """

    offset: int
    start: int
    end: int
    length: int
    status: int
    prealloc_length: int
    free: frozenset[int]


@dataclass(frozen=True)
class Slot:
    """One `StoredPage` slot-table entry: where a portion starts, how long it is, what it kept."""

    offset: int
    length: int
    reserved: int


@dataclass(frozen=True)
class Page:
    """One stored page: `StoredPage`'s header, its slot table, and the bytes both describe."""

    number: int
    format_id: int
    overflow: bool
    status: int
    slots: tuple[Slot, ...]
    data: bytes


class Container:
    """One container file of a zolca, read as `FileContainer` and `AllocPage` lay it out.

    Construction checks the container record's format id, its dropped status and its CRC32,
    then walks the allocation pages and refuses a retired extent. A page's checksum and
    format id are checked when it is read: page 0's with its borrowed record zeroed, as
    `AllocPage` computes it.
    """

    def __init__(self, member: str, data: bytes) -> None:
        self.member = member
        self.data = data
        self.info = _container_info(member, data)
        self.extents = _extents(self)

    def page(self, number: int) -> Page:
        """The page `number`, its checksum and format id checked."""
        size = self.info.page_size
        base = number * size
        if number < 0 or base + size > len(self.data):
            raise Invalid(f"{self.member}: page {number} lies past the container's end")
        format_id = struct.unpack(">H", self.data[base : base + 2])[0]
        if format_id not in (STORED_PAGE_FORMAT_ID, ALLOC_PAGE_FORMAT_ID):
            raise NotSupported(f"{self.member}: page {number} has format id {format_id}")
        stored = struct.unpack(">q", self.data[base + size - 8 : base + size])[0]
        if _checksum(self.data, number=number, page_size=size) != stored:
            raise Invalid(f"{self.member}: page {number} fails its checksum")
        return Page(
            number=number,
            format_id=format_id,
            overflow=self.data[base + PAGE_OVERFLOW_OFFSET] != 0,
            status=self.data[base + PAGE_STATUS_OFFSET],
            slots=_slots(member=self.member, data=self.data, number=number, page_size=size),
            data=self.data[base : base + size],
        )

    def live_pages(self) -> Iterator[Page]:
        """The pages a container holds rows on: neither free in their extent nor invalid."""
        for extent in self.extents:
            for number in range(extent.start, extent.start + extent.length):
                if number in extent.free:
                    continue
                page = self.page(number)
                if page.status != PAGE_VALID:
                    continue
                yield page


def _container_info(member: str, data: bytes) -> ContainerInfo:
    """The `FileContainer` record page 0 borrows its space for, its CRC32 checked."""
    if len(data) < BORROWED_SPACE_START + CONTAINER_INFO_SIZE:
        raise Invalid(f"{member}: {len(data)} bytes is shorter than a container header")
    length = data[BORROWED_SPACE_OFFSET]
    if length != CONTAINER_INFO_SIZE:
        raise NotSupported(f"{member}: the container record is {length} bytes")
    record = data[BORROWED_SPACE_START : BORROWED_SPACE_START + CONTAINER_INFO_SIZE]
    info = ContainerInfo(
        format_id=struct.unpack(">i", record[0:4])[0],
        status=struct.unpack(">i", record[4:8])[0],
        page_size=struct.unpack(">i", record[8:12])[0],
        spare_space_per_record=struct.unpack(">i", record[12:16])[0],
        minimum_record_size=struct.unpack(">i", record[16:20])[0],
        initial_pages=struct.unpack(">h", record[20:22])[0],
        prealloc_size=struct.unpack(">h", record[22:24])[0],
        first_alloc_page_number=struct.unpack(">q", record[24:32])[0],
        first_alloc_page_offset=struct.unpack(">q", record[32:40])[0],
        container_version=struct.unpack(">q", record[40:48])[0],
        estimated_rows=struct.unpack(">q", record[48:56])[0],
        reusable_record_id=struct.unpack(">q", record[56:64])[0],
        crc=struct.unpack(">q", record[CONTAINER_CRC_OFFSET:CONTAINER_INFO_SIZE])[0],
    )
    if info.format_id != CONTAINER_FORMAT_ID:
        raise NotSupported(f"{member}: the container has format id {info.format_id}")
    if info.status & (CONTAINER_STATUS_DROPPED | CONTAINER_STATUS_COMMITTED_DROP):
        raise NotSupported(f"{member}: the container is dropped, status {info.status}")
    if info.crc != zlib.crc32(record[:CONTAINER_CRC_OFFSET]):
        raise Invalid(f"{member}: the container record fails its CRC32")
    return info


def _extents(container: Container) -> tuple[Extent, ...]:
    """Every `AllocPage` extent of a container, walked through `nextAllocPageOffset`."""
    found: list[Extent] = []
    number = container.info.first_alloc_page_number
    offset = container.info.first_alloc_page_offset
    while number >= 0:
        base = offset * container.info.page_size
        extent, next_number, next_offset = _alloc_page(container, number=number, base=base)
        found.append(extent)
        number, offset = next_number, next_offset
    return tuple(found)


def _alloc_page(container: Container, *, number: int, base: int) -> tuple[Extent, int, int]:
    """One `AllocPage`: its checksum, its extent, and the allocation page it chains to."""
    size = container.info.page_size
    if base + size > len(container.data):
        raise Invalid(f"{container.member}: allocation page {number} lies past the container's end")
    page = container.page(number)
    if page.format_id != ALLOC_PAGE_FORMAT_ID:
        raise NotSupported(f"{container.member}: page {number} is no allocation page")
    data = container.data
    chained_at = base + NEXT_ALLOC_PAGE_OFFSET
    chained_offset_at = base + NEXT_ALLOC_PAGE_PHYSICAL_OFFSET
    extent_at = base + BORROWED_SPACE_START + data[base + BORROWED_SPACE_OFFSET]
    extent = _extent(container.member, data=data, base=extent_at)
    return (
        extent,
        struct.unpack(">q", data[chained_at : chained_at + 8])[0],
        struct.unpack(">q", data[chained_offset_at : chained_offset_at + 8])[0],
    )


def _extent(member: str, *, data: bytes, base: int) -> Extent:
    """The `AllocExtent` an allocation page holds, with the pages its bitmap leaves free."""
    offset, start, end, length, status, prealloc_length = struct.unpack(
        ">qqqiiiiqq", data[base : base + EXTENT_SIZE]
    )[:6]
    if status & EXTENT_RETIRED:
        raise NotSupported(f"{member}: the extent at page {start} is retired")
    bits_at = base + EXTENT_SIZE
    bits = struct.unpack(">i", data[bits_at : bits_at + 4])[0]
    free = frozenset(start + index for index in _set_bits(data, bits_at + 4, bits))
    return Extent(
        offset=offset,
        start=start,
        end=end,
        length=length,
        status=status,
        prealloc_length=prealloc_length,
        free=free,
    )


def _set_bits(data: bytes, at: int, bits: int) -> Iterator[int]:
    """The indexes a `FormatableBitSet` holds set, its bytes most significant bit first."""
    for index in range(bits):
        byte = data[at + index // 8]
        if byte >> (7 - index % 8) & 1:
            yield index


def _slots(*, member: str, data: bytes, number: int, page_size: int) -> tuple[Slot, ...]:
    """A stored page's slot table, `StoredPage`'s `3 * slotFieldSize` entries from the end."""
    base = number * page_size
    used_at = base + PAGE_SLOTS_IN_USE_OFFSET
    used = struct.unpack(">H", data[used_at : used_at + 2])[0]
    width = 2 if page_size < SLOT_WIDTH_LIMIT else 4
    entry = 3 * width
    code = ">3H" if width == 2 else ">3I"
    found: list[Slot] = []
    for index in range(used):
        at = base + page_size - 8 - entry - index * entry
        if at < base + PAGE_HEADER_SIZE:
            raise Invalid(f"{member}: page {number} claims {used} slots it has no room for")
        offset, length, reserved = struct.unpack(code, data[at : at + entry])
        if offset:
            found.append(Slot(offset=offset, length=length, reserved=reserved))
    return tuple(found)


def _checksum(data: bytes, *, number: int, page_size: int) -> int:
    """A page's CRC32 as `StoredPage` computes it, an allocation page's borrowed record zeroed."""
    start = number * page_size
    body = bytearray(data[start : start + page_size - 8])
    borrowed = data[start + BORROWED_SPACE_OFFSET]
    if borrowed and struct.unpack(">H", data[start : start + 2])[0] == ALLOC_PAGE_FORMAT_ID:
        body[BORROWED_SPACE_START : BORROWED_SPACE_START + borrowed] = bytes(borrowed)
    return zlib.crc32(body)
