"""Record every tool the full server lists as the snapshot the tests compare against."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecosemantic.local import build_context
from ecosemantic.mcp.server import build_server
from tests.engine_fixture import install_fixtures
from tests.tool_snapshot import snapshot

RECORDED = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tools.json"


async def main() -> None:
    with tempfile.TemporaryDirectory() as work:
        data = Path(work) / "data"
        systems = Path(work) / "systems"
        data.mkdir()
        systems.mkdir()
        install_fixtures(data, Path(work))
        context = build_context(data, systems)
        try:
            tools = await snapshot(build_server(context))
        finally:
            context.close()
    RECORDED.parent.mkdir(parents=True, exist_ok=True)
    RECORDED.write_text(json.dumps(tools, indent=2, sort_keys=True) + "\n")
    print(f"{len(tools)} tools recorded in {RECORDED}")


if __name__ == "__main__":
    asyncio.run(main())
