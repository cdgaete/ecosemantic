"""The tools that read or write the host's own machine, refused to a context naming a person."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import pytest

from ecosemantic.errors import NotSupported
from ecosemantic.local import build_context
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.installs import cancel_install, install_database
from ecosemantic.mcp.systems import export_product_system, import_product_system
from ecosemantic.mcp.tables import export_tables, import_tables
from ecosemantic.model.entities import Person, ProductSystem
from tests.conftest import fixture_system
from tests.mcp.test_installs import sources
from tests.memory_installs import MemoryInstaller, MemoryInstalls

ANA = Person(id="a", name="Ana")

Reaches = Callable[[ServerContext, ProductSystem, Path], Awaitable[object]]


def hosted(built: ServerContext, work: Path) -> ServerContext:
    """The context over the in-memory installs and installer, so no test starts an install's
    process, with the data directory and the uploads an install would write under this test's own
    directory: an install downloads over the network."""
    return dataclasses.replace(
        built,
        installs=MemoryInstalls(),
        installer=MemoryInstaller(sources()),
        watchers=set(),
        data_dir=work / "data",
        uploads_dir=work / "uploads",
    )


@pytest.fixture
def store(bundle_dir: Path, tmp_path: Path) -> Iterator[ServerContext]:
    """A store of this test's own over the fixture database, the installs held in memory."""
    (tmp_path / "systems").mkdir()
    built = hosted(build_context(bundle_dir, tmp_path / "systems"), tmp_path)
    yield built
    for task in built.watchers:
        task.cancel()
    built.close()


@pytest.fixture
async def stored(store: ServerContext) -> ProductSystem:
    system = fixture_system().product_system
    assert system is not None
    await store.storage.put_product_system(system, store.actor, "created")
    return system


async def _export_package(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await export_product_system(
        context, str(stored.id), str(work / "package.zip"), replace=True
    )


async def _import_package(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await import_product_system(context, str(work / "missing" / "package.zip"))


async def _export_folder(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await export_tables(context, str(stored.id), str(work / "tables"))


async def _import_folder(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await import_tables(context, str(work / "missing" / "tables"))


async def _post_install(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await install_database(context, "uslci")


async def _cancel(context: ServerContext, stored: ProductSystem, work: Path) -> object:
    return await cancel_install(context, str(uuid.uuid4()))


CASES: dict[str, tuple[Reaches, str]] = {
    "export_product_system": (
        _export_package,
        "export_product_system reaches the host's machine, which a signed-in person does not; "
        "download the openLCA package from the product system's page",
    ),
    "import_product_system": (
        _import_package,
        "import_product_system reaches the host's machine, which a signed-in person does not",
    ),
    "export_tables": (
        _export_folder,
        "export_tables reaches the host's machine, which a signed-in person does not; "
        "download the tables from the product system's page",
    ),
    "import_tables": (
        _import_folder,
        "import_tables reaches the host's machine, which a signed-in person does not; "
        "return the edited tables on the product system's page",
    ),
    "install_database": (
        _post_install,
        "install_database reaches the host's machine, which a signed-in person does not; "
        "the host's operator installs databases",
    ),
    "cancel_install": (
        _cancel,
        "cancel_install reaches the host's machine, which a signed-in person does not; "
        "the host's operator installs databases",
    ),
}


def held_under(root: Path) -> dict[str, bytes | None]:
    """Every path under the root, as the bytes a file holds and None for a directory."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


@pytest.mark.parametrize("named", list(CASES))
async def test_a_tool_that_reaches_the_host_is_refused_for_a_person(
    store: ServerContext, stored: ProductSystem, tmp_path: Path, named: str
) -> None:
    reaches, said = CASES[named]
    work = tmp_path / "work"
    work.mkdir()
    (work / "package.zip").write_bytes(b"a file of my own")
    (work / "tables").mkdir()
    before = held_under(tmp_path)
    with pytest.raises(NotSupported) as refused:
        await reaches(store.for_person(ANA), stored, work)
    assert str(refused.value) == said
    assert held_under(tmp_path) == before
