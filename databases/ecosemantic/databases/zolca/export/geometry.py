"""The location geometry openLCA stores, as the GeoJSON its writer emits.

`TBL_LOCATIONS.GEODATA` is a gzip member of the `FeatureCollection` that openLCA's `geo.proto`
defines (`GeoJSON` packs and unpacks it, gzip found by its magic bytes); a location's geometry is
the *first* feature's geometry, which `LocationWriter.mapGeometry` writes as `{"type",
"coordinates"}`. The whole message is protobuf, so this reads varints and length-delimited fields.
"""

from __future__ import annotations

import gzip
import struct

from ecosemantic.errors import Invalid, NotSupported

GZIP_MAGIC = b"\x1f\x8b"
VARINT = 0
FIXED_64 = 1
LENGTH_DELIMITED = 2
FIXED_32 = 5
WIDTHS = {VARINT: 1, FIXED_64: 8, LENGTH_DELIMITED: 0, FIXED_32: 4}

FEATURE_OF_COLLECTION = 1
GEOMETRY_OF_FEATURE = 1
FEATURE_COLLECTION = {FEATURE_OF_COLLECTION: LENGTH_DELIMITED}
FEATURE = {GEOMETRY_OF_FEATURE: LENGTH_DELIMITED, 2: LENGTH_DELIMITED}
GEOMETRY = {1: LENGTH_DELIMITED, 2: LENGTH_DELIMITED, 3: LENGTH_DELIMITED, 4: LENGTH_DELIMITED}
GEOMETRY |= {5: LENGTH_DELIMITED, 6: LENGTH_DELIMITED, 7: LENGTH_DELIMITED}
ONE_POINT = {1: LENGTH_DELIMITED}
POINT = {1: FIXED_64, 2: FIXED_64}

ARMS = {
    1: "Point",
    2: "MultiPoint",
    3: "LineString",
    4: "MultiLineString",
    5: "Polygon",
    6: "MultiPolygon",
    7: "GeometryCollection",
}


def geojson(blob: bytes) -> dict[str, object] | None:
    """`GeoJSON.unpack` and `LocationWriter.mapGeometry`: a location's geometry as GeoJSON."""
    unpacked = gzip.decompress(blob) if blob.startswith(GZIP_MAGIC) else blob
    features = [
        payload
        for number, payload in _fields(unpacked, message=FEATURE_COLLECTION)
        if number == FEATURE_OF_COLLECTION
    ]
    if not features:
        return None
    geometries = [
        payload
        for number, payload in _fields(features[0], message=FEATURE)
        if number == GEOMETRY_OF_FEATURE
    ]
    if not geometries:
        return None
    return _geometry(geometries[0])


def _geometry(payload: bytes) -> dict[str, object] | None:
    """`GeoJSON.readGeometry`: the arm of the `Geometry` oneof a message holds, as GeoJSON."""
    arms = list(_fields(payload, message=GEOMETRY))
    if not arms:
        return None
    number, body = arms[-1]
    kind = ARMS[number]
    if number == 1:
        return {"type": kind, "coordinates": _point(body)}
    if number == 7:
        return {"type": kind, "geometries": [_geometry(inner) for inner in _parts(body)]}
    if number == 2:
        return {"type": kind, "coordinates": [_point(inner) for inner in _parts(body)]}
    if number == 3:
        return {"type": kind, "coordinates": _points(body)}
    if number == 4:
        return {"type": kind, "coordinates": [_points(inner) for inner in _parts(body)]}
    if number == 5:
        return {"type": kind, "coordinates": _rings(body)}
    return {"type": kind, "coordinates": [_rings(inner) for inner in _parts(body)]}


def _parts(payload: bytes) -> list[bytes]:
    """The repeated message `geo.proto` writes one per part, each part's own bytes."""
    return [body for _, body in _fields(payload, message=ONE_POINT)]


def _rings(payload: bytes) -> list[list[list[float]]]:
    """A `Polygon`'s rings of points."""
    return [_points(inner) for inner in _parts(payload)]


def _points(payload: bytes) -> list[list[float]]:
    """A `LineString`'s points."""
    return [_point(inner) for inner in _parts(payload)]


def _point(payload: bytes) -> list[float]:
    """A `Point`: its `x` and `y`, the two fixed 64-bit doubles proto3 defaults to zero."""
    found = [0.0, 0.0]
    for number, body in _fields(payload, message=POINT):
        found[number - 1] = struct.unpack("<d", body)[0]
    return found


def _fields(payload: bytes, *, message: dict[int, int]) -> list[tuple[int, bytes]]:
    """One message's fields, each refused when `geo.proto` gives that field no such wire type."""
    found: list[tuple[int, bytes]] = []
    at = 0
    while at < len(payload):
        key, at = _varint(payload, at)
        number, wire = key >> 3, key & 7
        if message.get(number) != wire:
            raise NotSupported(f"field {number} of wire type {wire} is none `geo.proto` defines")
        body, at = _body(payload, at=at, wire=wire)
        found.append((number, body))
    return found


def _body(payload: bytes, *, at: int, wire: int) -> tuple[bytes, int]:
    """One field's bytes: a varint, a fixed width, or a length and the bytes that follow."""
    if wire == LENGTH_DELIMITED:
        length, at = _varint(payload, at)
        if at + length > len(payload):
            raise Invalid(f"a field of {length} bytes runs past the message")
        return payload[at : at + length], at + length
    width = WIDTHS[wire]
    if at + width > len(payload):
        raise Invalid(f"a fixed {width}-byte field runs past the message")
    return payload[at : at + width], at + width


def _varint(payload: bytes, at: int) -> tuple[int, int]:
    """One proto3 varint and the offset after it."""
    value = 0
    shift = 0
    while at < len(payload):
        byte = payload[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
    raise Invalid("a varint runs past the message")
