"""The Derby reader's imports: the standard library, `ecosemantic.errors`, and its own package."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ZOLCA = Path(__file__).parents[3] / "databases/ecosemantic/databases/zolca"
DERBY = ZOLCA / "derby"
EXPORT = ZOLCA / "export"
ALLOWED = ("ecosemantic.errors", "ecosemantic.databases.zolca.derby")
EXPORT_ALLOWED = (
    "ecosemantic.errors",
    "ecosemantic.databases.zolca.derby",
    "ecosemantic.databases.zolca.export",
    "olca_schema",
)


def modules(tree: ast.Module) -> set[str]:
    """Every dotted module a source file imports, relative imports aside."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_every_module_of_the_derby_reader_is_read() -> None:
    assert sorted(path.name for path in DERBY.glob("*.py")) == [
        "__init__.py",
        "catalog.py",
        "database.py",
        "log.py",
        "numbers.py",
        "pages.py",
        "records.py",
        "values.py",
    ]


def test_the_derby_reader_imports_the_standard_library_and_ecosemantic_errors_alone() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted(DERBY.glob("*.py")):
        for module in sorted(modules(ast.parse(path.read_text()))):
            if module.split(".")[0] in sys.stdlib_module_names:
                continue
            if module.startswith(ALLOWED):
                continue
            offenders.setdefault(path.name, []).append(module)
    assert offenders == {}


def test_every_module_of_the_export_is_read() -> None:
    assert sorted(path.name for path in EXPORT.glob("*.py")) == [
        "__init__.py",
        "entities.py",
        "geometry.py",
        "refs.py",
        "render.py",
        "tables.py",
        "write.py",
    ]


def test_the_export_imports_the_standard_library_olca_schema_and_the_reader_alone() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted(EXPORT.glob("*.py")):
        for module in sorted(modules(ast.parse(path.read_text()))):
            if module.split(".")[0] in sys.stdlib_module_names:
                continue
            if module.startswith(EXPORT_ALLOWED):
                continue
            offenders.setdefault(path.name, []).append(module)
    assert offenders == {}
