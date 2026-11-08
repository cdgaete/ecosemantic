from __future__ import annotations

import pytest

from ecosemantic.relay.errors import RelayError
from ecosemantic.relay.frames import CHUNK_BYTES, Chunk, chunks, pack, unpack


def test_a_chunk_round_trips_through_its_frame() -> None:
    chunk = Chunk(stream=7, data=b"body", end=True)
    assert unpack(pack(chunk)) == chunk
    assert len(pack(Chunk(stream=1, data=b"", end=False))) == 5


def test_a_frame_shorter_than_its_header_is_a_relay_error() -> None:
    with pytest.raises(RelayError):
        unpack(b"\x00\x01")


def test_a_body_is_split_at_64_kib_and_only_its_last_chunk_ends() -> None:
    body = bytes(200_000)
    found = chunks(stream=3, data=body, end=True)
    assert [len(chunk.data) for chunk in found] == [65_536, 65_536, 65_536, 3_392]
    assert [chunk.end for chunk in found] == [False, False, False, True]
    assert {chunk.stream for chunk in found} == {3}
    assert b"".join(chunk.data for chunk in found) == body
    assert CHUNK_BYTES == 65_536


def test_an_empty_ending_body_is_one_ending_chunk() -> None:
    assert chunks(stream=1, data=b"", end=True) == [Chunk(stream=1, data=b"", end=True)]
