"""The clean-environment check: the six wheels of a build, installed by path into an empty
environment with uv, with any dependency the build directory carries taken from it, serve over
scratch directories with no browser opened, answer `initialize` and list every tool of
the roster, and `import ecosemantic as es` opens a workspace over the same directories. Prints
one JSON report and exits 1 when a check fails.

    python scripts/clean_install.py DIST [--python VERSION]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from ecosemantic.mcp.server import ROSTER

TELEMETRY_OFF = {"ECOSEMANTIC_TELEMETRY": "off"}
OPENED = """
import json, sys
from pathlib import Path
import ecosemantic as es
with es.open(data_dir=Path(sys.argv[1]), systems_dir=Path(sys.argv[2])) as ws:
    print(json.dumps({"databases": [d.name for d in ws.list_databases().value],
                      "systems": len(ws.list_product_systems().value)}))
"""


def wheels(dist: Path) -> list[Path]:
    """The build's six wheels, refused when the directory holds another count."""
    found = sorted(dist.glob("ecosemantic*-py3-none-any.whl"))
    if len(found) != 6:
        sys.exit(f"{dist} holds {len(found)} ecosemantic wheels, not six")
    return found


def environment(root: Path, python: str, found: list[Path]) -> Path:
    """An empty environment with the wheels installed by path, a dependency the wheels' directory
    carries taken from it, and its interpreter."""
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv is not on PATH")
    venv = root / "venv"
    subprocess.run([uv, "venv", str(venv), "--python", python, "--quiet"], check=True)
    scripts = venv / ("Scripts" if sys.platform == "win32" else "bin")
    interpreter = scripts / ("python.exe" if sys.platform == "win32" else "python")
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(interpreter),
            "--quiet",
            "--find-links",
            str(found[0].parent),
            *map(str, found),
        ],
        check=True,
    )
    return interpreter


async def served(command: Path, data: Path, systems: Path) -> dict[str, object]:
    serving = StdioTransport(
        command=str(command),
        args=["serve", "--data-dir", str(data), "--systems-dir", str(systems), "--no-open"],
        env=TELEMETRY_OFF,
    )
    started = time.monotonic()
    async with Client(serving, timeout=120) as client:
        initialized = round(time.monotonic() - started, 2)
        tools = [tool.name for tool in await client.list_tools()]
    return {"initialize_s": initialized, "tools": len(tools), "roster": tools == list(ROSTER)}


def main() -> int:
    parser = argparse.ArgumentParser(prog="clean_install")
    parser.add_argument("dist", type=Path)
    parser.add_argument("--python", default=platform.python_version())
    args = parser.parse_args()
    found = wheels(args.dist)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        data, systems = root / "data", root / "systems"
        data.mkdir()
        systems.mkdir()
        interpreter = environment(root, args.python, found)
        command = interpreter.with_name(
            "ecosemantic.exe" if sys.platform == "win32" else "ecosemantic"
        )
        serving = asyncio.run(served(command, data, systems))
        opened = subprocess.run(
            [str(interpreter), "-c", OPENED, str(data), str(systems)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        workspace = json.loads(opened.stdout)
        version = subprocess.run(
            [str(interpreter), "-c", "import platform; print(platform.python_version())"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
    report = {
        "python": version,
        "wheels": [wheel.name for wheel in found],
        "serve": serving,
        "workspace": workspace,
        "passed": serving["roster"] and workspace == {"databases": [], "systems": 0},
    }
    print(json.dumps(report, indent=1))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
