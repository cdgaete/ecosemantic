"""The install port's contract. Subclass with an `installs` fixture that yields an empty
backend."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from ecosemantic.errors import Conflict, NotFound
from ecosemantic.model.entities import Actor
from ecosemantic.ports.types import InstallDraft, InstallPatch, InstallProgress


def draft(version: str | None = None) -> InstallDraft:
    """A `uslci` draft, which needs nothing beyond its source and the actor who posted it."""
    return InstallDraft(
        source="uslci",
        actor=Actor(kind="person", name="carlos"),
        version=version,
    )


class InstallConformance:
    async def test_a_posted_install_reads_back_queued(self, installs) -> None:
        posted = await installs.post_install(draft())
        read = await installs.get_install(posted.id)
        assert read.status == "queued" and read.draft == posted.draft
        assert read.posted_at == posted.posted_at
        assert read.error is None and read.summary is None

    async def test_a_patch_changes_only_what_it_names(self, installs) -> None:
        posted = await installs.post_install(draft())
        running = await installs.update_install(
            posted.id,
            InstallPatch(
                status="running",
                progress=InstallProgress(step="download", count=3),
            ),
        )
        assert running.status == "running" and running.progress is not None
        assert running.progress.count == 3
        assert running.draft == posted.draft and running.posted_at == posted.posted_at
        assert await installs.get_install(posted.id) == running

    async def test_installs_list_newest_first(self, installs) -> None:
        first = await installs.post_install(draft())
        second = await installs.post_install(draft(version="2026"))
        assert [install.id for install in await installs.list_installs()] == [second.id, first.id]

    async def test_cancel_sets_the_flag_and_a_finished_install_refuses_it(self, installs) -> None:
        posted = await installs.post_install(draft())
        asked = await installs.cancel_install(posted.id)
        # the flag is the ask; the install process sets the status
        assert asked.cancel_requested is True and asked.status == "queued"
        await installs.update_install(posted.id, InstallPatch(status="done"))
        with pytest.raises(Conflict):
            await installs.cancel_install(posted.id)

    async def test_an_unknown_install_is_not_found(self, installs) -> None:
        with pytest.raises(NotFound):
            await installs.get_install(uuid.uuid4())
        with pytest.raises(NotFound):
            await installs.update_install(uuid.uuid4(), InstallPatch(status="done"))
        with pytest.raises(NotFound):
            await installs.cancel_install(uuid.uuid4())

    async def test_a_write_is_announced_by_its_id(self, installs) -> None:
        posted = await installs.post_install(draft())
        changes = installs.changes()
        await installs.update_install(posted.id, InstallPatch(status="running"))
        assert await asyncio.wait_for(anext(changes), 5) == posted.id

    async def test_the_slot_admits_one_holder_at_a_time(self, installs) -> None:
        entered: list[str] = []

        async def hold(name: str) -> None:
            async with installs.slot():
                entered.append(f"{name} in")
                await asyncio.sleep(0.05)
                entered.append(f"{name} out")

        await asyncio.gather(hold("a"), hold("b"))
        # whoever enters first leaves before the other enters
        assert entered in (["a in", "a out", "b in", "b out"], ["b in", "b out", "a in", "a out"])
