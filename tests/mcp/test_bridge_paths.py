"""A chat off the engine's computer, on the bridge or across the network, names no path on it."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastmcp import Client
from starlette.types import ASGIApp, Receive, Scope, Send

from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.host import HOST_PATHS
from ecosemantic.mcp.reach import BRIDGE_EXTENSION
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import ProductSystem
from tests.callers import PATH, posted
from tests.conftest import fixture_system
from tests.fixture_data import FIXTURE_DB
from tests.mcp.test_installs import sources
from tests.memory_installs import MemoryInstaller, MemoryInstalls

PATH_NAMES = frozenset({"path", "package", "file", "folder", "directory", "destination"})


class Started(MemoryInstaller):
    """An installer that answers a pid and starts no process."""

    def start(self, install_id: object, account: object) -> int:
        return 4242

    def alive(self, install_id: object) -> bool:
        return True


def bridged(app: ASGIApp) -> ASGIApp:
    """The app as the relay reaches it, the bridge's extension in each request's scope."""

    async def relayed(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope["extensions"] = {BRIDGE_EXTENSION: {"proof": "proof"}}
            scope["client"] = ("bridge", 0)
        await app(scope, receive, send)

    return relayed


def across(app: ASGIApp) -> ASGIApp:
    """The app as another machine of the network reaches it."""

    async def arrived(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope["client"] = ("192.0.2.7", 50000)
        await app(scope, receive, send)

    return arrived


def forwarded(app: ASGIApp) -> ASGIApp:
    """The app as a tunnel on the engine's computer reaches it for someone elsewhere."""

    async def carried(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope["headers"] = [*scope["headers"], (b"cf-connecting-ip", b"192.0.2.7")]
        await app(scope, receive, send)

    return carried


DOORS = {
    "bridge": (bridged, "through the bridge"),
    "network": (across, "across the network"),
    "tunnel": (forwarded, "across the network"),
}


@pytest.fixture
def store(bundle_dir: Path, tmp_path: Path) -> Iterator[ServerContext]:
    """A store of this test's own, whose installs start no process."""
    (tmp_path / "systems").mkdir()
    built = build_context(bundle_dir, tmp_path / "systems", environ={})
    yield dataclasses.replace(
        built,
        installs=MemoryInstalls(),
        installer=Started(sources()),
        watchers=set(),
        uploads_dir=tmp_path / "uploads",
    )
    built.close()


@pytest.fixture
async def stored(store: ServerContext) -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    await store.storage.put_product_system(system, store.actor, "created")
    return system


async def called(
    store: ServerContext, tool: str, arguments: dict[str, object], door: str | None = None
) -> dict:
    """One tool call over HTTP in process, as a chat at that door or as one on this computer."""
    served = build_server(store).http_app(path=PATH)
    async with served.lifespan(served):
        app = DOORS[door][0](served) if door else served
        answer = await posted(app, None, "tools/call", {"name": tool, "arguments": arguments})
    for task in store.watchers:
        task.cancel()
    return answer.json()["result"]


def arguments_of(tool: str, system: ProductSystem, work: Path) -> dict[str, object]:
    """Arguments under which the tool would reach the paths they name."""
    named: dict[str, dict[str, object]] = {
        "export_product_system": {
            "product_system_id": str(system.id),
            "path": str(work / "mine.txt"),
            "replace": True,
        },
        "export_tables": {"product_system_id": str(system.id), "path": str(work), "replace": True},
        "import_product_system": {"path": str(work / "mine.txt")},
        "import_tables": {"path": str(work)},
        "install_database": {
            "source": "openlca",
            "package": str(work / "mine.txt"),
            "name": "named",
            "version": "1",
            "system_model": "unit process",
        },
    }
    return named[tool]


@pytest.mark.parametrize("door", sorted(DOORS))
@pytest.mark.parametrize("tool", sorted(HOST_PATHS))
async def test_a_chat_off_this_computer_names_no_path_on_it(
    store: ServerContext, stored: ProductSystem, tmp_path: Path, tool: str, door: str
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "mine.txt").write_bytes(b"mine")
    answer = await called(store, tool, arguments_of(tool, stored, work), door)
    assert answer["isError"]
    refused = json.loads(answer["content"][0]["text"])
    assert refused["error"] == "not_supported"
    assert f"a call {DOORS[door][1]}" in refused["message"]
    assert refused["message"].endswith(HOST_PATHS[tool].instead)
    assert [path.name for path in work.iterdir()] == ["mine.txt"]
    assert (work / "mine.txt").read_bytes() == b"mine"
    assert await store.installs.list_installs() == []
    [call] = await store.activity.list_calls()
    assert (call.tool, call.outcome) == (tool, "error")


async def test_a_chat_on_this_computer_still_names_a_path(
    store: ServerContext, stored: ProductSystem, tmp_path: Path
) -> None:
    written = tmp_path / "written.zip"
    arguments = {"product_system_id": str(stored.id), "path": str(written)}
    answer = await called(store, "export_product_system", arguments)
    assert not answer.get("isError")
    assert written.read_bytes().startswith(b"PK")


@pytest.mark.parametrize("door", sorted(DOORS))
async def test_a_chat_off_this_computer_still_installs_from_a_source(
    store: ServerContext, door: str
) -> None:
    arguments: dict[str, object] = {"source": "uslci"}
    answer = await called(store, "install_database", arguments, door)
    assert not answer.get("isError"), answer
    assert len(await store.installs.list_installs()) == 1


@pytest.mark.parametrize("door", sorted(DOORS))
async def test_a_chat_off_this_computer_still_models(store: ServerContext, door: str) -> None:
    arguments: dict[str, object] = {"name": "cup", "database": FIXTURE_DB}
    answer = await called(store, "create_product_system", arguments, door)
    assert not answer.get("isError"), answer


async def test_every_argument_that_names_a_path_is_in_the_rule(store: ServerContext) -> None:
    async with Client(build_server(store)) as client:
        found = {
            tool.name: name
            for tool in await client.list_tools()
            for name in tool.input_schema.get("properties", {})
            if name in PATH_NAMES
        }
    assert found == {tool: named.argument for tool, named in HOST_PATHS.items()}
