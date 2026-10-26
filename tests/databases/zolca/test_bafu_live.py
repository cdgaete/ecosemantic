"""BAFU:2026 exported and imported whole: the records the package holds and the core's import.

Marked `zolca_live` and excluded from the gate; it reads the zolca `ECOSEMANTIC_BAFU_ZOLCA` names.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ecosemantic.databases.zolca.export import write
from ecosemantic.package.background import read_background

PROCESSES = 11_947
RECORDS = {
    "actors": 107,
    "currencies": 13,
    "dq_systems": 8,
    "flows": 14_407,
    "flow_properties": 23,
    "lcia_categories": 568,
    "lcia_methods": 46,
    "locations": 583,
    "parameters": 2,
    "processes": 11_947,
    "sources": 129,
    "unit_groups": 21,
}


@pytest.mark.zolca_live
def test_bafu_2026_exports_its_records_and_the_core_imports_every_process(tmp_path: Path) -> None:
    named = os.environ.get("ECOSEMANTIC_BAFU_ZOLCA")
    if named is None:
        pytest.fail("ECOSEMANTIC_BAFU_ZOLCA names no zolca to export")

    result = write.export(Path(named), tmp_path / "bafu-2026-v1.zip")
    imported = read_background(result.bundle, "bafu-2026-v1", foreground=frozenset())

    assert result.records == RECORDS
    assert imported.processes == PROCESSES
    assert imported.unlinked == []
