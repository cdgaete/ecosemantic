from __future__ import annotations

import asyncio
import copy
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.runs import FilesystemRuns, StoredRun
from ecosemantic.errors import NotFound, Unavailable
from ecosemantic.files import REPLACE_ATTEMPTS
from ecosemantic.model.entities import Method
from ecosemantic.ports.run import RunPort
from ecosemantic.ports.types import (
    MonteCarloCategory,
    MonteCarloConfig,
    MonteCarloResult,
    MonteCarloSummary,
    Run,
    RunPatch,
)
from tests.conformance.runs import RunConformance, draft
from tests.fixture_data import FIXTURE_DATABASE

METHOD = Method.of(("bafu-2026-v1", "IPCC 2021", "IPCC 2021 GWP 100"), "kg CO2 eq")
SAMPLES = [0.000149, 0.000147, 0.000157]


def finished_run(system: uuid.UUID) -> Run:
    """A finished run carrying one category's summary and its draws."""
    return Run(
        id=uuid.UUID(int=7),
        product_system_id=system,
        at_hash="9c1d" + "0" * 60,
        methods=[METHOD],
        config=MonteCarloConfig(n=3),
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="done",
        result=MonteCarloResult(
            database=FIXTURE_DATABASE,
            n=3,
            stopped="fixed",
            gating_method=METHOD.id,
            scope="full",
            normals_at_amount=0,
            credit_loops=[],
            dropped_draws=[],
            dropped_loops=[],
            dropped_background=[],
            categories=[
                MonteCarloCategory(
                    method_id=METHOD.id,
                    summary=MonteCarloSummary(
                        n=3,
                        mean=0.00016,
                        median=0.00015,
                        median_ci95=(0.00014, 0.00017),
                        percentiles=(0.0001, 0.00025),
                        rel_se=0.046,
                    ),
                    samples=SAMPLES,
                )
            ],
        ),
    )


def naming_whole_methods(run: Run) -> dict[str, object]:
    """The run's record in the shape a store wrote when a result named each method by its whole
    record: the method records put back in place of their ids."""
    stored = run.model_dump(mode="json")
    result = stored["result"]
    assert isinstance(result, dict)
    whole = METHOD.model_dump(mode="json")
    result["gating_method"] = whole
    for category in result["categories"]:
        assert isinstance(category, dict)
        del category["method_id"]
        category["method"] = whole
    return stored


def written_naming_whole_methods(tmp_path: Path, run: Run) -> Path:
    """The run's record on disk, naming each method by its whole record."""
    folder = tmp_path / "runs" / str(run.id)
    folder.mkdir(parents=True)
    record = folder / "run.json"
    record.write_text(json.dumps(naming_whole_methods(run)), encoding="utf-8")
    return record


def test_a_record_naming_whole_methods_is_read_without_changing_what_it_holds() -> None:
    record = naming_whole_methods(finished_run(uuid.UUID(int=1)))
    unchanged = copy.deepcopy(record)
    read = StoredRun.model_validate(record)
    assert read.result is not None
    assert read.result.gating_method == METHOD.id
    assert [category.method_id for category in read.result.categories] == [METHOD.id]
    assert record == unchanged


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

    async def test_cancelling_a_run_the_store_does_not_hold_leaves_no_lock(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        missing = uuid.uuid4()
        with pytest.raises(NotFound):
            await runs.cancel_run(missing)
        assert [path.name for path in (tmp_path / "runs").glob(f"{missing}*")] == []

    async def test_deleting_a_systems_runs_leaves_no_file_and_no_folder_of_their_ids(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        await runs.update_run(posted.id, RunPatch(status="done"))
        await runs.delete_runs(posted.product_system_id)
        assert [path.name for path in (tmp_path / "runs").glob(f"{posted.id}*")] == []

    async def test_a_sweep_removes_the_lock_of_a_run_the_store_does_not_hold(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        await runs.update_run(posted.id, RunPatch(status="running"))
        folder = tmp_path / "runs"
        orphan = folder / f"{uuid.uuid4()}.lock"
        orphan.write_text("", encoding="utf-8")
        for kept in ("post.lock", "slot.lock"):
            (folder / kept).write_text("", encoding="utf-8")
        # Windows removes a lock's file when the lock is released, so it may be absent there
        held = (folder / f"{posted.id}.lock").is_file()

        runs.sweep()

        assert not orphan.exists()
        assert (folder / f"{posted.id}.lock").is_file() == held
        assert (folder / str(posted.id)).is_dir()
        assert (folder / "post.lock").is_file() and (folder / "slot.lock").is_file()

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
            encoding="utf-8",
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "writing"
        reads = 0
        while process.poll() is None:
            runs.read_record(posted.id)
            reads += 1
        assert process.returncode == 0 and reads > 0
        assert (await runs.get_run(posted.id)).progress.iterations > 0

    async def test_a_replace_refused_by_a_reader_is_retried_then_raised(
        self, runs: FilesystemRuns, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        attempts = 0
        real_replace = os.replace

        def flaky(source: str, destination: str) -> None:
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise PermissionError("held")
            real_replace(source, destination)

        monkeypatch.setattr(os, "replace", flaky)
        await runs.update_run(posted.id, RunPatch(status="running"))
        assert attempts == 3
        assert (await runs.get_run(posted.id)).status == "running"

        attempts = 0

        def always(source: str, destination: str) -> None:
            nonlocal attempts
            attempts += 1
            raise PermissionError("held")

        monkeypatch.setattr(os, "replace", always)
        with pytest.raises(Unavailable) as caught:
            await runs.update_run(posted.id, RunPatch(status="done"))
        assert attempts == REPLACE_ATTEMPTS
        assert isinstance(caught.value.__cause__, PermissionError)

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
            [sys.executable, "-c", holder, str(lock_path)],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
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
            [sys.executable, "-c", holder, str(tmp_path)],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert process.stdout is not None and process.stdout.readline().strip() == "held"

        async def enter() -> None:
            async with runs.slot():
                pass

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(enter(), timeout=0.5)
        assert process.wait(timeout=10) == 0
        await asyncio.wait_for(enter(), timeout=5)

    async def test_a_record_naming_each_method_by_its_record_reads_as_one_naming_it_by_id(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        stored = finished_run(uuid.UUID(int=1))
        written_naming_whole_methods(tmp_path, stored)
        read = await runs.get_run(stored.id)
        assert read.result is not None and stored.result is not None
        assert read.result.gating_method == METHOD.id
        assert [category.method_id for category in read.result.categories] == [METHOD.id]
        assert read.result.categories[0].summary == stored.result.categories[0].summary
        assert read.result.categories[0].samples == SAMPLES

    async def test_a_store_holding_such_a_record_lists_it_and_posts_another(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        stored = finished_run(uuid.UUID(int=1))
        written_naming_whole_methods(tmp_path, stored)
        assert [run.id for run in await runs.list_runs()] == [stored.id]
        posted = await runs.post_run(draft(stored.product_system_id))
        assert [run.id for run in await runs.list_runs()] == [posted.id, stored.id]

    async def test_a_record_this_version_cannot_read_is_refused_by_name(
        self, runs: FilesystemRuns, tmp_path: Path
    ) -> None:
        posted = await runs.post_run(draft(uuid.UUID(int=1)))
        record = tmp_path / "runs" / str(posted.id) / "run.json"
        stored = json.loads(record.read_text(encoding="utf-8"))
        del stored["at_hash"]
        record.write_text(json.dumps(stored), encoding="utf-8")
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
