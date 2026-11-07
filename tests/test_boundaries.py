"""The composition boundary, read mechanically from the source tree."""

from __future__ import annotations

import ast
import inspect
import pkgutil
import tomllib
from collections.abc import Callable
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
LAYERS = (
    ("errors", "relay"),
    ("model",),
    ("engine", "ports", "quantity"),
    ("geometry", "compute", "events"),
    ("routes", "scaling", "package", "tables"),
    ("troubles",),
    ("textmap", "layout", "backends", "databases"),
    ("mcp", "settings", "runs"),
    ("telemetry", "installs", "view", "bridge"),
    ("local", "serve"),
    ("workspace", "cli", "tray"),
    ("console",),
)
RANKS: dict[str, int] = {name: rank for rank, layer in enumerate(LAYERS) for name in layer}
SURFACES = {"view": "view/", "cli": "cli/", "workspace": "workspace/"}
CALLABLE_BELOW_MCP: dict[str, frozenset[str]] = {
    "view": frozenset(
        {
            "ecosemantic.errors.error_payload",
            "ecosemantic.errors.error_status",
            "ecosemantic.events.pump_installs",
            "ecosemantic.events.pump_runs",
            "ecosemantic.events.pump_storage",
            "ecosemantic.model.validation.anchors",
            "ecosemantic.package.package.unzip_package",
            "ecosemantic.package.package.zip_package",
            "ecosemantic.ports.types.open_trail",
            "ecosemantic.ports.types.trail",
            "ecosemantic.tables.results.write_contribution",
            "ecosemantic.tables.results.write_impact",
            "ecosemantic.tables.results.write_inventory",
        }
    ),
    "cli": frozenset(
        {
            "ecosemantic.backends.native.install.install",
            "ecosemantic.compute.accounts.account_from",
            "ecosemantic.compute.accounts.missing",
            "ecosemantic.errors.error_payload",
            "ecosemantic.package.background.read_background",
            "ecosemantic.package.manifest.read_manifest",
            "ecosemantic.package.model_package.import_model_package",
            "ecosemantic.package.release.build_release",
            "ecosemantic.package.working.build_working",
            "ecosemantic.package.working.foreground_processes",
            "ecosemantic.package.working.restore_systems",
            "ecosemantic.package.working.write_base_part",
            "ecosemantic.ports.types.source_credential",
            "ecosemantic.tables.reader.assemble",
            "ecosemantic.tables.results.write_contribution",
            "ecosemantic.tables.results.write_impact",
            "ecosemantic.tables.results.write_inventory",
        }
    ),
    "workspace": frozenset(),
}


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


def test_the_relay_imports_nothing_from_the_rest_of_the_core() -> None:
    """The bridge imports the relay alone, so no module of `relay/` names another subpackage."""
    naming = sorted(
        f"{path}:{line} {dotted}"
        for path, tree in modules().items()
        if path.startswith("relay/")
        for line, dotted in imported(tree)
        if dotted.split(".")[1] != "relay"
    )
    assert naming == [], naming


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


def imported(tree: ast.Module) -> list[tuple[int, str]]:
    """Each name an import of `ecosemantic` binds at run time, as its line and its dotted path.
    An import under `if TYPE_CHECKING:` binds nothing at run time."""
    typing_only = {
        id(child)
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
        for statement in node.body
        for child in ast.walk(statement)
    }
    found = []
    for node in ast.walk(tree):
        if id(node) in typing_only:
            continue
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found += [(node.lineno, f"{node.module}.{alias.name}") for alias in node.names]
    return [(line, dotted) for line, dotted in found if dotted.startswith("ecosemantic.")]


def rank(path: str) -> int:
    """The rank of the module at this path: its subpackage's; above every layer for the entry
    point beside the namespace, `__main__.py`, which runs the command and which nothing imports;
    and one below them all for the namespace's own `__init__.py`, which every import of a
    subpackage runs first. That module is a lazy facade: it reaches the modules behind its public
    names through `import_module` on first use, a dynamic import the AST does not read."""
    subpackage, _, inner = path.partition("/")
    if inner:
        return RANKS[subpackage]
    return len(LAYERS) if subpackage == "__main__.py" else -1


def test_every_subpackage_has_a_rank() -> None:
    assert set(RANKS) == {path.split("/")[0] for path in modules() if "/" in path}


def test_every_import_points_down_the_layers() -> None:
    upward = [
        f"{path}:{line} {dotted}"
        for path, tree in modules().items()
        for line, dotted in imported(tree)
        if dotted.split(".")[1] != path.split("/")[0] and RANKS[dotted.split(".")[1]] >= rank(path)
    ]
    assert upward == [], upward


def imported_below_mcp(prefix: str, kind: Callable[[object], bool]) -> dict[str, list[str]]:
    """Each object of this kind the modules under this path import from a subpackage ranked below
    `mcp`, by the dotted path the import names, with the `file:line` of each import."""
    found: dict[str, list[str]] = {}
    for path, tree in modules().items():
        if not path.startswith(prefix):
            continue
        for line, dotted in imported(tree):
            below = RANKS[dotted.split(".")[1]] < RANKS["mcp"]
            if below and kind(pkgutil.resolve_name(dotted)):
                found.setdefault(dotted, []).append(f"{path}:{line}")
    return found


def test_the_view_and_the_command_line_call_below_mcp_only_what_is_listed() -> None:
    unlisted: dict[str, list[str]] = {}
    unused: set[str] = set()
    for surface, prefix in SURFACES.items():
        called = imported_below_mcp(prefix, inspect.isfunction)
        listed = CALLABLE_BELOW_MCP[surface]
        unlisted |= {
            f"{surface} {dotted}": at for dotted, at in called.items() if dotted not in listed
        }
        unused |= {f"{surface} {dotted}" for dotted in listed - set(called)}
    assert unlisted == {}, unlisted
    assert unused == set(), unused


def test_no_surface_imports_a_module_from_below_mcp() -> None:
    """A call through a module's attribute is invisible to the import graph, so a surface imports
    from below `mcp` the functions it calls, never their module."""
    found = {
        f"{surface} {dotted}": at
        for surface, prefix in SURFACES.items()
        for dotted, at in imported_below_mcp(prefix, inspect.ismodule).items()
    }
    assert found == {}, found


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
    spellings: dict[frozenset[str], list[str]] = {}
    for path, tree in modules().items():
        for line, values in literals(tree):
            spellings.setdefault(frozenset(values), []).append(f"{path}:{line}")
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


TEST_DOUBLES = REPOSITORY / "tests"


def test_no_test_double_names_a_backend() -> None:
    doubles = sorted(TEST_DOUBLES.glob("memory_*.py")) + [TEST_DOUBLES / "dict_resolver.py"]
    offenders = [
        path.name
        for path in doubles
        if names(ast.parse(path.read_text(encoding="utf-8")), "ecosemantic.backends")
    ]
    assert offenders == [], offenders
