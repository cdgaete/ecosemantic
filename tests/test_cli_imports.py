"""What the commands load: the server comes with `serve` and with no other command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SERVER = ("fastmcp", "uvicorn", "starlette", "ecosemantic.view")


def loaded(tmp_path: Path, statement: str) -> list[str]:
    """The server's modules in `sys.modules` after a statement runs in a fresh interpreter."""
    written = tmp_path / "loaded.json"
    probe = "\n".join(
        [
            "import json, sys",
            statement,
            f"names = [name for name in {SERVER!r} if name in sys.modules]",
            f"open({str(written)!r}, 'w', encoding='utf-8').write(json.dumps(names))",
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
            "main(",
            f"    ['doctor', '--json', '--data-dir', {str(tmp_path)!r}, "
            f"'--systems-dir', {str(tmp_path)!r}]",
            ")",
        ]
    )
    assert loaded(tmp_path, statement) == []
