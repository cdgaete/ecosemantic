"""Read each dataset's ecoQuery URL from a release's Database Overview workbook."""

from __future__ import annotations

from pathlib import Path

from python_calamine import CalamineWorkbook

from ecosemantic.databases.ecoinvent.lcia import Sheet
from ecosemantic.errors import Invalid


def read_urls(workbook: Path, layout: Sheet) -> dict[str, str]:
    """The ecoQuery URL of each dataset, keyed by the native id the layout names, read as text."""
    rows = CalamineWorkbook.from_path(str(workbook)).get_sheet_by_name(layout.sheet).to_python()
    texts = [[str(cell) for cell in row] for row in rows]
    key_name, url_name = layout.columns
    found = next(
        (
            (index, row)
            for index, row in enumerate(texts)
            if all(name in row for name in layout.columns)
        ),
        None,
    )
    if found is None:
        seen = {cell for row in texts for cell in row}
        missing = [name for name in layout.columns if name not in seen]
        raise Invalid(f"{layout.sheet} has no header row naming {', '.join(missing)}")
    index, header = found
    key_column = header.index(key_name)
    url_column = header.index(url_name)
    urls: dict[str, str] = {}
    for row in texts[index + 1 :]:
        key = row[key_column]
        if not key:
            continue
        urls[key] = row[url_column]
    return urls
