from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.errors import Conflict, Invalid
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.jsonld import Stated
from ecosemantic.package.model_package import export_model_package, import_model_package, stated_at
from tests.conftest import frame_system, widget_linking
from tests.dict_resolver import DictResolver

AGENT = Actor(kind="agent", id="claude")


def _linked_pair() -> tuple[ProductSystem, ProductSystem]:
    """The widget linking the frame, and the frame as it stands at the widget's pin."""
    frame = frame_system()
    frame = frame.model_copy(update={"hash": content_hash(frame)})
    return widget_linking(frame), frame


def _rezipped(source: Path, target: Path, member: str, body: bytes) -> None:
    with zipfile.ZipFile(source) as read, zipfile.ZipFile(target, "w") as out:
        for name in read.namelist():
            out.writestr(name, body if name == member else read.read(name))


async def test_a_model_package_round_trips_through_a_storage_port(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    zipped = tmp_path / "shirt.zip"
    exported = export_model_package(product_system, zipped, AGENT, resolver)
    storage = FilesystemStorage(tmp_path / "store", resolver)
    system, entry = await import_model_package(zipped, storage, AGENT)
    assert system.id == product_system.id and entry.seq == 1 and entry.source == "import"
    assert entry.result_hash == exported.result_hash
    assert (await storage.get_product_system(system.id)).hash == exported.result_hash


async def test_a_missing_model_package_is_invalid(resolver: DictResolver, tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path / "store", resolver)
    with pytest.raises(Invalid):
        await import_model_package(tmp_path / "nothing.zip", storage, AGENT)


async def test_a_model_package_carries_each_linked_system_and_imports_it_first(
    context: ServerContext, tmp_path: Path
) -> None:
    widget, frame = _linked_pair()
    zipped = tmp_path / "widget.zip"
    await asyncio.to_thread(
        export_model_package, widget, zipped, AGENT, context.resolver, linked={frame.id: frame}
    )
    names = zipfile.ZipFile(zipped).namelist()
    assert f"product_systems/{frame.id}.json" in names
    assert f"linked/{frame.id}/ecosemantic/product_system.json" in names
    storage = FilesystemStorage(tmp_path / "store", context.resolver)
    system, entry = await import_model_package(zipped, storage, AGENT)
    # the widget's reader takes its own process, not the frame's beside it
    assert [p.code for p in system.processes] == ["widget"]
    assert entry.source == "import"
    assert (await storage.get_product_system(frame.id)).hash == frame.hash
    assert [e.source for e in await storage.log(frame.id)] == ["import"]
    assert (await storage.get_product_system(widget.id)).hash == entry.result_hash


async def test_a_linked_system_held_at_its_pin_is_left_as_it_is(
    context: ServerContext, tmp_path: Path
) -> None:
    widget, frame = _linked_pair()
    zipped = tmp_path / "widget.zip"
    await asyncio.to_thread(
        export_model_package, widget, zipped, AGENT, context.resolver, linked={frame.id: frame}
    )
    storage = FilesystemStorage(tmp_path / "store", context.resolver)
    await storage.put_product_system(
        frame.model_copy(update={"hash": None}), AGENT, "created", source="mcp"
    )
    await import_model_package(zipped, storage, AGENT)
    assert [e.source for e in await storage.log(frame.id)] == ["mcp"]
    assert (await storage.get_product_system(widget.id)).processes[0].code == "widget"


async def test_a_linked_system_held_only_at_other_states_is_refused(
    context: ServerContext, tmp_path: Path
) -> None:
    widget, frame = _linked_pair()
    zipped = tmp_path / "widget.zip"
    await asyncio.to_thread(
        export_model_package, widget, zipped, AGENT, context.resolver, linked={frame.id: frame}
    )
    storage = FilesystemStorage(tmp_path / "store", context.resolver)
    moved = frame.model_copy(update={"hash": None, "notes": "moved"}, deep=True)
    moved.processes[0].exchanges[1].amount *= 2
    await storage.put_product_system(moved, AGENT, "created", source="mcp")
    with pytest.raises(Conflict, match=f"never reached {frame.hash}"):
        await import_model_package(zipped, storage, AGENT)
    assert widget.id not in {s.id for s in await storage.list_product_systems()}


async def test_a_linked_system_that_does_not_hash_to_its_pin_is_invalid(
    context: ServerContext, tmp_path: Path
) -> None:
    widget, frame = _linked_pair()
    zipped = tmp_path / "widget.zip"
    await asyncio.to_thread(
        export_model_package, widget, zipped, AGENT, context.resolver, linked={frame.id: frame}
    )
    member = f"processes/{frame.processes[0].id}.json"
    process = json.loads(zipfile.ZipFile(zipped).read(member))
    produced = next(e for e in process["exchanges"] if not e.get("isQuantitativeReference"))
    produced["amount"] = produced["amount"] * 3
    tampered = tmp_path / "tampered.zip"
    _rezipped(zipped, tampered, member, json.dumps(process).encode())
    storage = FilesystemStorage(tmp_path / "store", context.resolver)
    with pytest.raises(Invalid, match=f"its link pins {frame.hash}"):
        await import_model_package(tampered, storage, AGENT)
    assert await storage.list_product_systems() == []


async def test_an_export_names_the_stored_entry_and_refuses_a_log_that_moved(
    product_system: ProductSystem, resolver: DictResolver, tmp_path: Path
) -> None:
    storage = FilesystemStorage(tmp_path / "store", resolver)
    await storage.put_product_system(product_system, AGENT, "created")
    first = await storage.get_product_system(product_system.id)
    noted = first.model_copy(update={"notes": "later"})
    await storage.put_product_system(noted, AGENT, "noted")
    log = await storage.log(product_system.id)
    assert stated_at(first, log) == Stated(seq=2, hash=first.hash or "")
    moved = first.model_copy(deep=True)
    moved.parameter("fabric_mass").value = 0.3
    moved.hash = content_hash(moved)
    with pytest.raises(Conflict, match="moved while it was read for export"):
        stated_at(moved, log)
