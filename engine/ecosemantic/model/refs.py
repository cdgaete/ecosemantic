"""Background databases, exchange references, and the id each backend derives from a reference.

A native id is two UUIDs joined by an underscore: ecoinvent process and product, or openLCA
process and product flow. A process with several products is several references.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Scheme = Literal["ecoinvent", "olca"]

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PAIR_ID = re.compile(rf"^{_UUID}_{_UUID}$")


class Database(BaseModel):
    """A background database a product system pins, as the inventory backend reports it.
    `fingerprint` names the build: the SHA-256 of its compiled arrays, which an installed
    database always carries and a product system carries once it is stamped with one."""

    model_config = ConfigDict(frozen=True)

    name: str
    elementary_flows: str
    scheme: Scheme
    version: str
    system_model: str
    fingerprint: str | None = None


class BackgroundRef(BaseModel):
    """A process in a background database, by that database's native id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["background"] = "background"
    database: str
    id: str


class ForegroundRef(BaseModel):
    """A process in this product system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["foreground"] = "foreground"
    code: str


class SystemRef(BaseModel):
    """One unit of the functional unit of another product system on the same database, as the
    content hash names that system's state, under the case of that system it names or its base
    values when it names none. A stored document always carries the hash; the create_exchange
    tool pins the system's current one when a caller leaves it out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["system"] = "system"
    product_system_id: uuid.UUID
    at_hash: str | None = None
    case: str | None = None


class LinkedProcessRef(BaseModel):
    """A process inside a linked product system, as a result names it: the system, the hash it
    was calculated at, and the process's code there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["linked"] = "linked"
    product_system_id: uuid.UUID
    at_hash: str
    code: str


class ElementaryFlowRef(BaseModel):
    """An elementary flow, by the elementary-flow database's native id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["elementary_flow"] = "elementary_flow"
    database: str
    id: str


ExchangeInput = Annotated[
    BackgroundRef | ForegroundRef | SystemRef | ElementaryFlowRef,
    Field(discriminator="kind", json_schema_extra={"type": "object"}),
]


def slug(text: str, separator: str) -> str:
    """A name in lowercase letters and digits, each run of anything else as one separator and
    none at either end."""
    return re.sub(r"[^a-z0-9]+", separator, text.lower()).strip(separator)


def keygen(*names: str) -> str:
    """openLCA's name-based id: an MD5 UUID over the lowercased names joined by '/'."""
    path = "/".join(name.strip() for name in names).lower()
    digest = hashlib.md5(path.encode("utf-8"), usedforsecurity=False).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def split_native_id(native_id: str) -> tuple[str, str]:
    """The two UUIDs a native id joins with an underscore."""
    if not _PAIR_ID.match(native_id):
        raise ValueError(f"not a native id of two UUIDs: {native_id!r}")
    first, second = native_id.split("_")
    return first, second


def olca_process_id(scheme: Scheme, native_id: str) -> str:
    """The openLCA process id for a background reference."""
    if scheme == "ecoinvent":
        return keygen(*split_native_id(native_id))
    return split_native_id(native_id)[0]


def olca_product_flow_id(scheme: Scheme, native_id: str) -> str:
    """The openLCA product flow id for a background reference."""
    return split_native_id(native_id)[1]


def olca_elementary_flow_id(
    scheme: Scheme, native_id: str, mapping: dict[str, str] | None = None
) -> str:
    """The openLCA elementary flow id, through the shipped mapping where one applies."""
    if mapping is not None and native_id in mapping:
        return mapping[native_id]
    return native_id
