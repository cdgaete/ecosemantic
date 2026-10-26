"""What openLCA cannot hold, kept beside the JSON-LD entities in the package."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from ecosemantic.errors import NotFound
from ecosemantic.model.entities import Scenario
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef, SystemRef

SIDECAR_DIR = "ecosemantic"
LAYOUT_FILE = "layout.json"


class ProcessIdentity(BaseModel):
    id: uuid.UUID
    code: str


class ExchangeIdentity(BaseModel):
    id: uuid.UUID
    label: str


class Identities(BaseModel):
    """openLCA ids to the product system's own ids and references.

    An elementary flow is named by its flow id. A background input is named by its supplier:
    the provider process and the product flow together, as openLCA names it, because one
    product flow has as many providers as the database has producers of that product."""

    processes: dict[str, ProcessIdentity] = Field(default_factory=dict)
    exchanges: dict[str, ExchangeIdentity] = Field(default_factory=dict)
    elementary_flows: dict[str, ElementaryFlowRef] = Field(default_factory=dict)
    suppliers: dict[str, BackgroundRef] = Field(default_factory=dict)
    product_flows: dict[str, uuid.UUID] = Field(default_factory=dict)
    links: dict[str, SystemRef] = Field(default_factory=dict)
    locations: dict[str, str] = Field(default_factory=dict)
    parameter_units: dict[str, str] = Field(default_factory=dict)
    parameter_prefix: str


class ActivityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    code: str


class ProjectRecord(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    notes: str
    database: Database
    hash: str
    format: int = 1
    processes: list[ActivityRecord]


class Sidecar(BaseModel):
    product_system: ProjectRecord
    identities: Identities
    scenarios: list[Scenario]
    metadata: dict[uuid.UUID, dict[str, JsonValue]]


_FILES: dict[str, str] = {
    "product_system": "product_system.json",
    "identities": "identities.json",
    "scenarios": "scenarios.json",
    "metadata": "metadata.json",
}


def write_lines(root: Path, filename: str, lines: Iterable[str]) -> None:
    """Write one file of JSON lines under root/ecosemantic/, each line ended."""
    folder = root / SIDECAR_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8", newline="\n"
    )


def read_lines(root: Path, filename: str) -> list[str]:
    """The lines of a file under root/ecosemantic/ that carry something, or none when the file
    does not exist."""
    path = root / SIDECAR_DIR / filename
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_sidecar(root: Path, sidecar: Sidecar) -> None:
    """Write each part of the sidecar as one JSON file under root/ecosemantic/."""
    folder = root / SIDECAR_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for attr, filename in _FILES.items():
        value = getattr(sidecar, attr)
        adapter = TypeAdapter(Sidecar.model_fields[attr].annotation)
        (folder / filename).write_bytes(adapter.dump_json(value, indent=1))


def read_sidecar(root: Path) -> Sidecar:
    """Read the sidecar under root/ecosemantic/."""
    folder = root / SIDECAR_DIR
    if not folder.is_dir():
        raise NotFound(f"no {SIDECAR_DIR}/ folder in {root}")
    parts = {}
    for attr, filename in _FILES.items():
        adapter = TypeAdapter(Sidecar.model_fields[attr].annotation)
        parts[attr] = adapter.validate_json((folder / filename).read_bytes())
    return Sidecar(**parts)


def supplier_key(provider_id: str, flow_id: str) -> str:
    """The key under which Identities.suppliers holds a background input."""
    return f"{provider_id}:{flow_id}"
