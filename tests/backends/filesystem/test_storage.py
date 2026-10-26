from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.errors import Conflict, NotFound
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.log import LOG_FILE
from ecosemantic.package.model_package import export_model_package
from ecosemantic.package.package import unzip_package
from ecosemantic.package.requests import REQUESTS_FILE
from ecosemantic.package.sidecar import SIDECAR_DIR
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import LogEntry, RequestDraft
from tests.conformance.storage import PackageConformance, StorageConformance
from tests.conftest import label_system, tshirt_labelled
from tests.dict_resolver import DictResolver


class TestFilesystemStorage(StorageConformance):
    @pytest.fixture
    def storage(self, tmp_path: Path, resolver: DictResolver) -> FilesystemStorage:
        return FilesystemStorage(tmp_path / "store", resolver)

    def test_satisfies_the_port(self, storage: FilesystemStorage) -> None:
        assert isinstance(storage, StoragePort)

    async def test_a_system_linking_another_is_stored_and_read_back(
        self, storage: FilesystemStorage, product_system: ProductSystem
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        label = label_system()
        await storage.put_product_system(label, agent, "created")
        labelled = tshirt_labelled(product_system, label)
        await storage.put_product_system(labelled, agent, "created")
        back = await storage.get_product_system(labelled.id)
        link = labelled.process("tshirt").exchanges[-1].input
        assert back.process("tshirt").exchanges[-1].input == link

    async def test_a_link_to_a_state_the_store_never_held_is_not_found(
        self, storage: FilesystemStorage, product_system: ProductSystem
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        with pytest.raises(NotFound):
            await storage.put_product_system(
                tshirt_labelled(product_system, label_system()), agent, "created"
            )

    async def test_a_missing_system_is_named_by_its_id_and_not_by_the_directory(
        self, storage: FilesystemStorage
    ) -> None:
        missing = uuid.uuid4()
        with pytest.raises(NotFound) as refused:
            await storage.get_product_system(missing)
        assert str(missing) in str(refused.value)
        assert str(storage.root) not in str(refused.value)

    async def test_requests_sit_beside_the_log_and_survive_a_write(
        self, storage: FilesystemStorage, product_system: ProductSystem
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        entry = await storage.put_product_system(product_system, agent, "created")
        await storage.post_request(
            product_system.id,
            RequestDraft(
                actor=Actor(kind="person", name="Carlos"),
                kind="return",
                at_hash=entry.result_hash,
                message="x",
            ),
        )
        folder = storage.root / str(product_system.id) / SIDECAR_DIR
        assert (folder / REQUESTS_FILE).is_file() and (folder / LOG_FILE).is_file()
        current = await storage.get_product_system(product_system.id)
        current.parameters[1].value = 0.12
        await storage.put_product_system(current, agent, "edited")
        assert len(await storage.list_requests(product_system.id)) == 1

    async def test_two_stores_over_one_directory_serialise(
        self, tmp_path: Path, resolver: DictResolver, product_system: ProductSystem
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        a = FilesystemStorage(tmp_path / "shared", resolver)
        b = FilesystemStorage(tmp_path / "shared", resolver)
        await a.put_product_system(product_system, agent, "created")
        via_a = await a.get_product_system(product_system.id)
        via_b = await b.get_product_system(product_system.id)
        via_a.parameters[1].value = 0.12
        via_b.parameters[1].value = 0.15
        outcomes = await asyncio.gather(
            a.put_product_system(via_a, agent, "a"),
            b.put_product_system(via_b, agent, "b"),
            return_exceptions=True,
        )
        kinds = sorted(type(o).__name__ for o in outcomes)
        assert kinds == sorted((Conflict.__name__, LogEntry.__name__))
        assert [e.seq for e in await a.log(product_system.id)] == [1, 2]
        assert (tmp_path / "shared" / f"{product_system.id}.lock").is_file()
        assert [s.id for s in await b.list_product_systems()] == [product_system.id]

    async def test_a_read_waits_for_a_lock_another_process_holds(
        self, storage: FilesystemStorage, product_system: ProductSystem
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        await storage.put_product_system(product_system, agent, "created")
        holder = (
            "import sys, time\n"
            "from filelock import FileLock\n"
            "with FileLock(sys.argv[1]):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(1.5)\n"
        )
        lock_path = storage.root / f"{product_system.id}.lock"
        process = subprocess.Popen(
            [sys.executable, "-c", holder, str(lock_path)], stdout=subprocess.PIPE, text=True
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "held"
        started = time.monotonic()
        current = await storage.get_product_system(product_system.id)
        assert time.monotonic() - started >= 1.0
        assert current.id == product_system.id
        assert process.wait(timeout=10) == 0

    async def test_a_returned_export_appends_one_openlca_entry(
        self, storage: FilesystemStorage, product_system: ProductSystem, tmp_path: Path
    ) -> None:
        agent = Actor(kind="agent", id="mcp")
        await storage.put_product_system(product_system, agent, "created")
        stored = await storage.get_product_system(product_system.id)
        zipped = tmp_path / "export.zip"
        export_model_package(stored, zipped, agent, storage.resolver)
        exported = tmp_path / "exported"
        unzip_package(zipped, exported)
        process_file = exported / "processes" / f"{stored.processes[0].id}.json"
        document = json.loads(process_file.read_text(encoding="utf-8"))
        document["description"] = "checked in openLCA"
        process_file.write_text(json.dumps(document), encoding="utf-8")
        entry = await storage.return_package(
            product_system.id, exported, Actor(kind="person", name="Carlos")
        )
        assert entry.source == "openlca" and entry.seq == 2
        assert [(c.entity, c.field, c.after) for c in entry.changes] == [
            ("process", "comment", "checked in openLCA")
        ]
        current = await storage.get_product_system(product_system.id)
        assert current.processes[0].comment == "checked in openLCA"


async def test_a_write_by_another_instance_over_one_directory_is_announced(
    tmp_path: Path, resolver: DictResolver, product_system: ProductSystem
) -> None:
    root = tmp_path / "shared"
    watcher = FilesystemStorage(root, resolver)
    writer = FilesystemStorage(root, resolver)
    changes = watcher.changes()
    await writer.put_product_system(product_system, Actor(kind="agent", id="other"), "created")
    change = await asyncio.wait_for(anext(changes), 5)
    assert change.product_system_id == product_system.id
    assert not change.gone


class TestFilesystemPackages(PackageConformance):
    @pytest.fixture
    def storage(self, tmp_path: Path, resolver: DictResolver) -> FilesystemStorage:
        return FilesystemStorage(tmp_path / "one", resolver)

    @pytest.fixture
    def other_storage(self, tmp_path: Path, resolver: DictResolver) -> FilesystemStorage:
        return FilesystemStorage(tmp_path / "other", resolver)
