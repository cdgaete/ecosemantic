"""Compare a zolca's exported package with openLCA's own JSON-LD export of the same database.

A composition root::

    uv run python scripts/zolca/compare_with_export.py <bundle.zip> <openLCA-export.zip>

Both archives are read as parsed JSON, so Gson's escaping and number spelling make no difference.
A record is keyed by its `@type` and `@id`; a list compares as a multiset of its items, and a list
holding the same items in another order is counted under `list order` rather than as a difference.
A key present on one side only is a difference.

The rendering differences the spec names are counted under their own names and never reported as
differences: the schema marker file each archive writes, `creationDate`'s conversion through
America/Santiago, the 1899 rows whose value is the wall clock read at a fixed UTC−04:00, the
records only the bundle holds that nothing in the export references, and the export's file-store
members. A bundle-only record the export does reference is a difference.

One JSON document goes to stdout.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from zoneinfo import ZoneInfo

SANTIAGO = ZoneInfo("America/Santiago")
MINUS_FOUR = timezone(timedelta(hours=-4))
MARKERS = frozenset({"openlca.json", "olca-schema.json"})
ABSENT = "<absent>"
PLACEHOLDER = "1899-12-30"
SHOWN = 5
Key = tuple[str, str]


@dataclass
class _Field:
    """One differing field of a record type: its differing values and up to five examples."""

    values: int = 0
    shown: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _Survey:
    """What the walk of the bundle found, accumulated record by record."""

    equal: int = 0
    differing: dict[str, int] = field(default_factory=dict)
    fields: dict[str, dict[str, _Field]] = field(default_factory=dict)
    order: dict[str, int] = field(default_factory=dict)
    zone: int = 0
    placeholder: list[dict[str, object]] = field(default_factory=list)


def main() -> None:
    """Print the comparison of the two archives the arguments name, as one JSON document."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("export", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(compare(arguments.bundle, arguments.export), indent=2, ensure_ascii=False))


def compare(bundle: Path, export: Path) -> dict[str, object]:
    """The records two archives hold, every way they differ, and the named rendering differences."""
    with zipfile.ZipFile(bundle) as left, zipfile.ZipFile(export) as right:
        left_markers, left_records, left_store = _members(left)
        right_markers, right_records, right_store = _members(right)
        members, referenced, kinds = _index(right, right_records)
        survey = _Survey()
        unreferenced: dict[str, int] = {}
        mismatched: dict[str, int] = {}
        only_bundle: dict[str, int] = {}
        seen: set[Key] = set()
        for member in left_records:
            document = _read(left, member)
            key = _key(document)
            counterpart = members.get(key)
            if counterpart is None:
                only_bundle[key[0]] = only_bundle.get(key[0], 0) + 1
                found = mismatched if key[1] in referenced else unreferenced
                found[key[0]] = found.get(key[0], 0) + 1
                continue
            seen.add(key)
            _compare_documents(document, _read(right, counterpart), survey)
        held = Counter(key[0] for key in seen)
        only_export = {
            kind: count - held[kind] for kind, count in kinds.items() if count != held[kind]
        }
        return {
            "bundle": {
                "path": str(bundle),
                "bytes": bundle.stat().st_size,
                "records": len(left_records),
            },
            "export": {
                "path": str(export),
                "bytes": export.stat().st_size,
                "records": len(right_records),
            },
            "schema marker": {
                "bundle": [_marker(left, name) for name in left_markers],
                "export": [_marker(right, name) for name in right_markers],
            },
            "file store": {
                "bundle": _store(left_store),
                "export": _store(right_store),
            },
            "records": {
                "in both": len(seen),
                "equal": survey.equal,
                "differing": sum(survey.differing.values()),
                "only in the bundle": sum(only_bundle.values()),
                "only in the export": sum(only_export.values()),
            },
            "differing": _differing(survey),
            "unreferenced": dict(sorted(unreferenced.items())),
            "referenced only in the bundle": dict(sorted(mismatched.items())),
            "only in the export": dict(sorted(only_export.items())),
            "list order": dict(sorted(survey.order.items())),
            "creationDate zone": survey.zone,
            "creationDate 1899 placeholder": {
                "count": len(survey.placeholder),
                "rows": survey.placeholder,
            },
        }


def _members(archive: zipfile.ZipFile) -> tuple[list[str], list[str], list[str]]:
    """One archive's schema markers, entity records and file-store members, by member name."""
    names = [name for name in archive.namelist() if not name.endswith("/")]
    return (
        [name for name in names if name in MARKERS],
        [name for name in names if _is_record(name)],
        [name for name in names if name not in MARKERS and not _is_record(name)],
    )


def _is_record(name: str) -> bool:
    """Whether a member is one entity record: `<folder>/<id>.json`, with no member below it."""
    parts = name.split("/")
    return len(parts) == 2 and bool(parts[0]) and parts[1].endswith(".json")


def _index(
    archive: zipfile.ZipFile, records: list[str]
) -> tuple[dict[Key, str], set[str], dict[str, int]]:
    """Each record's member by its key, every id the archive references, its records by type."""
    members: dict[Key, str] = {}
    referenced: set[str] = set()
    kinds: dict[str, int] = {}
    for member in records:
        document = _read(archive, member)
        key = _key(document)
        members[key] = member
        referenced.update(_references(document))
        kinds[key[0]] = kinds.get(key[0], 0) + 1
    return members, referenced, kinds


def _read(archive: zipfile.ZipFile, member: str) -> dict[str, object]:
    """One member's parsed JSON document."""
    document: dict[str, object] = json.loads(archive.read(member))
    return document


def _marker(archive: zipfile.ZipFile, member: str) -> dict[str, object]:
    """One schema marker member and its parsed content."""
    return {"file": member, "content": json.loads(archive.read(member))}


def _store(members: list[str]) -> dict[str, object]:
    """The members outside the records and markers, counted by the name each ends with."""
    names: dict[str, int] = {}
    for member in members:
        names[member.rsplit("/", 1)[-1]] = names.get(member.rsplit("/", 1)[-1], 0) + 1
    return {"members": len(members), "by name": dict(sorted(names.items()))}


def _key(document: dict[str, object]) -> Key:
    """A record's key: its `@type` and `@id`."""
    return (str(document["@type"]), str(document["@id"]))


def _references(document: dict[str, object]) -> Iterator[str]:
    """Every id the document references: each object nested in it that carries `@type` and `@id`."""
    pending: list[object] = list(document.values())
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if "@type" in value and "@id" in value:
                yield str(value["@id"])
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def _compare_documents(
    bundle: dict[str, object], export: dict[str, object], survey: _Survey
) -> None:
    """Count one record's fields the two archives disagree on, the named differences apart."""
    kind, identifier = _key(bundle)
    fields: dict[str, _Field] = {}
    for name in sorted(set(bundle) | set(export)):
        if name not in export:
            _note(fields, name, name, identifier, bundle[name], ABSENT)
            continue
        if name not in bundle:
            _note(fields, name, name, identifier, ABSENT, export[name])
            continue
        left, right = bundle[name], export[name]
        if _canonical(left) == _canonical(right):
            continue
        _compare(left, right, name, name, identifier, fields, survey)
    if not fields:
        survey.equal += 1
        return
    survey.differing[kind] = survey.differing.get(kind, 0) + 1
    named = survey.fields.setdefault(kind, {})
    for path, found in fields.items():
        target = named.setdefault(path, _Field())
        target.values += found.values
        room = max(0, SHOWN - len(target.shown))
        target.shown.extend(found.shown[:room])


def _named(bundle_value: object, export_value: object, identifier: str, survey: _Survey) -> bool:
    """Whether a `creationDate` is the export's zone conversion or its 1899 placeholder.

    The placeholder names a value only where the export equals the wall clock read at a fixed
    UTC−04:00, the offset openLCA applies to the 1899 rows; any other `1899-12-30` value is a
    difference.
    """
    if not isinstance(bundle_value, str) or not isinstance(export_value, str):
        return False
    if _canonical(bundle_value) == _canonical(export_value):
        return True
    if _santiago(bundle_value) == export_value:
        survey.zone += 1
        return True
    if bundle_value.startswith(PLACEHOLDER) and _offset(bundle_value) == export_value:
        survey.placeholder.append(
            {"id": identifier, "bundle": bundle_value, "export": export_value}
        )
        return True
    return False


def _santiago(value: str) -> str | None:
    """A stored wall clock read in America/Santiago, as Java's `Instant.toString()` writes it."""
    moment = _wall_clock(value)
    if moment is None:
        return None
    return _instant(moment.replace(tzinfo=SANTIAGO).astimezone(UTC))


def _offset(value: str) -> str | None:
    """A stored wall clock read at a fixed UTC−04:00, as Java's `Instant.toString()` writes it."""
    moment = _wall_clock(value)
    if moment is None:
        return None
    return _instant(moment.replace(tzinfo=MINUS_FOUR).astimezone(UTC))


def _wall_clock(value: str) -> datetime | None:
    """A stored wall clock with no zone; a value of another shape carries none and answers None."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return None if moment.tzinfo is not None else moment


def _instant(moment: datetime) -> str:
    """Java's `Instant.toString()`: `Z`, and three or six fractional digits when there are any."""
    digits = ""
    if moment.microsecond % 1000:
        digits = f".{moment.microsecond:06d}"
    elif moment.microsecond:
        digits = f".{moment.microsecond // 1000:03d}"
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}{digits}Z"
    )


def _compare(
    bundle_value: object,
    export_value: object,
    path: str,
    at: str,
    identifier: str,
    fields: dict[str, _Field],
    survey: _Survey,
) -> None:
    """Count every difference the two values hold, at the deepest path that names it."""
    if path.rsplit(".", 1)[-1] == "creationDate" and _named(
        bundle_value, export_value, identifier, survey
    ):
        return
    if isinstance(bundle_value, dict) and isinstance(export_value, dict):
        for name in sorted(set(bundle_value) | set(export_value)):
            child = f"{path}.{name}"
            where = f"{at}.{name}"
            if name not in export_value:
                _note(fields, child, where, identifier, bundle_value[name], ABSENT)
            elif name not in bundle_value:
                _note(fields, child, where, identifier, ABSENT, export_value[name])
            else:
                _compare(
                    bundle_value[name], export_value[name], child, where, identifier, fields, survey
                )
        return
    if isinstance(bundle_value, list) and isinstance(export_value, list):
        _compare_lists(bundle_value, export_value, path, at, identifier, fields, survey)
        return
    if _canonical(bundle_value) != _canonical(export_value):
        _note(fields, path, at, identifier, bundle_value, export_value)


def _compare_lists(
    bundle_items: list[object],
    export_items: list[object],
    path: str,
    at: str,
    identifier: str,
    fields: dict[str, _Field],
    survey: _Survey,
) -> None:
    """Compare two lists as multisets of their items, an order-only difference counted apart."""
    held = Counter(_canonical(item) for item in bundle_items)
    other = Counter(_canonical(item) for item in export_items)
    if held == other:
        if [_canonical(item) for item in bundle_items] != [
            _canonical(item) for item in export_items
        ]:
            survey.order[path] = survey.order.get(path, 0) + 1
        return
    left = sorted(_leftover(bundle_items, other), key=_canonical)
    right = sorted(_leftover(export_items, held), key=_canonical)
    for mine, theirs in zip_longest(left, right, fillvalue=ABSENT):
        if mine is ABSENT or theirs is ABSENT:
            _note(fields, path, at, identifier, mine, theirs)
            continue
        _compare(mine, theirs, path, _instance(at, mine), identifier, fields, survey)


def _instance(at: str, item: object) -> str:
    """The path of one list item: the id it carries, or `[]` when it carries none."""
    if isinstance(item, dict) and "@id" in item:
        return f"{at}[{item['@id']}]"
    return f"{at}[]"


def _leftover(items: list[object], other: Counter[str]) -> list[object]:
    """The items the other side holds fewer times, in their own order."""
    held = Counter(other)
    left: list[object] = []
    for item in items:
        canonical = _canonical(item)
        if held.get(canonical, 0):
            held[canonical] -= 1
        else:
            left.append(item)
    return left


def _canonical(value: object) -> str:
    """One value's canonical JSON, which fixes escaping and key order for comparison."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _note(
    fields: dict[str, _Field],
    path: str,
    at: str,
    identifier: str,
    bundle_value: object,
    export_value: object,
) -> None:
    """Count one differing value at path, keeping at most five examples at the path it sits."""
    found = fields.setdefault(path, _Field())
    found.values += 1
    if len(found.shown) < SHOWN:
        found.shown.append(
            {"id": identifier, "path": at, "bundle": bundle_value, "export": export_value}
        )


def _differing(survey: _Survey) -> list[dict[str, object]]:
    """Each record type that differs, its fields, and the examples of each."""
    found: list[dict[str, object]] = []
    for kind in sorted(survey.fields):
        fields = survey.fields[kind]
        found.append(
            {
                "type": kind,
                "records": survey.differing[kind],
                "fields": [
                    {
                        "path": path,
                        "values": fields[path].values,
                        "examples": fields[path].shown,
                    }
                    for path in sorted(fields)
                ],
            }
        )
    return found


if __name__ == "__main__":
    main()
