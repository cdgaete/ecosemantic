"""What openLCA cannot hold, kept beside the JSON-LD entities in the package."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from ecosemantic.errors import NotFound, unreadable
from ecosemantic.files import write_whole
from ecosemantic.model.entities import Scenario
from ecosemantic.model.refs import BackgroundRef, Database, ElementaryFlowRef, SystemRef
from ecosemantic.package.olca import WrittenLognormal
from ecosemantic.ports.types import Layout

SIDECAR_DIR = "ecosemantic"
LAYOUT_FILE = "layout.json"
VERSION_HINT = "open this product system with the version of ecosemantic that wrote it"


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
    lognormals: dict[str, WrittenLognormal] = Field(default_factory=dict)
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
    """Write one file of JSON lines under root/ecosemantic/, each line ended, whole."""
    folder = root / SIDECAR_DIR
    folder.mkdir(parents=True, exist_ok=True)
    write_whole(folder / filename, "".join(line + "\n" for line in lines).encode("utf-8"))


def parsed_lines[M: BaseModel](path: Path, model: type[M], hint: str) -> list[M]:
    """Each non-blank line of a stored file validated as model, none when the file does not exist;
    a line this version cannot read raises Unavailable naming the file and the line."""
    if not path.is_file():
        return []
    parsed: list[M] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed.append(model.model_validate_json(line))
        except ValidationError as error:
            raise unreadable(f"{path.name} line {number}", error, hint) from error
    return parsed


def write_sidecar(root: Path, sidecar: Sidecar) -> None:
    """Write each part of the sidecar as one whole JSON file under root/ecosemantic/."""
    folder = root / SIDECAR_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for attr, filename in _FILES.items():
        value = getattr(sidecar, attr)
        adapter = TypeAdapter(Sidecar.model_fields[attr].annotation)
        write_whole(folder / filename, adapter.dump_json(value, indent=1))


def read_sidecar(root: Path) -> Sidecar:
    """Read the sidecar under root/ecosemantic/."""
    folder = root / SIDECAR_DIR
    if not folder.is_dir():
        raise NotFound(f"no {SIDECAR_DIR}/ folder in {root}")
    parts = {}
    for attr, filename in _FILES.items():
        adapter = TypeAdapter(Sidecar.model_fields[attr].annotation)
        try:
            parts[attr] = adapter.validate_json((folder / filename).read_bytes())
        except ValidationError as error:
            raise unreadable(filename, error, VERSION_HINT) from error
    return Sidecar(**parts)


def write_layout(root: Path, layout: Layout) -> None:
    """Write the layout under root/ecosemantic/ whole."""
    write_whole(root / SIDECAR_DIR / LAYOUT_FILE, layout.model_dump_json(indent=1).encode("utf-8"))


def read_layout(root: Path) -> Layout:
    """The layout under root/ecosemantic/, empty when the product system holds none."""
    path = root / SIDECAR_DIR / LAYOUT_FILE
    if not path.is_file():
        return Layout()
    try:
        return Layout.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise unreadable(
            path.name, error, f"remove {path}; the drawing places its cards again"
        ) from error


def supplier_key(provider_id: str, flow_id: str) -> str:
    """The key under which Identities.suppliers holds a background input."""
    return f"{provider_id}:{flow_id}"
