#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run ty check --python-platform win32 app/ecosemantic/tray
uv run ty check --python-platform win32 --extra-search-path . tests/tray/test_windows.py
uv run vulture
PYTHONWARNDEFAULTENCODING=1 uv run coverage run -m pytest
uv run coverage report