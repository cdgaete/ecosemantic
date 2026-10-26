"""A zolca's tables as the export reads them: rows by `ID`, children by foreign key.

openLCA keys every table by `ID`, a row's internal bigint, and points at another table with an
`F_*` column holding that id. `NULL` is no target everywhere except the provider column of
`TBL_EXCHANGES`, whose `0` is no provider (`JsonExport.handleProvider`); `REF_ID` is the entity's
`@id` and is never a foreign key.
"""

from __future__ import annotations

from collections.abc import Mapping

from ecosemantic.databases.zolca.derby.database import Database
from ecosemantic.errors import Invalid, NotFound

NO_PROVIDER = "F_DEFAULT_PROVIDER"


def foreign(row: Mapping[str, object], column: str) -> int | None:
    """A row's foreign key as an id: `None` where the column is null, and for a provider's `0`."""
    found = row[column]
    if found is None:
        return None
    if not isinstance(found, int):
        raise Invalid(f"{column}: {found!r} is no row id")
    if column == NO_PROVIDER and not found:
        return None
    return found


class Tables:
    """A zolca's tables, each read once: its rows by `ID`, indexed, and its children by a key."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._rows: dict[str, tuple[dict[str, object], ...]] = {}
        self._by_id: dict[str, dict[int, dict[str, object]]] = {}
        self._children: dict[tuple[str, str], dict[int, tuple[dict[str, object], ...]]] = {}

    def rows(self, table: str) -> tuple[dict[str, object], ...]:
        """Every row of one table, read from the database the first time the table is asked for."""
        if table not in self._rows:
            self._rows[table] = tuple(self.database.rows(table))
        return self._rows[table]

    def row(self, table: str, row_id: int) -> dict[str, object]:
        """The row of one table whose `ID` is `row_id`."""
        found = self.by_id(table).get(row_id)
        if found is None:
            raise NotFound(f"{table}: no row has ID {row_id}")
        return found

    def by_id(self, table: str) -> dict[int, dict[str, object]]:
        """The rows of one table by their `ID`, indexed the first time the table is asked for."""
        if table not in self._by_id:
            self._by_id[table] = {_id(row): row for row in self.rows(table)}
        return self._by_id[table]

    def children(self, table: str, column: str, value: int) -> tuple[dict[str, object], ...]:
        """The rows of one table whose `column` holds `value`, indexed the first time."""
        key = (table, column)
        if key not in self._children:
            index: dict[int, list[dict[str, object]]] = {}
            for row in self.rows(table):
                named = foreign(row, column)
                if named is not None:
                    index.setdefault(named, []).append(row)
            self._children[key] = {named: tuple(rows) for named, rows in index.items()}
        return self._children[key].get(value, ())


def _id(row: Mapping[str, object]) -> int:
    """A row's own `ID`."""
    found = row["ID"]
    if not isinstance(found, int):
        raise Invalid(f"a row's ID is {found!r}")
    return found
