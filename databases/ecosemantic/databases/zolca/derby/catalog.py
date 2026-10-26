"""Derby's system catalogs, the four heaps `service.properties` names, and the SQL type of a column.

Each catalog heap's conglomerate record (`Heap.writeExternal_v10_2`, format id 467, the record it
keeps as id 6) carries that heap's own column count and the stored format id of every column, so
nothing here keeps a table of stored ids: they are read. A column's SQL type is the serialized
`TypeDescriptorImpl` in SYSCOLUMNS' COLUMNDATATYPE — its format id, its type id, the `writeUTF`
name, precision, scale, nullability and width — and the name is checked against the type id.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ecosemantic.databases.zolca.derby import records, values
from ecosemantic.databases.zolca.derby.pages import Container
from ecosemantic.errors import Invalid, NotSupported

SCHEMAS = "SysschemasIdentifier"
TABLES = "SystablesIdentifier"
CONGLOMERATES = "SysconglomeratesIdentifier"
COLUMNS = "SyscolumnsIdentifier"

SCHEMA = "APP"
CONGLOMERATE_FORMAT_ID = 467
CONGLOMERATE_RECORD_ID = 6
TYPE_DESCRIPTOR_FORMAT_ID = 14
TYPE_DESCRIPTOR_WIDTHS = 13
COLUMN_DATATYPE = 3

TYPE_IDS = {
    "BIGINT": 23,
    "BLOB": 442,
    "BOOLEAN": 16,
    "CHAR": 17,
    "CLOB": 446,
    "DATE": 32,
    "DOUBLE": 18,
    "INTEGER": 19,
    "SMALLINT": 22,
    "TIMESTAMP": 34,
    "VARCHAR": 25,
}


@dataclass(frozen=True)
class ColumnType:
    """The SQL type a column is stored as, from the serialized `TypeDescriptorImpl` it carries."""

    name: str
    type_id: int
    precision: int
    scale: int
    nullable: bool
    width: int


@dataclass(frozen=True)
class Column:
    """One column: its name, its number as `SYSCOLUMNS` counts it, its type and its stored id."""

    name: str
    number: int
    type: ColumnType
    stored_id: int


@dataclass(frozen=True)
class Table:
    """One table of schema `APP`: its name, its heap's conglomerate and its columns in order."""

    name: str
    conglomerate: int
    columns: tuple[Column, ...]


@dataclass(frozen=True)
class _Declared:
    """One column `SYS.SYSCOLUMNS` declares: its number, its name and the SQL type it names."""

    number: int
    name: str
    type: ColumnType


def tables(
    *, container_of: Callable[[int], Container], properties: Mapping[str, str]
) -> dict[str, Table]:
    """Every table of schema `APP`, its columns typed and its stored ids read from its own heap."""
    schema = _app_schema(container_of(_conglomerate(properties, SCHEMAS)))
    named = _app_tables(container_of(_conglomerate(properties, TABLES)), schema)
    heaps = _heaps(container_of(_conglomerate(properties, CONGLOMERATES)))
    declared = _declared(container_of(_conglomerate(properties, COLUMNS)), tables=named)
    found: dict[str, Table] = {}
    for table_id, name in named.items():
        conglomerate = heaps.get(table_id)
        if conglomerate is None:
            raise NotSupported(f"{name}: the catalog names no heap for the table")
        stored = _stored_ids(container_of(conglomerate))
        columns = sorted(declared.get(table_id, []), key=lambda column: column.number)
        if len(stored) != len(columns):
            raise Invalid(
                f"{name}: the catalog names {len(columns)} columns, the heap {len(stored)}"
            )
        found[name] = Table(
            name=name,
            conglomerate=conglomerate,
            columns=tuple(
                Column(
                    name=column.name,
                    number=column.number,
                    type=column.type,
                    stored_id=stored[at],
                )
                for at, column in enumerate(columns)
            ),
        )
    return found


def column_type(field: records.Field, *, where: str) -> ColumnType:
    """`TypeDescriptorImpl`: its format id, its type id, the `writeUTF` name and the widths."""
    if field.data is None:
        raise Invalid(f"{where}: the column's type descriptor is null")
    data = field.data
    if len(data) < 6 or struct.unpack(">H", data[0:2])[0] != TYPE_DESCRIPTOR_FORMAT_ID:
        raise NotSupported(f"{where}: the column's type is no `TypeDescriptorImpl`")
    type_id = struct.unpack(">H", data[2:4])[0]
    length = struct.unpack(">H", data[4:6])[0]
    name = values.modified_utf8(data[6 : 6 + length])
    at = 6 + length
    if len(data) != at + TYPE_DESCRIPTOR_WIDTHS:
        raise Invalid(f"{where}: the type descriptor is {len(data)} bytes")
    precision, scale, nullable, width = struct.unpack(">iiBi", data[at:])
    if TYPE_IDS.get(name) != type_id:
        raise NotSupported(f"{where}: the type descriptor names {name!r} at type id {type_id}")
    return ColumnType(
        name=name,
        type_id=type_id,
        precision=precision,
        scale=scale,
        nullable=bool(nullable),
        width=width,
    )


def _conglomerate(properties: Mapping[str, str], key: str) -> int:
    """The conglomerate `service.properties` names for one system catalog."""
    named = properties.get(key)
    if named is None:
        raise Invalid(f"service.properties names no {key}")
    return int(named)


def _stored_ids(container: Container) -> tuple[int, ...]:
    """A heap's column count and each column's stored format id, from its conglomerate record."""
    for page in container.live_pages():
        for record in records.records(page):
            if record.record_id == CONGLOMERATE_RECORD_ID:
                return _heap_descriptor(records.row(container, record)[0], member=container.member)
    raise Invalid(f"{container.member}: the heap holds no conglomerate record")


def _heap_descriptor(field: records.Field, *, member: str) -> tuple[int, ...]:
    """`Heap.writeExternal_v10_2`: format id 467, segment, container, count, then the stored ids."""
    if field.data is None:
        raise Invalid(f"{member}: the heap's conglomerate record is null")
    data = field.data
    if len(data) < 2 or struct.unpack(">H", data[0:2])[0] != CONGLOMERATE_FORMAT_ID:
        raise NotSupported(f"{member}: the heap conglomerate is of another format")
    count = struct.unpack(">i", data[14:18])[0]
    if len(data) < 18 + 2 * count:
        raise Invalid(f"{member}: the heap conglomerate names {count} columns it does not hold")
    return tuple(struct.unpack(">H", data[18 + 2 * at : 20 + 2 * at])[0] for at in range(count))


def _app_schema(container: Container) -> str:
    """The schema id `SYS.SYSSCHEMAS` gives `APP`."""
    stored = _stored_ids(container)
    for row in records.rows(container):
        if _text(container, row, stored, 1, where="SYSSCHEMAS.SCHEMANAME") == SCHEMA:
            return _text(container, row, stored, 0, where="SYSSCHEMAS.SCHEMAID")
    raise NotSupported(f"the database holds no schema {SCHEMA}")


def _app_tables(container: Container, schema: str) -> dict[str, str]:
    """`SYS.SYSTABLES`' table ids of one schema, by table name."""
    stored = _stored_ids(container)
    found: dict[str, str] = {}
    for row in records.rows(container):
        if _text(container, row, stored, 3, where="SYSTABLES.SCHEMAID") != schema:
            continue
        name = _text(container, row, stored, 1, where="SYSTABLES.TABLENAME")
        found[_text(container, row, stored, 0, where="SYSTABLES.TABLEID")] = name
    return found


def _heaps(container: Container) -> dict[str, int]:
    """`SYS.SYSCONGLOMERATES`' heap conglomerate number for each table id."""
    stored = _stored_ids(container)
    found: dict[str, int] = {}
    for row in records.rows(container):
        if _value(container, row, stored, 4, where="SYSCONGLOMERATES.ISINDEX") is not False:
            continue
        number = _number(container, row, stored, 2, where="SYSCONGLOMERATES.CONGLOMERATENUMBER")
        found[_text(container, row, stored, 1, where="SYSCONGLOMERATES.TABLEID")] = number
    return found


def _declared(container: Container, *, tables: Mapping[str, str]) -> dict[str, list[_Declared]]:
    """`SYS.SYSCOLUMNS`' declarations by table id, for the tables of schema `APP` alone."""
    stored = _stored_ids(container)
    found: dict[str, list[_Declared]] = {}
    for row in records.rows(container):
        reference = _text(container, row, stored, 0, where="SYSCOLUMNS.REFERENCEID")
        if reference not in tables:
            continue
        name = _text(container, row, stored, 1, where="SYSCOLUMNS.COLUMNNAME")
        number = _number(
            container, row, stored, 2, where=f"{tables[reference]}.{name} COLUMNNUMBER"
        )
        found.setdefault(reference, []).append(
            _Declared(
                number=number,
                name=name,
                type=column_type(row[COLUMN_DATATYPE], where=f"{tables[reference]}.{name}"),
            )
        )
    return found


def _value(
    container: Container,
    row: tuple[records.Field, ...],
    stored: tuple[int, ...],
    at: int,
    *,
    where: str,
) -> object:
    """One catalog field, decoded by the stored format id its heap's conglomerate record gives."""
    return records.value(container, row[at], stored[at], where=where)


def _number(
    container: Container,
    row: tuple[records.Field, ...],
    stored: tuple[int, ...],
    at: int,
    *,
    where: str,
) -> int:
    """One catalog field's number."""
    found = _value(container, row, stored, at, where=where)
    if not isinstance(found, int):
        raise Invalid(f"{where}: {found!r} is no number")
    return found


def _text(
    container: Container,
    row: tuple[records.Field, ...],
    stored: tuple[int, ...],
    at: int,
    *,
    where: str,
) -> str:
    """One catalog field's text."""
    found = _value(container, row, stored, at, where=where)
    if not isinstance(found, str):
        raise Invalid(f"{where}: {found!r} is no text")
    return found
