"""One run, in its own process: read the record, sample, and write back what happened."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.backends.filesystem.run_folder import beat, run_dir
from ecosemantic.backends.filesystem.runs import FilesystemRuns
from ecosemantic.backends.filesystem.storage import FilesystemStorage
from ecosemantic.backends.native.calculation import NativeCalculation
from ecosemantic.backends.native.inventory import NativeInventory
from ecosemantic.backends.native.store import NativeStore
from ecosemantic.compute.links import linked_documents
from ecosemantic.compute.parameters import materialize
from ecosemantic.engine.solver import SOLVERS
from ecosemantic.errors import EcoSemanticError, error_payload, failure_payload
from ecosemantic.package.resolver import InventoryResolver
from ecosemantic.ports.types import MonteCarloResult, RunPatch, RunProgress, System


def _reporter(
    runs: FilesystemRuns, run_id: uuid.UUID, folder: Path
) -> Callable[[int, float | None], bool]:
    """A callback for the sampling loop: beat the heartbeat, record the iteration, and stop when
    asked.

    It runs on the store's worker thread, so it reads and writes the record synchronously
    and never touches the event loop.
    """

    def watch(iterations: int, worst: float | None) -> bool:
        beat(folder)
        patched = runs.apply_patch(
            run_id, RunPatch(progress=RunProgress(iterations=iterations, worst_rel_se=worst))
        )
        return not patched.cancel_requested

    return watch


async def _carry(
    systems: Path, data: Path, runs_root: Path, run_id: uuid.UUID, solver: str
) -> None:
    runs = FilesystemRuns(runs_root)
    folder = run_dir(runs_root, run_id)
    beat(folder)
    store = NativeStore(data, solver)
    try:
        run = await runs.get_run(run_id)
        await runs.update_run(run_id, RunPatch(status="running", started_at=datetime.now(UTC)))
        resolver = InventoryResolver(NativeInventory(store))
        storage = FilesystemStorage(systems, resolver)
        stored = await storage.get_version(run.product_system_id, run.at_hash)
        linked = await linked_documents(stored, storage.get_version)
        system = System.of(materialize(stored), linked)
        result: MonteCarloResult = await NativeCalculation(store).monte_carlo(
            system,
            run.demand,
            run.methods,
            run.config,
            on_iteration=_reporter(runs, run_id, folder),
        )
        asked = (await runs.get_run(run_id)).cancel_requested
        await runs.update_run(
            run_id,
            RunPatch(
                status="cancelled" if asked else "done",
                result=result,
                finished_at=datetime.now(UTC),
            ),
        )
    except EcoSemanticError as error:
        await runs.update_run(
            run_id,
            RunPatch(status="failed", error=error_payload(error), finished_at=datetime.now(UTC)),
        )
    except Exception as error:
        await runs.update_run(
            run_id,
            RunPatch(
                status="failed",
                error=failure_payload(str(error)),
                finished_at=datetime.now(UTC),
            ),
        )
        raise
    finally:
        store.close()


def run_once(
    systems: Path, data: Path, runs_root: Path, run_id: uuid.UUID, solver: str = "superlu"
) -> None:
    """Carry one run to a terminal status, in this process, under the named solver."""
    asyncio.run(_carry(systems, data, runs_root, run_id, solver))


def main(argv: list[str] | None = None) -> int:
    """Carry the run the arguments name; 0 whatever status it reached, 2 on a usage error."""
    parser = argparse.ArgumentParser(prog="ecosemantic-run")
    parser.add_argument("--systems-dir", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--runs-dir", required=True, type=Path)
    parser.add_argument("--run", required=True, type=uuid.UUID)
    parser.add_argument("--solver", choices=SOLVERS, default="superlu")
    args = parser.parse_args(argv)
    run_once(args.systems_dir, args.data_dir, args.runs_dir, args.run, args.solver)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
