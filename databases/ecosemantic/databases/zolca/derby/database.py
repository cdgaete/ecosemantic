"""A zolca read in place: its archive, its `service.properties`, its log and its tables' rows.

`Database` opens the archive read-only and never writes beside it. Construction refuses an
encrypted database and runs `log.check`, so no container is read from a database whose log holds
work after its checkpoint; `tables()` answers the four system catalogs' description of schema `APP`
once, and `rows()` reads one container at a time and releases it before the next.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

from ecosemantic.databases.zolca.derby import catalog, log, records
from ecosemantic.databases.zolca.derby.pages import Container
from ecosemantic.errors import Invalid, NotSupported

PROPERTIES = "service.properties"
ENCRYPTION = ("dataEncryption", "data_encryption")
CONTAINER = "seg0/c{conglomerate:x}.dat"


class Database:
    """An openLCA zolca: Derby's containers behind one zip, read from the archive in place.

    An encrypted database is refused before any container is read: Derby writes the property
    `dataEncryption` (`Attribute.DATA_ENCRYPTION`) and the spec names the attribute
    `data_encryption`, and either one set marks ciphertext the reader would take for values.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._properties = _properties(self._member(PROPERTIES).decode("latin-1"))
        encrypted = [key for key in ENCRYPTION if self._properties.get(key, "false") != "false"]
        if encrypted:
            raise NotSupported(f"{path}: the database is encrypted, {encrypted[0]} is set")
        log.check(self._log_members())
        self._tables: dict[str, catalog.Table] | None = None

    def tables(self) -> dict[str, catalog.Table]:
        """Every table of schema `APP`, described from the four system catalogs."""
        if self._tables is None:
            self._tables = catalog.tables(container_of=self._container, properties=self._properties)
        return self._tables

    def rows(self, table: str | catalog.Table) -> Iterator[dict[str, object]]:
        """Every row of one table, its columns by name, one container in memory at a time."""
        named = table if isinstance(table, catalog.Table) else self.tables()[table]
        container = self._container(named.conglomerate)
        for fields in records.rows(container):
            if len(fields) != len(named.columns):
                raise Invalid(
                    f"{named.name}: a row holds {len(fields)} fields, the table "
                    f"{len(named.columns)} columns"
                )
            yield {
                column.name: records.value(
                    container, field, column.stored_id, where=f"{named.name}.{column.name}"
                )
                for column, field in zip(named.columns, fields, strict=True)
            }

    def _container(self, conglomerate: int) -> Container:
        """One container of the database, read from the archive under the name Derby gives it."""
        member = CONTAINER.format(conglomerate=conglomerate)
        return Container(member=member, data=self._member(member))

    def _member(self, name: str) -> bytes:
        """One member of the archive, the zip closed again before it is answered."""
        with zipfile.ZipFile(self.path) as archive:
            try:
                return archive.read(name)
            except KeyError as error:
                raise Invalid(f"{self.path}: the archive holds no {name}") from error

    def _log_members(self) -> dict[str, bytes]:
        """The log's members: its control files and every log file the archive holds."""
        with zipfile.ZipFile(self.path) as archive:
            return {
                name: archive.read(name)
                for name in archive.namelist()
                if name.startswith("log/") and name.endswith((".ctrl", ".dat"))
            }


def _properties(text: str) -> dict[str, str]:
    """`service.properties`' keys and values, its comments and blank lines dropped."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith(("#", "!")):
            continue
        key, _, value = line.partition("=")
        found[key.strip()] = value.strip()
    return found
