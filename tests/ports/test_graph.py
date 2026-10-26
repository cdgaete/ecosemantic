from __future__ import annotations

from ecosemantic.ports.graph import GraphQueryPort


def test_the_port_is_declared_and_unimplemented() -> None:
    assert hasattr(GraphQueryPort, "query")
    assert GraphQueryPort.__module__ == "ecosemantic.ports.graph"
