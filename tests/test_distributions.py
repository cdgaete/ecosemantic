"""What each distribution imports, what it declares, the order between them, and their one
version."""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from collections.abc import Mapping
from functools import cache
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest
from packaging.requirements import Requirement

REPOSITORY = Path(__file__).resolve().parents[1]
LEVELS = {
    "ecosemantic-engine": 1,
    "ecosemantic-core": 2,
    "ecosemantic-mcp": 3,
    "ecosemantic-view": 4,
    "ecosemantic-databases": 4,
    "ecosemantic": 5,
}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@cache
def members() -> dict[str, dict]:
    root = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    found = {}
    for directory in root["tool"]["uv"]["workspace"]["members"]:
        project = tomllib.loads(
            (REPOSITORY / directory / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        required = [Requirement(line) for line in project.get("dependencies", [])]
        for extra in project.get("optional-dependencies", {}).values():
            required += [Requirement(line) for line in extra]
        found[project["name"]] = {
            "directory": REPOSITORY / directory,
            "version": project["version"],
            "requires": required,
            "extras": {
                name: [Requirement(line) for line in lines]
                for name, lines in project.get("optional-dependencies", {}).items()
            },
        }
    return found


@cache
def owners() -> dict[str, str]:
    """Each module and package of the namespace, by dotted name, and the distribution that
    ships it."""
    owned = {}
    for name, member in members().items():
        source = member["directory"] / "ecosemantic"
        for path in source.rglob("*.py"):
            parts = path.relative_to(source.parent).with_suffix("").parts
            dotted = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            owned[dotted] = name
    return owned


def owner(module: str) -> str | None:
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        found = owners().get(".".join(parts[:end]))
        if found is not None:
            return found
    return None


def imported(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def imports() -> list[tuple[str, Path, str]]:
    return [
        (name, path, module)
        for name, member in members().items()
        for path in sorted((member["directory"] / "ecosemantic").rglob("*.py"))
        for module in imported(path)
    ]


def declared(name: str) -> set[str]:
    """The distributions a member's declarations bring in: its own requirements, and the
    dependencies of the extra's of a sibling it declares."""
    reached = {canonical(requirement.name) for requirement in members()[name]["requires"]}
    for requirement in members()[name]["requires"]:
        sibling = members().get(canonical(requirement.name))
        if sibling is None:
            continue
        for extra in requirement.extras:
            reached |= {canonical(r.name) for r in sibling["extras"].get(extra, [])}
    return reached


def undeclared(providers: Mapping[str, list[str]]) -> list[str]:
    missing = []
    for name, path, module in imports():
        top = module.split(".")[0]
        if top in ("ecosemantic", "__future__") or top in sys.stdlib_module_names:
            continue
        if canonical(top) in declared(name):
            continue
        provided = {canonical(d) for d in providers.get(top, [])}
        if not provided & declared(name):
            missing.append(f"{path.relative_to(REPOSITORY)}: {module}")
    return missing


def test_every_third_party_import_is_declared() -> None:
    assert undeclared(packages_distributions()) == []


def test_a_marker_declared_dependency_counts_as_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = packages_distributions()
    without_pypardiso = {top: deps for top, deps in providers.items() if top != "pypardiso"}
    monkeypatch.setattr(
        "tests.test_distributions.packages_distributions", lambda: without_pypardiso
    )
    assert undeclared(packages_distributions()) == []


def test_every_sibling_import_is_declared_and_points_down() -> None:
    wrong = []
    for name, path, module in imports():
        if not module.startswith("ecosemantic."):
            continue
        target = owner(module)
        if target is None or target == name:
            continue
        declared = {canonical(r.name) for r in members()[name]["requires"]}
        if canonical(target) not in declared or LEVELS[target] >= LEVELS[name]:
            wrong.append(f"{path.relative_to(REPOSITORY)}: {module} ({name} -> {target})")
    assert wrong == [], wrong


def test_every_member_has_a_level() -> None:
    assert set(members()) == set(LEVELS)


def test_one_version_and_every_sibling_pinned_to_it() -> None:
    versions = {member["version"] for member in members().values()}
    versions.add(
        json.loads((REPOSITORY / "page" / "package.json").read_text(encoding="utf-8"))["version"]
    )
    assert len(versions) == 1, versions
    (version,) = versions
    loose = [
        f"{name} requires {requirement}"
        for name, member in members().items()
        for requirement in member["requires"]
        if requirement.name in members() and str(requirement.specifier) != f"=={version}"
    ]
    assert loose == [], loose


def test_only_the_command_s_distribution_ships_the_namespace_s_init() -> None:
    shipped = [
        name
        for name, member in members().items()
        if (member["directory"] / "ecosemantic" / "__init__.py").exists()
    ]
    assert shipped == ["ecosemantic"]
    source = members()["ecosemantic"]["directory"] / "ecosemantic" / "__init__.py"
    text = source.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = [ast.unparse(n) for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
    assert imported == ["from typing import TYPE_CHECKING"]
    # the one form of the pkgutil namespace a type checker reads as a namespace
    assert '__path__ = __import__("pkgutil").extend_path(__path__, __name__)' in text
