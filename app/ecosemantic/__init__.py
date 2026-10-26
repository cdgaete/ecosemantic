"""Open a workspace with `ecosemantic.open()`; every MCP tool is a method on it."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ecosemantic.model.entities import (
        Case,
        DemandItem,
        ExchangeOverride,
        Parameter,
        ParameterOverride,
        Uncertainty,
    )
    from ecosemantic.model.refs import BackgroundRef, ElementaryFlowRef, ForegroundRef, SystemRef
    from ecosemantic.ports.types import MonteCarloConfig
    from ecosemantic.workspace import Workspace, open

__path__ = __import__("pkgutil").extend_path(__path__, __name__)

PUBLIC = {
    "open": "ecosemantic.workspace",
    "Workspace": "ecosemantic.workspace",
    "Parameter": "ecosemantic.model.entities",
    "Case": "ecosemantic.model.entities",
    "Uncertainty": "ecosemantic.model.entities",
    "ExchangeOverride": "ecosemantic.model.entities",
    "ParameterOverride": "ecosemantic.model.entities",
    "DemandItem": "ecosemantic.model.entities",
    "BackgroundRef": "ecosemantic.model.refs",
    "ForegroundRef": "ecosemantic.model.refs",
    "ElementaryFlowRef": "ecosemantic.model.refs",
    "SystemRef": "ecosemantic.model.refs",
    "MonteCarloConfig": "ecosemantic.ports.types",
}

__all__ = [
    "BackgroundRef",
    "Case",
    "DemandItem",
    "ElementaryFlowRef",
    "ExchangeOverride",
    "ForegroundRef",
    "MonteCarloConfig",
    "Parameter",
    "ParameterOverride",
    "SystemRef",
    "Uncertainty",
    "Workspace",
    "open",
]


def __getattr__(name: str) -> object:
    """The public name from the module that defines it, imported on first use."""
    if name not in PUBLIC:
        raise AttributeError(f"module 'ecosemantic' has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(PUBLIC[name]), name)
