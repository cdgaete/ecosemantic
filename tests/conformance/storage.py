"""The storage port's contract. Subclass with a `storage` fixture that yields an empty backend."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.log import verify_chain
from ecosemantic.ports.types import Layout, Outcome, RequestDraft, Spot

AGENT = Actor(kind="agent", id="claude")
PERSON = Actor(kind="person", name="Carlos")


class StorageConformance:
    async def test_empty_store_lists_nothing(self, storage) -> None:
        assert await storage.list_product_systems() == []

    async def test_first_write_is_entry_one(self, storage, product_system: ProductSystem) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        assert entry.seq == 1 and entry.base_hash is None
        stored = await storage.get_product_system(product_system.id)
        assert stored.hash == entry.result_hash
        summaries = await storage.list_product_systems()
        assert [s.id for s in summaries] == [product_system.id]
        assert summaries[0].hash == entry.result_hash

    async def test_stale_write_conflicts(self, storage, product_system: ProductSystem) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        stale = product_system.model_copy(deep=True)
        stale.parameters[1].value = 0.12
        with pytest.raises(Conflict):
            await storage.put_product_system(stale, AGENT, "stale")

    async def test_current_write_appends_and_keeps_versions(
        self, storage, product_system: ProductSystem
    ) -> None:
        first = await storage.put_product_system(product_system, AGENT, "created")
        current = await storage.get_product_system(product_system.id)
        current.parameters[1].value = 0.12
        second = await storage.put_product_system(current, AGENT, "waste rate")
        assert second.seq == 2 and second.base_hash == first.result_hash
        log = await storage.log(product_system.id)
        verify_chain(log)
        assert [e.seq for e in log] == [1, 2]
        old = await storage.get_version(product_system.id, first.result_hash)
        assert old.parameters[1].value == 0.1
        with pytest.raises(NotFound):
            await storage.get_version(product_system.id, "0" * 64)

    async def test_delete_then_not_found(self, storage, product_system: ProductSystem) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        await storage.delete_product_system(product_system.id, AGENT)
        with pytest.raises(NotFound):
            await storage.get_product_system(product_system.id)
        with pytest.raises(NotFound):
            await storage.delete_product_system(product_system.id, AGENT)

    async def test_unknown_project_is_not_found(self, storage) -> None:
        with pytest.raises(NotFound):
            await storage.get_product_system(uuid.uuid4())
        with pytest.raises(NotFound):
            await storage.log(uuid.uuid4())

    async def test_a_write_records_its_source(self, storage, product_system: ProductSystem) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "imported", source="import")
        assert entry.source == "import"
        assert (await storage.log(product_system.id))[0].source == "import"

    async def test_a_request_gets_the_next_seq_and_is_open(
        self, storage, product_system: ProductSystem
    ) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        first = await storage.post_request(
            product_system.id,
            RequestDraft(
                actor=PERSON, kind="return", at_hash=entry.result_hash, message="too heavy"
            ),
        )
        second = await storage.post_request(
            product_system.id,
            RequestDraft(
                actor=PERSON, kind="approve", at_hash=entry.result_hash, message="looks right"
            ),
        )
        assert (first.seq, second.seq) == (1, 2)
        assert first.open and not second.open
        opened = await storage.list_requests(product_system.id, open_only=True)
        assert [r.id for r in opened] == [first.id]
        assert len(await storage.list_requests(product_system.id)) == 2

    async def test_resolving_closes_a_request_once(
        self, storage, product_system: ProductSystem
    ) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        request = await storage.post_request(
            product_system.id,
            RequestDraft(actor=PERSON, kind="return", at_hash=entry.result_hash, message="x"),
        )
        outcome = Outcome(
            timestamp=datetime.now(UTC), actor=AGENT, resolution="overridden", message="kept"
        )
        resolved = await storage.resolve_request(product_system.id, request.id, outcome)
        assert resolved.outcome == outcome and not resolved.open
        assert await storage.list_requests(product_system.id, open_only=True) == []
        with pytest.raises(Conflict):
            await storage.resolve_request(product_system.id, request.id, outcome)
        with pytest.raises(NotFound):
            await storage.resolve_request(product_system.id, uuid.uuid4(), outcome)

    async def test_an_approval_is_never_resolved(
        self, storage, product_system: ProductSystem
    ) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        approval = await storage.post_request(
            product_system.id,
            RequestDraft(actor=PERSON, kind="approve", at_hash=entry.result_hash, message="ok"),
        )
        outcome = Outcome(
            timestamp=datetime.now(UTC), actor=AGENT, resolution="accepted", message="x"
        )
        with pytest.raises(Invalid):
            await storage.resolve_request(product_system.id, approval.id, outcome)

    async def test_requests_of_an_unknown_system_are_not_found(self, storage) -> None:
        draft = RequestDraft(actor=PERSON, kind="return", at_hash="0" * 64, message="x")
        with pytest.raises(NotFound):
            await storage.post_request(uuid.uuid4(), draft)
        with pytest.raises(NotFound):
            await storage.list_requests(uuid.uuid4())

    async def test_deleting_a_system_deletes_its_requests(
        self, storage, product_system: ProductSystem
    ) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        await storage.post_request(
            product_system.id,
            RequestDraft(actor=PERSON, kind="return", at_hash=entry.result_hash, message="x"),
        )
        await storage.delete_product_system(product_system.id, AGENT)
        with pytest.raises(NotFound):
            await storage.list_requests(product_system.id)

    async def test_a_write_announces_the_system(
        self, storage, product_system: ProductSystem
    ) -> None:
        changes = storage.changes()
        await storage.put_product_system(product_system, AGENT, "created")
        change = await asyncio.wait_for(anext(changes), 5)
        assert change.product_system_id == product_system.id
        assert not change.gone

    async def test_a_delete_announces_the_system_gone(
        self, storage, product_system: ProductSystem
    ) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        changes = storage.changes()
        await storage.delete_product_system(product_system.id, AGENT)
        change = await asyncio.wait_for(anext(changes), 5)
        assert change.product_system_id == product_system.id
        assert change.gone

    async def test_a_stored_system_starts_with_nothing_held(
        self, storage, product_system: ProductSystem
    ) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        assert (await storage.get_layout(product_system.id)).held == {}

    async def test_an_arrangement_reads_back_and_leaves_the_hash_alone(
        self, storage, product_system: ProductSystem
    ) -> None:
        entry = await storage.put_product_system(product_system, AGENT, "created")
        code = product_system.processes[0].code
        await storage.put_layout(product_system.id, Layout(held={code: Spot(x=10.0, y=20.0)}))
        stored = await storage.get_layout(product_system.id)
        assert stored.held[code].x == 10.0 and stored.held[code].y == 20.0
        # placing a card is not an edit: no entry, and the same hash
        assert [e.seq for e in await storage.log(product_system.id)] == [entry.seq]
        assert (await storage.get_product_system(product_system.id)).hash == entry.result_hash


class PackageConformance:
    async def test_a_package_leaves_and_returns_whole(
        self, storage, other_storage, product_system: ProductSystem, tmp_path: Path
    ) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        stored = await storage.get_product_system(product_system.id)
        zipped = tmp_path / "p.zip"
        await storage.export_package(product_system.id, zipped)
        assert await other_storage.restore_package(zipped) == "added"
        back = await other_storage.get_product_system(product_system.id)
        assert back.hash == stored.hash
        assert await other_storage.log(product_system.id) == await storage.log(product_system.id)
        assert await other_storage.restore_package(zipped) == "unchanged"

    async def test_a_diverged_package_conflicts_naming_both_states(
        self, storage, other_storage, product_system: ProductSystem, tmp_path: Path
    ) -> None:
        await storage.put_product_system(product_system, AGENT, "created")
        zipped = tmp_path / "p.zip"
        await storage.export_package(product_system.id, zipped)
        await other_storage.restore_package(zipped)
        edited = (await other_storage.get_product_system(product_system.id)).model_copy(deep=True)
        edited.parameters[0].value = 0.3
        entry = await other_storage.put_product_system(edited, AGENT, "diverge")
        with pytest.raises(Conflict, match=entry.result_hash):
            await other_storage.restore_package(zipped)
