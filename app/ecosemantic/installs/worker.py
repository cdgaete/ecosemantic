"""One install, in its own process: read the record and the account, install the source, and write
back what happened."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue

from ecosemantic.backends.filesystem.installs import (
    FilesystemInstalls,
    install_dir,
    uploads_dir,
)
from ecosemantic.backends.filesystem.run_folder import beat, beating
from ecosemantic.errors import Cancelled, EcoSemanticError, error_payload, failure_payload
from ecosemantic.installs.handover import decoded
from ecosemantic.installs.sources import install_source
from ecosemantic.ports.types import (
    BEAT_SECONDS,
    Account,
    Install,
    InstallDraft,
    InstallPatch,
    InstallProgress,
    InstallTerms,
    Reporter,
)


def _refuse_when_asked(install: Install) -> None:
    """Raise `Cancelled` when the record asks this install to stop."""
    if install.cancel_requested:
        raise Cancelled(f"install {install.id} was asked to stop")


def _reporter(installs: FilesystemInstalls, install_id: uuid.UUID, folder: Path) -> Reporter:
    """A callback for the source's install: beat the heartbeat, record the step, and stop when the
    record asks to."""

    def report(progress: InstallProgress) -> None:
        beat(folder)
        _refuse_when_asked(installs.apply_patch(install_id, InstallPatch(progress=progress)))

    return report


def _discard_upload(data: Path, draft: InstallDraft) -> None:
    """Delete the package an install read, when it was uploaded under the data directory."""
    if draft.package is None:
        return
    package = Path(draft.package)
    if package.is_relative_to(uploads_dir(data)):
        package.unlink(missing_ok=True)


def recorded(summary: dict[str, JsonValue], folder: Path) -> dict[str, JsonValue]:
    """The summary an install's record carries: each of its lists written beside the record, their
    places holding their counts, and the files that hold them named."""
    record = dict(summary)
    for name, value in summary.items():
        if not isinstance(value, list):
            continue
        path = folder / f"{name}.json"
        path.write_text(json.dumps(value, indent=1) + "\n", "utf-8")
        record[name] = len(value)
        record[f"{name}_file"] = str(path)
    return record


def carry(data: Path, install_id: uuid.UUID, account: Account | None) -> None:
    """Install one database in this process, from the record the data directory holds and with the
    account the server handed over, leaving the record at the status the install reached and
    deleting the package it read when that package was uploaded under the data directory."""
    installs = FilesystemInstalls(data)
    folder = install_dir(data, install_id)
    folder.mkdir(parents=True, exist_ok=True)
    beat(folder)
    draft = installs.read_record(install_id).draft
    try:
        _refuse_when_asked(
            installs.apply_patch(
                install_id, InstallPatch(status="running", started_at=datetime.now(UTC))
            )
        )
        with beating(folder, BEAT_SECONDS):
            answer = install_source(data, draft, account, _reporter(installs, install_id, folder))
        if isinstance(answer, InstallTerms):
            installs.apply_patch(
                install_id,
                InstallPatch(
                    status="terms", terms=answer, finished_at=datetime.now(UTC), error=None
                ),
            )
        else:
            installs.apply_patch(
                install_id,
                InstallPatch(
                    status="done",
                    summary=recorded(answer, folder),
                    finished_at=datetime.now(UTC),
                    error=None,
                ),
            )
    except Cancelled:
        installs.apply_patch(
            install_id,
            InstallPatch(status="cancelled", finished_at=datetime.now(UTC), error=None),
        )
    except EcoSemanticError as error:
        installs.apply_patch(
            install_id,
            InstallPatch(
                status="failed", error=error_payload(error), finished_at=datetime.now(UTC)
            ),
        )
    except Exception as error:
        installs.apply_patch(
            install_id,
            InstallPatch(
                status="failed", error=failure_payload(str(error)), finished_at=datetime.now(UTC)
            ),
        )
        raise
    finally:
        _discard_upload(data, draft)


def main(argv: list[str] | None = None) -> int:
    """Carry the install the arguments name, with the account this process reads from its standard
    input; 0 whatever status it reached, 2 on a usage error."""
    parser = argparse.ArgumentParser(prog="ecosemantic-install")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--install", required=True, type=uuid.UUID)
    args = parser.parse_args(argv)
    carry(args.data_dir, args.install, decoded(sys.stdin.buffer.read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
