from __future__ import annotations

import json
from pathlib import Path

from fastmcp import FastMCP

from tests.tool_snapshot import snapshot

RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "tools.json"


async def test_every_tool_is_what_the_snapshot_recorded(full_server: FastMCP) -> None:
    assert await snapshot(full_server) == json.loads(RECORDED.read_text())
