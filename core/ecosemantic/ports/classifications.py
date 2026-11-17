"""The classification and method trees the explorer browses, built from a catalog's rows."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Literal

from ecosemantic.errors import Invalid, NotFound
from ecosemantic.model.entities import Method
from ecosemantic.ports.types import (
    ClassificationNode,
    ClassificationScheme,
    ClassificationValue,
    MethodCategory,
    MethodFamily,
)

CODE_LEVELS: dict[str, tuple[int, ...]] = {"ISIC": (2, 3), "CPC": (1, 2, 3, 4), "HS": (2, 4)}

ISIC_STRUCTURE = Path(__file__).parent / "data" / "isic_rev4_english_structure.csv"

SchemeKind = Literal["code", "path", "flat"]


@cache
def isic_names() -> dict[str, str]:
    """The names ISIC Rev.4 publishes for its divisions and groups, in English, by code, read once
    from the structure the package carries."""
    with ISIC_STRUCTURE.open(newline="", encoding="ascii") as handle:
        rows = csv.DictReader(handle)
        return {
            row["Code"]: row["Description"].strip()
            for row in rows
            if len(row["Code"]) in CODE_LEVELS["ISIC"]
        }


def _rest(scheme: str, value: ClassificationValue) -> str:
    """What a stored value holds after its scheme's name; a value of another scheme is refused."""
    prefix = f"{scheme}: "
    if not value.value.startswith(prefix):
        raise Invalid(f"classification value {value.value!r} is not under scheme {scheme!r}")
    return value.value.removeprefix(prefix)


def _code_key(scheme: str) -> str | None:
    """The key of `CODE_LEVELS` the scheme's name starts with, the first it does; none when it
    starts with no key."""
    return next((key for key in CODE_LEVELS if scheme.startswith(key)), None)


def _coded(rest: str) -> bool:
    """Whether a rest begins with one or more digits followed by a colon."""
    code, colon, _ = rest.partition(":")
    return bool(colon) and code.isdigit()


def _chain(code: str, levels: Sequence[int]) -> list[str]:
    """The codes from the top of a code tree down to the code: its prefixes at the scheme's
    levels shorter than it, then the code itself."""
    prefixes = [code[:level] for level in levels if level < len(code)]
    return [*prefixes, code]


def scheme_kind(scheme: str, values: Sequence[ClassificationValue]) -> SchemeKind:
    """Which shape the scheme's stored values nest in: by code prefix, by path segment, or one
    level. The code rule is read first, so a code scheme stays one when a value's name holds a
    `/`."""
    rests = [_rest(scheme, value) for value in values]
    if rests and _code_key(scheme) is not None and all(_coded(rest) for rest in rests):
        return "code"
    if any("/" in rest for rest in rests):
        return "path"
    return "flat"


def _levels_key(scheme: str) -> str:
    """The key of `CODE_LEVELS` the scheme's name starts with; a scheme starting with none is
    refused."""
    key = _code_key(scheme)
    if key is None:
        raise Invalid(f"code scheme {scheme!r} starts with no key of CODE_LEVELS")
    return key


def _rank(scheme: str, kind: SchemeKind) -> int:
    """Where a scheme falls in the explorer's order: a code scheme by the index of the key its
    name starts with, then path schemes, then flat ones."""
    if kind == "code":
        return list(CODE_LEVELS).index(_levels_key(scheme))
    return len(CODE_LEVELS) + (1 if kind == "path" else 2)


def ordered_schemes(
    schemes: Sequence[ClassificationScheme], kinds: Mapping[str, SchemeKind]
) -> list[ClassificationScheme]:
    """The schemes in the order the explorer lists them: code schemes by the table's key order,
    then path ones, then flat ones, each by processes covered and then by name."""
    return sorted(
        schemes,
        key=lambda scheme: (
            _rank(scheme.scheme, kinds[scheme.scheme]),
            -scheme.processes,
            scheme.scheme,
        ),
    )


def _record(
    scheme: str,
    keyed: dict[str, ClassificationValue],
    node: str,
    value: ClassificationValue,
) -> None:
    """Record a stored value as the node it is, refusing two stored values that share that node."""
    found = keyed.get(node)
    if found is not None:
        raise Invalid(
            f"two classification values under {scheme!r} share {node!r}: "
            f"{found.value!r} and {value.value!r}"
        )
    keyed[node] = value


def _children(parents: Mapping[str, str | None]) -> tuple[dict[str, list[str]], list[str]]:
    """The child ids of every node, and the ids no other node holds."""
    children: dict[str, list[str]] = {node: [] for node in parents}
    roots: list[str] = []
    for node, parent in parents.items():
        if parent is None:
            roots.append(node)
        else:
            children[parent].append(node)
    return children, roots


def _label(node: str) -> str:
    """The last segment of a path node's id, which is its label."""
    return node.rsplit("/", 1)[-1]


def _code_tree(scheme: str, values: Sequence[ClassificationValue]) -> list[ClassificationNode]:
    """The nodes of a code scheme, one per code, each parent above its prefixes at the scheme's
    levels and named by the structure the core carries for it when the data names it not."""
    key = _levels_key(scheme)
    levels = CODE_LEVELS[key]
    published = isic_names() if key == "ISIC" else {}
    stored: dict[str, ClassificationValue] = {}
    names: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for value in values:
        code, _, name = _rest(scheme, value).partition(":")
        _record(scheme=scheme, keyed=stored, node=code, value=value)
        names[code] = name.strip()
        chain = _chain(code, levels)
        for index, node in enumerate(chain):
            parents.setdefault(node, chain[index - 1] if index else None)
    children, roots = _children(parents)

    def build(code: str) -> ClassificationNode:
        held = stored.get(code)
        own = held.processes if held is not None else 0
        built = [build(child) for child in sorted(children[code])]
        return ClassificationNode(
            id=code,
            label=code,
            code=code,
            name=names.get(code) or published.get(code),
            value=held.value if held is not None else None,
            own=own,
            processes=own + sum(child.processes for child in built),
            children=built,
        )

    return [build(code) for code in sorted(roots)]


def _path_tree(scheme: str, values: Sequence[ClassificationValue]) -> list[ClassificationNode]:
    """The nodes of a path scheme, one per segment, each id the segments joined by `/`."""
    stored: dict[str, ClassificationValue] = {}
    parents: dict[str, str | None] = {}
    for value in values:
        segments = _rest(scheme, value).split("/")
        nodes = ["/".join(segments[: index + 1]) for index in range(len(segments))]
        for index, node in enumerate(nodes):
            parents.setdefault(node, nodes[index - 1] if index else None)
        _record(scheme=scheme, keyed=stored, node=nodes[-1], value=value)
    children, roots = _children(parents)

    def build(node: str) -> ClassificationNode:
        held = stored.get(node)
        own = held.processes if held is not None else 0
        built = [build(child) for child in sorted(children[node], key=_label)]
        return ClassificationNode(
            id=node,
            label=_label(node),
            code=None,
            name=None,
            value=held.value if held is not None else None,
            own=own,
            processes=own + sum(child.processes for child in built),
            children=built,
        )

    return [build(node) for node in sorted(roots, key=_label)]


def _flat_tree(scheme: str, values: Sequence[ClassificationValue]) -> list[ClassificationNode]:
    """The nodes of a flat scheme, one per stored value and none above them."""
    stored: dict[str, ClassificationValue] = {}
    for value in values:
        _record(scheme=scheme, keyed=stored, node=_rest(scheme, value), value=value)
    return [
        ClassificationNode(
            id=node,
            label=node,
            code=None,
            name=None,
            value=value.value,
            own=value.processes,
            processes=value.processes,
            children=[],
        )
        for node, value in sorted(stored.items())
    ]


def classification_tree(
    scheme: str, values: Sequence[ClassificationValue]
) -> list[ClassificationNode]:
    """The scheme's values as a tree: a code scheme by the prefixes of its codes, a path scheme by
    segment, any other as one level. A node carries the processes of every value under it."""
    kind = scheme_kind(scheme, values)
    if kind == "code":
        return _code_tree(scheme, values)
    if kind == "path":
        return _path_tree(scheme, values)
    return _flat_tree(scheme, values)


def _found(nodes: Sequence[ClassificationNode], wanted: str) -> ClassificationNode | None:
    """The node with the id, searched depth first from the roots; none when the tree has none."""
    for node in nodes:
        if node.id == wanted:
            return node
        deeper = _found(node.children, wanted)
        if deeper is not None:
            return deeper
    return None


def _held(node: ClassificationNode) -> list[str]:
    """The stored values a node and every node under it carry, in tree order."""
    found = [node.value] if node.value is not None else []
    for child in node.children:
        found.extend(_held(child))
    return found


def values_under(scheme: str, values: Sequence[ClassificationValue], node: str) -> list[str]:
    """The stored values the node and every node under it carry, in tree order; an id the tree
    does not hold is refused."""
    found = _found(classification_tree(scheme, values), node)
    if found is None:
        raise NotFound(f"no node {node!r} under classification scheme {scheme!r}")
    return _held(found)


def method_tree(methods: Sequence[Method]) -> list[MethodFamily]:
    """The methods folded into families, categories and indicators, each level by name."""
    families: dict[str, dict[str, list[Method]]] = {}
    for method in methods:
        families.setdefault(method.impact_method, {}).setdefault(method.impact_category, []).append(
            method
        )
    built: list[MethodFamily] = []
    for family, categories in sorted(families.items()):
        members: list[MethodCategory] = []
        for category, indicators in sorted(categories.items()):
            ordered = sorted(indicators, key=lambda found: found.indicator)
            members.append(MethodCategory(name=category, indicators=ordered))
        built.append(MethodFamily(name=family, categories=members))
    return built
