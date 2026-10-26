"""The append-only change log: entity-level diffs chained on content hashes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, JsonValue

from ecosemantic.errors import Invalid
from ecosemantic.model.canonical import content_hash, significant
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.sidecar import read_lines, write_lines
from ecosemantic.ports.types import Change, Entity, LogEntry, Source

LOG_FILE = "log.jsonl"
_ACTIVITY_FIELDS = (
    "code",
    "name",
    "unit",
    "location",
    "reference_product",
    "comment",
    "metadata",
)
_EXCHANGE_FIELDS = ("type", "name", "amount", "unit", "input", "formula", "comment", "uncertainty")
_PARAMETER_FIELDS = ("value", "formula", "unit", "description")
_PROJECT_FIELDS = ("name", "description", "notes", "database", "reference_process")


def _dump(value: object) -> JsonValue | None:
    if isinstance(value, BaseModel):
        return _dump(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_dump(v) for v in value]
    if isinstance(value, float):
        return float(significant(value))
    if value is None or isinstance(value, str | int | bool):
        return value
    raise Invalid(f"cannot record a {type(value).__name__} in the log")


def _updates(
    entity: Entity, entity_id: str, before: BaseModel, after: BaseModel, fields: tuple[str, ...]
) -> list[Change]:
    return [
        Change(
            op="update",
            entity=entity,
            id=entity_id,
            field=f,
            before=_dump(getattr(before, f)),
            after=_dump(getattr(after, f)),
        )
        for f in fields
        if _dump(getattr(before, f)) != _dump(getattr(after, f))
    ]


def _by_key(
    entity: Entity,
    before: dict[str, BaseModel],
    after: dict[str, BaseModel],
    fields: tuple[str, ...],
) -> list[Change]:
    changes: list[Change] = []
    for key in sorted(set(before) | set(after)):
        if key not in after:
            changes.append(Change(op="delete", entity=entity, id=key))
        elif key not in before:
            changes.append(Change(op="add", entity=entity, id=key, after=_dump(after[key])))
        else:
            changes.extend(_updates(entity, key, before[key], after[key], fields))
    return changes


def diff_product_systems(before: ProductSystem | None, after: ProductSystem) -> list[Change]:
    """Every entity added, deleted or changed between two states."""
    if before is None:
        return [Change(op="add", entity="product_system", id=str(after.id))]
    changes = _updates("product_system", str(after.id), before, after, _PROJECT_FIELDS)
    changes += _by_key(
        "process",
        {str(a.id): a for a in before.processes},
        {str(a.id): a for a in after.processes},
        _ACTIVITY_FIELDS,
    )
    changes += _by_key(
        "exchange",
        {str(e.id): e for a in before.processes for e in a.exchanges},
        {str(e.id): e for a in after.processes for e in a.exchanges},
        _EXCHANGE_FIELDS,
    )
    changes += _by_key(
        "parameter",
        {p.name: p for p in before.parameters},
        {p.name: p for p in after.parameters},
        _PARAMETER_FIELDS,
    )
    changes += _by_key(
        "case",
        {c.name: c for c in before.cases},
        {c.name: c for c in after.cases},
        ("description", "values"),
    )
    changes += _by_key(
        "scenario",
        {s.name: s for s in before.scenarios},
        {s.name: s for s in after.scenarios},
        ("description", "overrides", "base_hash"),
    )
    return changes


def next_entry(
    log: list[LogEntry],
    actor: Actor,
    source: Source,
    before: ProductSystem | None,
    after: ProductSystem,
    message: str,
    now: datetime | None = None,
) -> LogEntry:
    """The entry that takes the log from its last state to `after`; before must be that state."""
    last = log[-1] if log else None
    base_hash = None if before is None else content_hash(before)
    if (last is None and base_hash is not None) or (
        last is not None and last.result_hash != base_hash
    ):
        raise Invalid("the write is based on a state that is not the log's last state")
    return LogEntry(
        seq=(last.seq + 1) if last else 1,
        timestamp=now or datetime.now(UTC),
        actor=actor,
        source=source,
        base_hash=base_hash,
        result_hash=content_hash(after),
        changes=diff_product_systems(before, after),
        message=message,
    )


def verify_chain(log: list[LogEntry]) -> None:
    """Raise unless each base hash is the previous result hash and seq counts from one."""
    previous: LogEntry | None = None
    for entry in log:
        expected_seq = 1 if previous is None else previous.seq + 1
        expected_base = None if previous is None else previous.result_hash
        if entry.seq != expected_seq or entry.base_hash != expected_base:
            raise Invalid(f"log entry {entry.seq} breaks the chain")
        previous = entry


def write_log(root: Path, log: list[LogEntry]) -> None:
    """Write the log as JSON lines under root/ecosemantic/."""
    write_lines(root, LOG_FILE, (entry.model_dump_json() for entry in log))


def read_log(root: Path) -> list[LogEntry]:
    """The log under root/ecosemantic/, or an empty list when the file does not exist."""
    entries = [LogEntry.model_validate_json(line) for line in read_lines(root, LOG_FILE)]
    verify_chain(entries)
    return entries
