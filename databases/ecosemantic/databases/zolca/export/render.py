"""openLCA's renderings of what its tables store: versions, instants, tags and category paths.

`Version.asString` splits a `VERSION` bigint into three 16-bit fields; `Util.mapBasicAttributes`
writes `lastChange` as `Instant.toString()` of epoch milliseconds and omits it at zero, and splits
`TAGS` on commas, trimming each part and dropping the blanks; `Categories.PathBuilder.pathOf`
walks a category's parents and joins their trimmed names with `/`.
"""

from __future__ import annotations

import datetime

from ecosemantic.databases.zolca.export.tables import Tables, foreign
from ecosemantic.errors import Invalid

VERSION_MAJOR = 32
VERSION_MINOR = 16
FIELD_MASK = 0xFFFF
CATEGORIES = "TBL_CATEGORIES"


def version(value: int) -> str:
    """`Version.asString`: a `VERSION`'s three 16-bit fields, as `00.00.000`."""
    return (
        f"{(value >> VERSION_MAJOR) & FIELD_MASK:02d}."
        f"{(value >> VERSION_MINOR) & FIELD_MASK:02d}."
        f"{value & FIELD_MASK:03d}"
    )


def instant(epoch_ms: int) -> str | None:
    """`Util`'s `Instant.toString()` of a `LAST_CHANGE`: none at 0, milliseconds as three digits.

    Epoch milliseconds hold nothing finer than a millisecond, so this writes no fraction or three
    digits and never the six or nine a nanosecond instant would.
    """
    if not epoch_ms:
        return None
    moment = datetime.datetime.fromtimestamp(epoch_ms // 1000, tz=datetime.UTC)
    millis = epoch_ms % 1000
    fraction = f".{millis:03d}" if millis else ""
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}{fraction}Z"
    )


def tags(text: str | None) -> list[str]:
    """`Util.mapBasicAttributes`: a `TAGS` column split on commas, each part trimmed."""
    return _split(text, separator=",")


def synonyms(text: str | None) -> list[str]:
    """`UnitWriter.mapSynonyms`: a `SYNONYMS` column split on semicolons, each part trimmed."""
    return _split(text, separator=";")


def category_path(tables: Tables, category_id: int | None) -> str | None:
    """`Categories.PathBuilder.pathOf`: the names up the parent chain, trimmed, joined by `/`."""
    if category_id is None:
        return None
    names: list[str] = []
    seen: set[int] = set()
    at: int | None = category_id
    while at is not None:
        if at in seen:
            raise Invalid(f"category {category_id}: its parent chain returns to {at}")
        seen.add(at)
        row = tables.row(CATEGORIES, at)
        names.append(str(row["NAME"]).strip())
        at = foreign(row, "F_CATEGORY")
    return "/".join(reversed(names)) or None


def _split(text: str | None, *, separator: str) -> list[str]:
    """One column's parts, each trimmed, the blank ones dropped."""
    if not text:
        return []
    return [part for part in (found.strip() for found in text.split(separator)) if part]
