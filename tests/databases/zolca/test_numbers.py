"""Derby's compressed integers, at every width `CompressedNumber` writes them."""

from __future__ import annotations

import pytest

from ecosemantic.databases.zolca.derby import numbers
from ecosemantic.errors import Invalid


def test_a_compressed_int_of_one_byte_reads_its_value() -> None:
    assert numbers.read_int(b"\x00", at=0) == (0, 1)
    assert numbers.read_int(b"\x3f", at=0) == (63, 1)


def test_a_compressed_int_of_two_bytes_reads_its_value() -> None:
    assert numbers.read_int(b"\x40\x40", at=0) == (64, 2)
    assert numbers.read_int(b"\x7f\xff", at=0) == (16383, 2)


def test_a_compressed_int_of_four_bytes_reads_its_value() -> None:
    assert numbers.read_int(b"\x80\x00\x40\x00", at=0) == (16384, 4)
    assert numbers.read_int(b"\xc0\x00\x00\x00", at=0) == (2**30, 4)
    assert numbers.read_int(b"\xff\xff\xff\xff", at=0) == (2**31 - 1, 4)


def test_a_compressed_int_reads_on_from_the_offset_it_was_given() -> None:
    assert numbers.read_int(b"\xaa\x07\x00", at=1) == (7, 2)
    assert numbers.read_int(b"\xaa\xc0\x00\x00\x00", at=1) == (2**30, 5)


def test_a_compressed_long_of_two_bytes_reads_its_value() -> None:
    assert numbers.read_long(b"\x00\x00", at=0) == (0, 2)
    assert numbers.read_long(b"\x00\x3f", at=0) == (63, 2)
    assert numbers.read_long(b"\x00\x40", at=0) == (64, 2)
    assert numbers.read_long(b"\x3f\xff", at=0) == (16383, 2)


def test_a_compressed_long_of_four_bytes_reads_its_value() -> None:
    assert numbers.read_long(b"\x40\x00\x40\x00", at=0) == (16384, 4)
    assert numbers.read_long(b"\x7f\xff\xff\xff", at=0) == (2**30 - 1, 4)


def test_a_compressed_long_of_eight_bytes_reads_its_value() -> None:
    assert numbers.read_long(b"\x80\x00\x00\x00\x40\x00\x00\x00", at=0) == (2**30, 8)
    assert numbers.read_long(b"\xc0\x00\x00\x00\x00\x00\x00\x00", at=0) == (2**62, 8)
    assert numbers.read_long(b"\xff\xff\xff\xff\xff\xff\xff\xff", at=0) == (2**63 - 1, 8)


def test_a_compressed_long_reads_on_from_the_offset_it_was_given() -> None:
    assert numbers.read_long(b"\xaa\x00\x05", at=1) == (5, 3)


def test_a_number_that_runs_past_the_data_is_invalid() -> None:
    with pytest.raises(Invalid):
        numbers.read_int(b"\x80\x00", at=0)
    with pytest.raises(Invalid):
        numbers.read_long(b"\x80\x00\x00", at=0)
