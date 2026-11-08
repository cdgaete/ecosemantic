"""The tunnel's binary frames: a stream's body in chunks of at most 64 KiB, each frame carrying its
stream and whether it ends it."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ecosemantic.relay.errors import RelayError

CHUNK_BYTES = 65536
_HEADER = struct.Struct(">IB")


@dataclass(frozen=True)
class Chunk:
    """One frame of a stream's body: its stream, its bytes, and whether it is the last."""

    stream: int
    data: bytes
    end: bool


def pack(chunk: Chunk) -> bytes:
    """The binary frame that carries the chunk: its stream, the bit that ends it, then its body."""
    return _HEADER.pack(chunk.stream, 1 if chunk.end else 0) + chunk.data


def unpack(frame: bytes) -> Chunk:
    """The chunk a binary frame carries, refused when the frame is shorter than its header."""
    if len(frame) < _HEADER.size:
        raise RelayError(
            f"a frame of {len(frame)} bytes is shorter than its {_HEADER.size}-byte header"
        )
    stream, flags = _HEADER.unpack_from(frame)
    return Chunk(stream=stream, data=frame[_HEADER.size :], end=bool(flags & 1))


def chunks(stream: int, data: bytes, end: bool) -> list[Chunk]:
    """A stream's body split at 64 KiB, the last chunk alone carrying whether it ends the stream."""
    pieces = [data[at : at + CHUNK_BYTES] for at in range(0, len(data), CHUNK_BYTES)] or [b""]
    last = len(pieces) - 1
    return [
        Chunk(stream=stream, data=piece, end=end and at == last) for at, piece in enumerate(pieces)
    ]
