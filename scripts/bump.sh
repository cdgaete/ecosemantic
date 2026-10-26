#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="${1:?usage: scripts/bump.sh <version>}"
for project in */pyproject.toml; do
  sed -i -E "s/^version = \"[^\"]+\"/version = \"$version\"/" "$project"
  sed -i -E "s/\"(ecosemantic(-[a-z]+)?(\[[a-z,]+\])?)==[^\"]+\"/\"\1==$version\"/g" "$project"
done
sed -i -E "s/^  \"version\": \"[^\"]+\"/  \"version\": \"$version\"/" page/package.json
uv lock
