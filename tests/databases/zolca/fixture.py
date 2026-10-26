"""The synthetic Derby databases these tests read, and the rows `rows.json` records for them."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from ecosemantic.databases.zolca.derby import pages, records

FIXTURES = Path(__file__).parent / "fixtures"


def recorded(archive: str = "openlca.zip") -> dict[str, list[dict[str, object]]]:
    """The live rows `rows.json` records for one archive, by table name."""
    document = json.loads((FIXTURES / "rows.json").read_text())
    return document["databases"][archive]["tables"]


def containers(archive: str = "openlca.zip") -> dict[str, pages.Container]:
    """Every container of one archive, by its member in the zip."""
    with zipfile.ZipFile(FIXTURES / archive) as opened:
        return {
            name: pages.Container(member=name, data=opened.read(name))
            for name in opened.namelist()
            if name.startswith("seg0/") and name.endswith(".dat")
        }


def row_of(columns: int, *, holding: str) -> tuple[pages.Container, pages.Page, records.Record]:
    """The row of the fixture with `columns` columns that holds `holding`, and its page."""
    for container in containers().values():
        for page in container.live_pages():
            for record in records.records(page):
                fields = records.row(container, record)
                if len(fields) == columns and any(
                    holding.encode() in (field.data or b"") for field in fields
                ):
                    return container, page, record
    raise AssertionError(f"no row of {columns} columns holds {holding!r}")


def value(
    container: pages.Container, field: records.Field, stored_id: int, *, where: str
) -> object:
    """One field's value, as the reader decodes it: its bytes, or the chain it points at."""
    return records.value(container, field, stored_id, where=where)
