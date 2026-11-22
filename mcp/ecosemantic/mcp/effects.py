"""What a tool declares about its effect: it reads, it writes, it deletes, or it computes on the
store, or it writes over files on the engine's computer."""

from __future__ import annotations

from collections.abc import Set

from mcp.types import ToolAnnotations

from ecosemantic.ports.types import Effect

COMPUTE = "compute"
FILES = "files"

READ = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
DELETE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
OVERWRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)


def effect_of(annotations: ToolAnnotations | None, tags: Set[str]) -> Effect:
    """A tool's effect, read from what it registered with: the compute tag, the files tag of a
    tool that writes over files and deletes nothing from the store, else its annotations."""
    if COMPUTE in tags:
        return "compute"
    if FILES in tags:
        return "write"
    if annotations is None:
        raise ValueError("a tool registers with READ, WRITE or DELETE")
    if annotations.read_only_hint:
        return "read"
    if annotations.destructive_hint:
        return "delete"
    return "write"
