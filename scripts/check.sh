#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run vulture
uv run coverage run -m pytest
uv run coverage report