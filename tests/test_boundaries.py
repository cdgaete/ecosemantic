"""The composition boundary, read mechanically from the source tree."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import ecosemantic

ROOTS_ON_PATH = [Path(entry) for entry in ecosemantic.__path__]
REPOSITORY = Path(__file__).resolve().parents[1]

COMMAND = "cli/__init__.py"
RUNNER = "serve/__init__.py"
ROOTS = (
    "local/__init__.py",
    COMMAND,
    "runs/worker.py",
    "runs/supervisor.py",
    "installs/sources.py",
    "installs/supervisor.py",
    "installs/worker.py",
)
INSTALL_ROOTS = ("installs/sources.py", "installs/supervisor.py")
LIBRARIES = ("bw2data", "bw2calc", "bw_processing", "olca_schema")
BRIGHTWAY = ("bw2data", "bw2calc", "bw_processing", "bw2parameters", "peewee")
OLCA_ENCODINGS = (
    "package/olca.py",
    "package/background.py",
    "package/jsonld.py",
    "package/base_writer.py",
    "package/wholeness.py",
    "package/base.py",
    "package/release.py",
)


def modules() -> dict[str, ast.Module]:
    return {
        path.relative_to(root).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
        for root in ROOTS_ON_PATH
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def names(tree: ast.Module, *prefixes: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith(prefixes) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.startswith(prefixes):
                return True
    return False


def inside_function(tree: ast.Module, node: ast.AST) -> bool:
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
    return False


def test_nothing_below_mcp_imports_backends() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if not path.startswith("backends/")
        and not path.startswith("databases/")
        and path not in ROOTS
        and names(tree, "ecosemantic.backends")
    ]
    assert offenders == [], offenders


def test_only_the_install_roots_name_the_databases() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if not path.startswith("databases/")
        and path not in INSTALL_ROOTS
        and names(tree, "ecosemantic.databases")
    ]
    assert offenders == [], offenders


def test_runs_names_nothing_from_mcp() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if path.startswith("runs/") and names(tree, "ecosemantic.mcp")
    ]
    assert offenders == [], offenders


def test_nothing_the_view_stands_on_names_the_view() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if not path.startswith("view/") and path != RUNNER and names(tree, "ecosemantic.view")
    ]
    assert offenders == [], offenders


def test_layout_is_pure() -> None:
    tree = modules()["layout/__init__.py"]
    offenders = names(
        tree, "ecosemantic.view", "ecosemantic.backends", "ecosemantic.mcp", "ecosemantic.runs"
    )
    assert not offenders


def test_no_mcp_module_binds_the_backends() -> None:
    bound = [
        path
        for path, tree in modules().items()
        if path.startswith("mcp/") and names(tree, "ecosemantic.backends")
    ]
    assert bound == [], bound


def test_the_lca_libraries_are_named_only_at_the_backend_boundary() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if not path.startswith("backends/")
        and not path.startswith("databases/")
        and path not in OLCA_ENCODINGS
        and names(tree, *LIBRARIES)
    ]
    assert offenders == [], offenders


def test_no_module_names_brightway() -> None:
    naming = sorted(path for path, tree in modules().items() if names(tree, *BRIGHTWAY))
    assert naming == [], naming


def test_the_lock_holds_nothing_of_brightway() -> None:
    lock = tomllib.loads((REPOSITORY / "uv.lock").read_text(encoding="utf-8"))
    held = {package["name"] for package in lock["package"]}
    assert held & {*BRIGHTWAY, "bw-processing", "ecosemantic-brightway"} == set()


def test_only_the_native_backend_names_duckdb() -> None:
    naming = sorted(
        path
        for path, tree in modules().items()
        if not path.startswith("backends/native/") and names(tree, "duckdb")
    )
    assert naming == [], naming


def test_pypardiso_is_imported_inside_the_function_that_uses_it() -> None:
    for path, tree in modules().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] == "pypardiso" for alias in node.names
            ):
                assert inside_function(tree, node), path


def literals(tree: ast.Module) -> list[tuple[int, tuple[str, ...]]]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
            continue
        if node.value.id != "Literal":
            continue
        items = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in items):
            found.append((node.lineno, tuple(item.value for item in items)))
    return found


def test_a_literal_vocabulary_is_spelled_once() -> None:
    spellings: dict[tuple[str, ...], list[str]] = {}
    for path, tree in modules().items():
        for line, values in literals(tree):
            spellings.setdefault(values, []).append(f"{path}:{line}")
    repeated = {values: at for values, at in spellings.items() if len(at) > 1}
    assert repeated == {}, repeated


def sequences(tree: ast.Module) -> list[tuple[int, frozenset[str]]]:
    """Every tuple, list or set of two or more strings that is not the inside of a Literal."""
    inside = {
        id(node.slice)
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Literal"
    }
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Tuple, ast.List, ast.Set)) or id(node) in inside:
            continue
        if len(node.elts) > 1 and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.elts
        ):
            found.append((node.lineno, frozenset(item.value for item in node.elts)))
    return found


def test_a_literal_vocabulary_is_not_spelled_again_as_a_sequence() -> None:
    vocabularies = {
        frozenset(values)
        for tree in modules().values()
        for _, values in literals(tree)
        if len(values) > 1
    }
    offenders = [
        f"{path}:{line}"
        for path, tree in modules().items()
        for line, values in sequences(tree)
        if values in vocabularies
    ]
    assert offenders == [], offenders


def test_no_mcp_module_names_the_telemetry_sdk() -> None:
    offenders = [
        path
        for path, tree in modules().items()
        if path.startswith("mcp/") and names(tree, "opentelemetry.sdk")
    ]
    assert offenders == [], offenders
