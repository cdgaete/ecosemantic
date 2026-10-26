"""The bench a release and a working database are built on: the synthetic base installed from
its bundle, and the casing and device systems stored over it."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.install import install
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.background import read_background
from ecosemantic.package.manifest import BaseDatabase
from tests.database_fixture import BASE, backgrounds, casing_system, device_system, flows
from tests.dict_resolver import DictResolver
from tests.openlca_fixture import build_package

AGENT = Actor(kind="agent", id="claude")
NOW = datetime(2030, 1, 1, tzinfo=UTC)
BASE_DB = BaseDatabase(name=BASE, version="1")


@dataclasses.dataclass
class Bench:
    store: NativeStore
    storage: FilesystemStorage
    base_bundle: Path
    casing: ProductSystem
    device: ProductSystem
    root: Path


@pytest.fixture
async def bench(tmp_path: Path) -> AsyncIterator[Bench]:
    base_bundle = build_package(tmp_path / "base.zip")
    imported = read_background(base_bundle, BASE, foreground=frozenset())
    install(
        tmp_path / "data",
        dataclasses.replace(imported, unlinked=[]),
        base_bundle,
        version="1",
        system_model="unit process",
    )
    store = NativeStore(tmp_path / "data")
    storage = FilesystemStorage(tmp_path / "systems", DictResolver(backgrounds(), flows()))
    casing = casing_system()
    await storage.put_product_system(casing, AGENT, "created")
    casing = await storage.get_product_system(casing.id)
    device = device_system(casing)
    await storage.put_product_system(device, AGENT, "created")
    device = await storage.get_product_system(device.id)
    yield Bench(store, storage, store.bundle_of(BASE), casing, device, tmp_path)
    store.close()
