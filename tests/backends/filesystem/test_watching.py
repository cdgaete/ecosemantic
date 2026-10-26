from __future__ import annotations

import asyncio
from pathlib import Path

from ecosemantic.backends.filesystem.watching import touched


async def test_a_write_right_after_the_watch_is_asked_for_is_reported(tmp_path: Path) -> None:
    batches = touched(tmp_path)
    # nothing is awaited between asking for the watch and writing
    (tmp_path / "record.json").write_text("{}", encoding="utf-8")
    batch = await asyncio.wait_for(anext(batches), 5)
    assert tmp_path / "record.json" in batch
    await batches.aclose()


async def test_the_directory_is_created_when_the_watch_is_asked_for(tmp_path: Path) -> None:
    root = tmp_path / "store"
    batches = touched(root)
    assert root.is_dir()
    (root / "record.json").write_text("{}", encoding="utf-8")
    assert root / "record.json" in await asyncio.wait_for(anext(batches), 5)
    await batches.aclose()


async def test_a_closed_watch_reports_nothing_more(tmp_path: Path) -> None:
    batches = touched(tmp_path)
    await batches.aclose()
    (tmp_path / "record.json").write_text("{}", encoding="utf-8")
    async for _ in batches:
        raise AssertionError("a closed watch reported a write")
