from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.errors import Unavailable
from ecosemantic.ports.run import RunPort
from ecosemantic.ports.types import RunPatch
from tests.conformance.runs import RunConformance, draft


class TestFilesystemRuns(RunConformance):
    @pytest.fixture
    def runs(self, tmp_path: Path) -> FilesystemRuns:
        return FilesystemRuns(tmp_path)

    def test_satisfies_the_port(self, runs: FilesystemRuns) -> None:
        assert isinstance(runs, RunPort)

    async def test_a_run_is_a_record_under_runs_in_the_systems_directory(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        assert (tmp_path / "runs" / str(posted.id) / "run.json").is_file()
        assert await FilesystemRuns(tmp_path).get_run(posted.id) == posted

    async def test_nothing_is_listed_before_the_first_run(self, runs: FilesystemRuns) -> None:
        assert await runs.list_runs() == []

    async def test_a_record_another_process_keeps_rewriting_always_reads_whole(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        writer = (
            "import sys, time, uuid\n"
            "from pathlib import Path\n"
            "from ecosemantic.backends.filesystem.runs import FilesystemRuns\n"
            "from ecosemantic.ports.types import RunPatch, RunProgress\n"
            "runs = FilesystemRuns(Path(sys.argv[1]))\n"
            "run_id = uuid.UUID(sys.argv[2])\n"
            "print('writing', flush=True)\n"
            "end, n = time.monotonic() + 1.0, 0\n"
            "while time.monotonic() < end:\n"
            "    n += 1\n"
            "    runs.apply_patch(run_id, RunPatch(progress=RunProgress(iterations=n)))\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", writer, str(tmp_path), str(posted.id)],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "writing"
        reads = 0
        while process.poll() is None:
            runs.read_record(posted.id)
            reads += 1
        assert process.returncode == 0 and reads > 0
        assert (await runs.get_run(posted.id)).progress.iterations > 0

    async def test_a_patch_waits_for_a_lock_another_process_holds(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        holder = (
            "import sys, time\n"
            "from filelock import FileLock\n"
            "with FileLock(sys.argv[1]):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(1.5)\n"
        )
        lock_path = tmp_path / "runs" / f"{posted.id}.lock"
        process = subprocess.Popen(
            [sys.executable, "-c", holder, str(lock_path)], stdout=subprocess.PIPE, text=True
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "held"
        started = time.monotonic()
        await runs.update_run(posted.id, RunPatch(status="running"))
        assert time.monotonic() - started >= 1.0
        assert process.wait(timeout=10) == 0

    async def test_the_slot_excludes_another_process_over_the_same_directory(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        holder = (
            "import asyncio, sys, time\n"
            "from pathlib import Path\n"
            "from ecosemantic.backends.filesystem.runs import FilesystemRuns\n"
            "async def hold():\n"
            "    async with FilesystemRuns(Path(sys.argv[1])).slot():\n"
            "        print('held', flush=True)\n"
            "        time.sleep(1.5)\n"
            "asyncio.run(hold())\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", holder, str(tmp_path)], stdout=subprocess.PIPE, text=True
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "held"

        async def enter() -> None:
            async with runs.slot():
                pass

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(enter(), timeout=0.5)
        assert process.wait(timeout=10) == 0
        await asyncio.wait_for(enter(), timeout=5)

    async def test_a_record_this_version_cannot_read_is_refused_by_name(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        record = tmp_path / "runs" / str(posted.id) / "run.json"
        stored = json.loads(record.read_text())
        del stored["at_hash"]
        record.write_text(json.dumps(stored))
        for read in (lambda: runs.get_run(posted.id), runs.list_runs):
            with pytest.raises(Unavailable) as caught:
                await read()
            assert str(posted.id) in str(caught.value) and "at_hash" in str(caught.value)
            assert caught.value.hint is not None and str(record.parent) in caught.value.hint


async def test_a_run_written_by_another_instance_is_announced(tmp_path: Path) -> None:
    watcher = FilesystemRuns(tmp_path)
    writer = FilesystemRuns(tmp_path)
    run = await writer.post_run(draft(uuid.UUID(int=1)))
    changes = watcher.changes()
    await writer.update_run(run.id, RunPatch(status="running"))
    change = await asyncio.wait_for(anext(changes), 5)
    assert change.run_id == run.id
    assert change.product_system_id == run.product_system_id
