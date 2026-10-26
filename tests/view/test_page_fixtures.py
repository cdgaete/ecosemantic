from __future__ import annotations

import json
from pathlib import Path

from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from scripts.record_page_fixtures import FIXTURES, record_fixtures


def shape(value: object) -> object:
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted({json.dumps(shape(item), sort_keys=True) for item in value})
    return None


async def test_every_committed_fixture_has_the_shape_of_a_fresh_recording(
    bundle_dir: Path, context: ServerContext, tmp_path: Path
) -> None:
    fresh = build_context(bundle_dir, tmp_path)
    recorded = await record_fixtures(fresh)
    fresh.close()
    committed = {path.stem: json.loads(path.read_text()) for path in FIXTURES.glob("*.json")}
    assert sorted(committed) == sorted(recorded)
    for name, payload in recorded.items():
        assert shape(committed[name]) == shape(payload), name
