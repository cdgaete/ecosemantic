"""One openLCA JSON-LD package from a zolca's tables, and the rows the package does not carry.

Every row of every table the export reads becomes a record — its own file where openLCA writes an
entity, or inline inside the record that owns it. A table the export does not read is named in the
report with the rows it holds, so nothing is dropped silently. The archive is written beside the
destination as `<name>.partial` and moved into place whole; a destination that exists is refused.
"""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.databases.zolca.export import entities
from ecosemantic.databases.zolca.export.tables import Tables
from ecosemantic.errors import Conflict

MARKER = "olca-schema.json"
MARKER_BYTES = '{"version": 2}'
PARTIAL = ".partial"

WRITTEN: dict[str, Callable[[Tables, dict[str, object]], dict[str, object]]] = {
    "TBL_ACTORS": entities.actor,
    "TBL_CURRENCIES": entities.currency,
    "TBL_DQ_SYSTEMS": entities.dq_system,
    "TBL_FLOWS": entities.flow,
    "TBL_FLOW_PROPERTIES": entities.flow_property,
    "TBL_IMPACT_CATEGORIES": entities.impact_category,
    "TBL_IMPACT_METHODS": entities.impact_method,
    "TBL_LOCATIONS": entities.location,
    "TBL_PROCESSES": entities.process,
    "TBL_SOURCES": entities.source,
    "TBL_UNIT_GROUPS": entities.unit_group,
}
FOLDERS = {
    "Actor": "actors",
    "Currency": "currencies",
    "DQSystem": "dq_systems",
    "Flow": "flows",
    "FlowProperty": "flow_properties",
    "ImpactCategory": "lcia_categories",
    "ImpactMethod": "lcia_methods",
    "Location": "locations",
    "Parameter": "parameters",
    "Process": "processes",
    "Source": "sources",
    "UnitGroup": "unit_groups",
}
INLINE = frozenset(
    {
        "TBL_ACTOR_LINKS",
        "TBL_DQ_INDICATORS",
        "TBL_DQ_SCORES",
        "TBL_EXCHANGES",
        "TBL_FLOW_PROPERTY_FACTORS",
        "TBL_IMPACT_FACTORS",
        "TBL_IMPACT_LINKS",
        "TBL_NW_FACTORS",
        "TBL_NW_SETS",
        "TBL_PARAMETERS",
        "TBL_PROCESS_DOCS",
        "TBL_REVIEWS",
        "TBL_SOURCE_LINKS",
        "TBL_UNITS",
    }
)
REASONS = {
    "TBL_ALLOCATION_FACTORS": "no record holds an allocation factor",
    "TBL_CATEGORIES": "only a category's name path is written, as its entities' category",
    "TBL_COMPLIANCE_DECLARATIONS": "no record holds a compliance declaration",
    "TBL_MAPPING_FILES": "no openLCA JSON-LD record holds a mapping file",
    "TBL_SOCIAL_ASPECTS": "no record holds a social aspect",
}
FILLED = (("TBL_LOCATIONS", "OTHER_PROPERTIES"), ("TBL_PROCESS_DOCS", "PRECEDING_DATASET"))


@dataclass(frozen=True)
class NotCarried:
    """A table, or one of its columns, whose rows the package does not carry, and why."""

    table: str
    rows: int
    reason: str


@dataclass(frozen=True)
class Exported:
    """The package one export wrote, its records by folder, and what it left out."""

    bundle: Path
    records: dict[str, int]
    not_carried: tuple[NotCarried, ...]


def export(zolca: Path, destination: Path) -> Exported:
    """Write one zolca's tables as an openLCA JSON-LD package at destination."""
    if destination.exists():
        raise Conflict(f"{destination} exists")
    tables = Tables(Database(zolca))
    partial = destination.with_name(destination.name + PARTIAL)
    records: dict[str, int] = {}
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MARKER, MARKER_BYTES)
        for table, entity in WRITTEN.items():
            for row in tables.rows(table):
                if _unwritable(table, row) is not None:
                    continue
                record = entity(tables, row)
                _write(archive, FOLDERS[str(record["@type"])], record, records)
        for row in tables.rows("TBL_PARAMETERS"):
            if row["SCOPE"] == entities.GLOBAL_SCOPE:
                _write(archive, FOLDERS["Parameter"], entities.parameter(tables, row), records)
    os.replace(partial, destination)
    return Exported(
        bundle=destination,
        records=records,
        not_carried=_not_carried(tables),
    )


def _write(
    archive: zipfile.ZipFile, folder: str, record: dict[str, object], records: dict[str, int]
) -> None:
    """One record under the folder and id `ZipWriter` gives it, and one more of its kind."""
    archive.writestr(f"{folder}/{record['@id']}.json", json.dumps(record, ensure_ascii=False))
    records[folder] = records.get(folder, 0) + 1


def _unwritable(table: str, row: Mapping[str, object]) -> str | None:
    """Why the record openLCA writes for this row is not one the package can hold, or None."""
    if table == "TBL_FLOW_PROPERTIES" and row["F_UNIT_GROUP"] is None:
        return "a flow property that names no unit group has no reference unit to write"
    return None


def _not_carried(tables: Tables) -> tuple[NotCarried, ...]:
    """The rows of every table and column the package does not carry, with the reason each."""
    found: list[NotCarried] = []
    for table in WRITTEN:
        unwritable: dict[str, int] = {}
        for row in tables.rows(table):
            why = _unwritable(table, row)
            if why is not None:
                unwritable[why] = unwritable.get(why, 0) + 1
        for why, held in unwritable.items():
            found.append(NotCarried(table=table, rows=held, reason=why))
    for name in tables.database.tables():
        if name in WRITTEN or name in INLINE:
            continue
        held = sum(1 for _ in tables.database.rows(name))
        if held:
            found.append(
                NotCarried(
                    table=name,
                    rows=held,
                    reason=REASONS.get(name, "no openLCA JSON-LD record holds this table's rows"),
                )
            )
    for table, column in FILLED:
        filled = sum(1 for row in tables.rows(table) if row[column] not in (None, b""))
        if filled:
            found.append(
                NotCarried(
                    table=f"{table}.{column}",
                    rows=filled,
                    reason=f"no openLCA JSON-LD field holds {column}",
                )
            )
    return tuple(sorted(found, key=lambda entry: entry.table))
