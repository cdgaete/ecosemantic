from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0"},
    },
}


async def test_the_console_command_answers_first_on_stdout(
    bundle_dir: Path, tmp_path: Path
) -> None:
    # the data directory comes from the environment
    environ = {**os.environ, "ECOSEMANTIC_DATA_DIR": str(bundle_dir)}
    served = await asyncio.create_subprocess_exec(
        str(Path(sys.executable).parent / "ecosemantic"),
        "serve",
        "--no-view",
        "--systems-dir",
        str(tmp_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=environ,
    )
    assert served.stdin is not None and served.stdout is not None
    served.stdin.write((json.dumps(INITIALIZE) + "\n").encode())
    await served.stdin.drain()
    first = await asyncio.wait_for(served.stdout.readline(), 120)
    served.stdin.close()
    await asyncio.wait_for(served.wait(), 30)
    answer = json.loads(first)
    assert answer["id"] == 0 and "serverInfo" in answer["result"]
