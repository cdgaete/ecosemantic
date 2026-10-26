"""The run port's contract. Subclass with a `runs` fixture that yields an empty backend."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from ecosemantic.backends.filesystem import records
from ecosemantic.errors import Conflict, NotFound
from ecosemantic.ports.types import MonteCarloConfig, RunDraft, RunPatch, RunProgress


def draft(system: uuid.UUID) -> RunDraft:
    return RunDraft(
        product_system_id=system,
        at_hash="9c1d" + "0" * 60,
        demand=[],
        methods=[],
        config=MonteCarloConfig(),
    )


class RunConformance:
    async def test_a_posted_run_reads_back_queued(self, runs) -> None:
        system = uuid.UUID(int=1)
        posted = await runs.post_run(draft(system))
        read = await runs.get_run(posted.id)
        assert read.status == "queued" and read.product_system_id == system
        assert read.at_hash == posted.at_hash

    async def test_a_patch_changes_only_what_it_names(self, runs) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        running = await runs.update_run(
            posted.id,
            RunPatch(status="running", progress=RunProgress(iterations=7, worst_rel_se=0.2)),
        )
        assert running.status == "running" and running.progress.iterations == 7
        assert running.at_hash == posted.at_hash and running.config == posted.config
        assert await runs.get_run(posted.id) == running

    async def test_runs_list_newest_first_and_filter_by_product_system(
        self, runs, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        one, other = uuid.UUID(int=1), uuid.UUID(int=2)
        monkeypatch.setattr(records, "now", lambda: datetime(2024, 1, 1, tzinfo=UTC))
        first = await runs.post_run(draft(one))
        second = await runs.post_run(draft(other))
        assert [r.id for r in await runs.list_runs()] == [second.id, first.id]
        assert [r.id for r in await runs.list_runs(one)] == [first.id]

    async def test_cancelling_asks_and_does_not_decide(self, runs) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        asked = await runs.cancel_run(posted.id)
        # the flag is the ask; the worker sets the status
        assert asked.cancel_requested is True and asked.status == "queued"

    async def test_cancelling_a_finished_run_is_refused(self, runs) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        await runs.update_run(posted.id, RunPatch(status="done"))
        with pytest.raises(Conflict):
            await runs.cancel_run(posted.id)

    async def test_the_slot_admits_one_holder_at_a_time(self, runs) -> None:
        entered: list[str] = []

        async def hold(name: str) -> None:
            async with runs.slot():
                entered.append(f"{name} in")
                await asyncio.sleep(0.05)
                entered.append(f"{name} out")

        await asyncio.gather(hold("a"), hold("b"))
        # whoever enters first leaves before the other enters
        assert entered in (["a in", "a out", "b in", "b out"], ["b in", "b out", "a in", "a out"])

    async def test_an_unknown_run_is_not_found(self, runs) -> None:
        with pytest.raises(NotFound):
            await runs.get_run(uuid.uuid4())
        with pytest.raises(NotFound):
            await runs.update_run(uuid.uuid4(), RunPatch(status="done"))

    async def test_a_run_announces_itself(self, runs) -> None:
        system = uuid.UUID(int=1)
        run = await runs.post_run(draft(system))
        changes = runs.changes()
        await runs.update_run(run.id, RunPatch(status="running"))
        change = await asyncio.wait_for(anext(changes), 5)
        assert change.run_id == run.id
        assert change.product_system_id == system

    async def test_deleting_a_systems_runs_leaves_none_for_it_and_others_whole(self, runs) -> None:
        gone, kept = uuid.UUID(int=41), uuid.UUID(int=42)
        first = await runs.post_run(draft(gone))
        second = await runs.post_run(draft(gone))
        other = await runs.post_run(draft(kept))
        with pytest.raises(Conflict):
            await runs.delete_runs(gone)
        for run in (first, second):
            await runs.update_run(run.id, RunPatch(status="done"))
        await runs.delete_runs(gone)
        assert await runs.list_runs(gone) == []
        assert [r.id for r in await runs.list_runs(kept)] == [other.id]
        with pytest.raises(NotFound):
            await runs.get_run(first.id)
