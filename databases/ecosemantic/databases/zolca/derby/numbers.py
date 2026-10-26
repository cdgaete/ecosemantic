"""Derby's compressed integers, the widths record ids, field lengths and counts are written in."""

from __future__ import annotations

from ecosemantic.errors import Invalid

INT_ONE_BYTE = 0x3F
INT_TWO_BYTE = 0x7F
LONG_TWO_BYTE = 0x3F
LONG_FOUR_BYTE = 0x7F


def read_int(data: bytes, at: int) -> tuple[int, int]:
    """Read one `CompressedNumber` int at `at`; return its value and the offset after it.

    One byte holds 0..63, two hold up to 16,383 with a `0x40` prefix, and four hold the
    rest, the first byte masked by 0x7F so that `C0 00 00 00` reads 2**30 rather than 0.
    """
    first = _byte(data, at)
    if first <= INT_ONE_BYTE:
        return first, at + 1
    if first <= INT_TWO_BYTE:
        return ((first & 0x3F) << 8) | _byte(data, at + 1), at + 2
    _need(data, at, 4)
    return (
        ((first & 0x7F) << 24)
        | (_byte(data, at + 1) << 16)
        | (_byte(data, at + 2) << 8)
        | _byte(data, at + 3),
        at + 4,
    )


def read_long(data: bytes, at: int) -> tuple[int, int]:
    """Read one `CompressedNumber` long at `at`; return its value and the offset after it.

    Two bytes hold 0..16,383 with a `0x00` prefix, four hold up to 2**30-1 with a `0x40`
    prefix masked by 0x3F, and eight hold the rest with a `0x80` prefix masked by 0x7F.
    """
    first = _byte(data, at)
    if first <= LONG_TWO_BYTE:
        return (first << 8) | _byte(data, at + 1), at + 2
    if first <= LONG_FOUR_BYTE:
        return (
            ((first & 0x3F) << 24)
            | (_byte(data, at + 1) << 16)
            | (_byte(data, at + 2) << 8)
            | _byte(data, at + 3),
            at + 4,
        )
    _need(data, at, 8)
    value = first & 0x7F
    for offset in range(1, 8):
        value = (value << 8) | _byte(data, at + offset)
    return value, at + 8


def _byte(data: bytes, at: int) -> int:
    _need(data, at, 1)
    return data[at]


def _need(data: bytes, at: int, width: int) -> None:
    """Refuse a compressed number that the data does not hold whole."""
    if at < 0 or at + width > len(data):
        raise Invalid(f"a compressed number at offset {at} runs past {len(data)} bytes")
