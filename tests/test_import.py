from __future__ import annotations

import subprocess
import sys
import tomllib
from importlib.metadata import requires, version
from pathlib import Path

import pytest
from packaging.requirements import Requirement

DISTRIBUTIONS = (
    "ecosemantic",
    "ecosemantic-engine",
    "ecosemantic-core",
    "ecosemantic-mcp",
    "ecosemantic-view",
    "ecosemantic-databases",
)


def test_every_distribution_answers_the_version_the_command_declares() -> None:
    project = Path(__file__).resolve().parents[1] / "app" / "pyproject.toml"
    declared = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"]
    assert {version(name) for name in DISTRIBUTIONS} == {declared}
    pins = {
        (name, str(required.specifier))
        for name in DISTRIBUTIONS
        for required in map(Requirement, requires(name) or [])
        if required.name in DISTRIBUTIONS
    }
    assert pins and {specifier for _name, specifier in pins} == {f"=={declared}"}


def on(platform: str, machine: str) -> dict[str, str]:
    return {"sys_platform": platform, "platform_machine": machine, "extra": "mkl"}


def test_the_mkl_extra_installs_pypardiso_wherever_mkl_publishes_wheels() -> None:
    required = [Requirement(line) for line in requires("ecosemantic-engine") or []]
    pardiso = [r for r in required if r.name == "pypardiso"]
    assert len(pardiso) == 1 and pardiso[0].marker is not None
    marker = pardiso[0].marker
    assert marker.evaluate(on("linux", "x86_64")) and marker.evaluate(on("win32", "AMD64"))
    # mkl publishes no macOS or ARM wheel
    assert not marker.evaluate(on("darwin", "x86_64"))
    assert not marker.evaluate(on("linux", "aarch64"))


def test_the_command_offers_the_mkl_extra_of_the_engine() -> None:
    required = [Requirement(line) for line in requires("ecosemantic") or []]
    [engine] = [r for r in required if r.name == "ecosemantic-engine" and r.extras]
    assert engine.extras == {"mkl"} and engine.marker is not None
    assert engine.marker.evaluate({"extra": "mkl"})


def _printed(code: str) -> str:
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return done.stdout.strip()


def test_importing_a_package_of_the_namespace_imports_nothing_from_the_command() -> None:
    code = "import ecosemantic.model, sys; print('ecosemantic.workspace' in sys.modules)"
    assert _printed(code) == "False"


def test_the_namespace_answers_open_and_the_types_an_argument_takes() -> None:
    import ecosemantic as es
    from ecosemantic import workspace
    from ecosemantic.model.entities import DemandItem, Parameter
    from ecosemantic.ports.types import MonteCarloConfig

    assert es.open is workspace.open and es.Workspace is workspace.Workspace
    assert es.Parameter is Parameter and es.DemandItem is DemandItem
    assert es.MonteCarloConfig is MonteCarloConfig
    with pytest.raises(AttributeError, match="nowhere"):
        _ = es.nowhere
