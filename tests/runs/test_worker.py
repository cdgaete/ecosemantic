from __future__ import annotations

import asyncio
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from ecosemantic.backends.filesystem.run_folder import run_dir
from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.compute.parameters import materialize
from ecosemantic.mcp.calculation import demand_of
from ecosemantic.mcp.context import ServerContext
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import ProductSystem
from ecosemantic.ports.types import MonteCarloConfig, Run, RunDraft, RunPatch, System
from ecosemantic.runs.worker import main, run_once
from tests.fixture_data import FIXTURE_DB


async def queued(
    context: ServerContext,
    runs_root: Path,
    system: ProductSystem,
    n: int,
) -> tuple[FilesystemRuns, uuid.UUID]:
    """A queued run over the fixture system, pinned at the hash it is stored under."""
    runs = FilesystemRuns(runs_root)
    methods = await context.inventory.list_methods(system.database.name, None)
    run = await runs.post_run(
        RunDraft(
            product_system_id=system.id,
            at_hash=content_hash(system),
            demand=demand_of(system, None),
            methods=methods[:1],
            config=MonteCarloConfig(n=n, n_min=1, n_max=200, seed=12345),
        )
    )
    return runs, run.id


async def test_the_worker_carries_a_queued_run_to_done(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
) -> None:
    runs, run_id = await queued(context, tmp_path, fixture_system_stored, 4)
    await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run_id)
    done = await runs.get_run(run_id)
    assert done.status == "done"
    assert done.result is not None and done.result.n == 4
    assert done.result.database == await context.inventory.get_database(FIXTURE_DB)
    assert done.progress.iterations == 4
    assert done.started_at is not None and done.finished_at is not None
    system = System(
        database=fixture_system_stored.database.name,
        product_system=materialize(fixture_system_stored),
    )
    # the same seed and config answer the same samples in this process
    assert done.result == await context.calculation.monte_carlo(
        system, done.demand, done.methods, done.config
    )


async def test_the_worker_beats_its_heartbeat_at_start_and_at_each_draw(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs, run_id = await queued(context, tmp_path, fixture_system_stored, 4)
    beaten: list[Path] = []
    monkeypatch.setattr("ecosemantic.runs.worker.beat", beaten.append)
    await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run_id)
    assert (await runs.get_run(run_id)).status == "done"
    # once before the run reads its system, then once for each of the four draws
    assert beaten == [run_dir(tmp_path, run_id)] * 5


async def test_a_run_asked_to_stop_is_cancelled_and_keeps_what_it_had(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
) -> None:
    runs, run_id = await queued(context, tmp_path, fixture_system_stored, 50)
    await runs.update_run(run_id, RunPatch(cancel_requested=True))
    await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run_id)
    stopped = await runs.get_run(run_id)
    assert stopped.status == "cancelled"
    # it stopped at the first report and kept that sample
    assert stopped.result is not None and 0 < stopped.result.n < 50


async def test_a_hash_the_store_does_not_hold_fails_as_the_envelope(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
) -> None:
    runs = FilesystemRuns(tmp_path)
    run = await runs.post_run(
        RunDraft(
            product_system_id=fixture_system_stored.id,
            at_hash="0" * 64,
            demand=[],
            methods=[],
            config=MonteCarloConfig(n=2),
        )
    )
    args = ["--systems-dir", str(systems_dir), "--data-dir", str(bundle_dir)]
    args += ["--runs-dir", str(tmp_path), "--run", str(run.id)]
    assert await asyncio.to_thread(main, args) == 0
    failed = await runs.get_run(run.id)
    assert failed.status == "failed"
    assert failed.error is not None and failed.error.error == "not_found"


async def test_a_system_on_another_build_fails_as_the_envelope(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
) -> None:
    system = fixture_system_stored.model_copy(deep=True, update={"hash": None})
    system.id = uuid.uuid5(system.id, "worker on another build")
    system.database = system.database.model_copy(update={"fingerprint": "0" * 64})
    await context.storage.put_product_system(system, context.actor, "created")
    stored = await context.storage.get_product_system(system.id)
    runs, run_id = await queued(context, tmp_path, stored, 2)
    await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run_id)
    failed = await runs.get_run(run_id)
    assert failed.status == "failed" and failed.error is not None
    assert failed.error.error == "conflict" and failed.error.details["named"] == "0" * 64


async def test_a_crash_inside_the_sampling_is_recorded_and_still_raised(
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
) -> None:
    runs = FilesystemRuns(tmp_path)
    run = await runs.post_run(
        RunDraft(
            product_system_id=fixture_system_stored.id,
            at_hash=content_hash(fixture_system_stored),
            demand=demand_of(fixture_system_stored, None),
            methods=[],
            config=MonteCarloConfig(n=2),
        )
    )
    # no method leaves no sample stream to report on
    with pytest.raises(IndexError):
        await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run.id)
    failed = await runs.get_run(run.id)
    assert failed.status == "failed" and failed.finished_at is not None
    assert failed.error is not None and failed.error.error == "failed"


def test_the_module_runs_as_a_subprocess() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "ecosemantic.runs.worker", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert out.returncode == 0 and "--run" in out.stdout


def test_main_refuses_without_its_arguments() -> None:
    try:
        main([])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("main accepted no arguments")


async def test_the_worker_reads_the_record_once_an_iteration(
    context: ServerContext,
    systems_dir: Path,
    bundle_dir: Path,
    tmp_path: Path,
    fixture_system_stored: ProductSystem,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs, run_id = await queued(context, tmp_path, fixture_system_stored, 4)
    reads: list[uuid.UUID] = []
    read = FilesystemRuns.read_record

    def counted(self: FilesystemRuns, found: uuid.UUID) -> Run:
        reads.append(found)
        return read(self, found)

    monkeypatch.setattr(FilesystemRuns, "read_record", counted)
    await asyncio.to_thread(run_once, systems_dir, bundle_dir, tmp_path, run_id)
    # two reads and two patches around the sampling, then one patch an iteration
    assert len(reads) == 8
