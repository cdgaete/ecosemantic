"""What the commands load: the server comes with `serve` and with no other command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ecosemantic.cli import main
from ecosemantic.model.entities import ProductSystem

SERVER = ("fastmcp", "uvicorn", "starlette", "ecosemantic.view")

NOISY_SERVER = """
import importlib.abc
import sys

MARKER = "the server loaded"
printed = []


class Noisy(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name in ("fastmcp", "uvicorn") and name not in printed:
            printed.append(name)
            print(MARKER)
        return None


sys.meta_path.insert(0, Noisy())


import ecosemantic.cli as cli


async def held(context, settings, systems_dir, meter_provider=None):
    return None


cli.run = held
sys.argv = ["ecosemantic", "serve", "--data-dir", {data!r}, "--systems-dir", {systems!r}]
from ecosemantic.console import main

sys.exit(main())
"""


def loaded(tmp_path: Path, statement: str) -> list[str]:
    """The server's modules in `sys.modules` after a statement runs in a fresh interpreter, which
    exits with the code it assigned to `code`."""
    written = tmp_path / "loaded.json"
    probe = "\n".join(
        [
            "import json, sys",
            "code = 0",
            statement,
            f"names = [name for name in {SERVER!r} if name in sys.modules]",
            f"open({str(written)!r}, 'w', encoding='utf-8').write(json.dumps(names))",
            "sys.exit(code)",
        ]
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert done.returncode == 0, done.stderr
    return json.loads(written.read_text(encoding="utf-8"))


def test_importing_the_cli_loads_no_server(tmp_path: Path) -> None:
    assert loaded(tmp_path, "import ecosemantic.cli") == []


def test_doctor_loads_no_server(tmp_path: Path) -> None:
    statement = "\n".join(
        [
            "from ecosemantic.cli import main",
            "code = main(",
            f"    ['doctor', '--json', '--data-dir', {str(tmp_path)!r}, "
            f"'--systems-dir', {str(tmp_path)!r}]",
            ")",
        ]
    )
    assert loaded(tmp_path, statement) == []


def test_import_loads_no_server(
    fixture_system_stored: ProductSystem, bundle_dir: Path, systems_dir: Path, tmp_path: Path
) -> None:
    zipped = tmp_path / "widget.zip"
    exported = main(
        [
            "export",
            "--data-dir",
            str(bundle_dir),
            "--systems-dir",
            str(systems_dir),
            "--id",
            str(fixture_system_stored.id),
            "--to",
            str(zipped),
        ]
    )
    assert exported == 0
    other = tmp_path / "other-systems"
    other.mkdir()
    statement = "\n".join(
        [
            "from ecosemantic.cli import main",
            "code = main(",
            f"    ['import', '--data-dir', {str(bundle_dir)!r}, '--systems-dir', {str(other)!r}, "
            f"'--from', {str(zipped)!r}]",
            ")",
        ]
    )
    assert loaded(tmp_path, statement) == []
    assert (other / str(fixture_system_stored.id)).is_dir()


def test_the_server_loads_beneath_the_redirect_to_stderr(tmp_path: Path) -> None:
    data = tmp_path / "data"
    systems = tmp_path / "systems"
    data.mkdir()
    systems.mkdir()
    environ = {**os.environ, "ECOSEMANTIC_TELEMETRY": "off"}
    environ.pop("ECOSEMANTIC_DATA_DIR", None)
    done = subprocess.run(
        [sys.executable, "-I", "-c", NOISY_SERVER.format(data=str(data), systems=str(systems))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environ,
    )
    assert done.returncode == 0, done.stderr
    assert "the server loaded" in done.stderr
    assert done.stdout == ""
