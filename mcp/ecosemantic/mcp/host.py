"""The rules that keep a caller off the host's machine: a signed-in person off its files, its
installs and its accounts, and a call from off the machine off its paths."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ecosemantic.errors import NotSupported
from ecosemantic.mcp.accounts import ARRIVAL
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.reach import reach

OPERATOR_INSTALLS = "the host's operator installs databases"
OPERATOR_ACCOUNTS = "the host's operator enters database accounts"
DOWNLOAD_PACKAGE = "download the openLCA package from the product system's page"
DOWNLOAD_TABLES = "download the tables from the product system's page"
RETURN_TABLES = "return the edited tables on the product system's page"
IMPORT_THERE = "import it on the computer where EcoSemantic runs"
UPLOAD_ZIP = "upload the zip on the page's Databases editor"


@dataclass(frozen=True)
class HostPath:
    """The argument by which a tool names a path on the engine's computer, and what a caller who
    names none does instead."""

    argument: str
    instead: str


HOST_PATHS: Mapping[str, HostPath] = {
    "export_product_system": HostPath(argument="path", instead=DOWNLOAD_PACKAGE),
    "import_product_system": HostPath(argument="path", instead=IMPORT_THERE),
    "export_tables": HostPath(argument="path", instead=DOWNLOAD_TABLES),
    "import_tables": HostPath(argument="path", instead=RETURN_TABLES),
    "install_database": HostPath(argument="package", instead=UPLOAD_ZIP),
}


def refuse_host(context: ServerContext, named: str, instead: str | None = None) -> None:
    """Refuse to a context naming a person a tool or a route that reads or writes the host's own
    machine, naming what that person does instead."""
    if context.person is None:
        return
    refusal = f"{named} reaches the host's machine, which a signed-in person does not"
    raise NotSupported(refusal if instead is None else f"{refusal}; {instead}")


def named_path(tool: str, arguments: Mapping[str, object]) -> HostPath | None:
    """The rule of the path a call names on the engine's computer, or none for a call that names
    no path."""
    rule = HOST_PATHS.get(tool)
    return None if rule is None or arguments.get(rule.argument) is None else rule


def refuse_remote_path(
    scope: Mapping[str, object] | None, tool: str, arguments: Mapping[str, object]
) -> None:
    """Refuse a call that names a path on the engine's computer from a request that reached it
    from off that computer, naming what its caller does instead."""
    rule = named_path(tool, arguments)
    if rule is None or scope is None:
        return
    reached = reach(scope)
    if reached == "here":
        return
    raise NotSupported(
        f"{tool} names a path on the computer where EcoSemantic runs, which a call "
        f"{ARRIVAL[reached]} does not; {rule.instead}"
    )


def refuse_replayed_path(tool: str, arguments: Mapping[str, object]) -> None:
    """Refuse to run again a recorded call that names a path: whoever recorded it chose the path,
    and the one who runs it again would write or read there as themselves."""
    if named_path(tool, arguments) is not None:
        raise NotSupported(
            f"{tool} names a path on the computer where EcoSemantic runs; the page reruns no "
            "such call"
        )
