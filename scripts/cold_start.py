"""How long a stdio start takes to answer `initialize` from a fresh `uv tool install` of a
build's six wheels, the way a chatbot starts the server: the tool and its command live in a
temporary directory, never the person's own; the first start after the install is reported
apart from the rest. Prints one JSON report.

    python scripts/cold_start.py DIST [--runs N] [--python VERSION]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

TELEMETRY_OFF = {"ECOSEMANTIC_TELEMETRY": "off"}


def tool(root: Path, dist: Path, python: str) -> Path:
    """The `ecosemantic` command `uv tool install` puts in a temporary tool directory, under the
    Python version named."""
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv is not on PATH")
    found = sorted(dist.glob("ecosemantic*-py3-none-any.whl"))
    app = [wheel for wheel in found if wheel.name.startswith("ecosemantic-")]
    if len(found) != 6 or len(app) != 1:
        sys.exit(f"{dist} holds no build of the six wheels")
    siblings = [str(wheel) for wheel in found if wheel not in app]
    bins = root / "bin"
    environ = {**os.environ, "UV_TOOL_DIR": str(root / "tools"), "UV_TOOL_BIN_DIR": str(bins)}
    command = [uv, "tool", "install", "--quiet", "--python", python, str(app[0])]
    for sibling in siblings:
        command += ["--with", sibling]
    subprocess.run(command, check=True, env=environ)
    return bins / ("ecosemantic.exe" if sys.platform == "win32" else "ecosemantic")


async def started(command: Path, data: Path, systems: Path) -> float:
    serving = StdioTransport(
        command=str(command),
        args=["serve", "--data-dir", str(data), "--systems-dir", str(systems)],
        env=TELEMETRY_OFF,
    )
    began = time.monotonic()
    async with Client(serving, timeout=120):
        return time.monotonic() - began


def main() -> int:
    parser = argparse.ArgumentParser(prog="cold_start")
    parser.add_argument("dist", type=Path)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--python", default=platform.python_version())
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        data, systems = root / "data", root / "systems"
        data.mkdir()
        systems.mkdir()
        command = tool(root, args.dist, args.python)
        seconds = [asyncio.run(started(command, data, systems)) for _ in range(args.runs + 1)]
    later = seconds[1:]
    print(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "first_s": round(seconds[0], 2),
                "runs": len(later),
                "median_s": round(statistics.median(later), 2),
                "max_s": round(max(later), 2),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
