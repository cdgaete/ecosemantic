from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ecosemantic.ports.types import Run, RunDraft, RunPatch, RunProgress


def draft() -> RunDraft:
    return RunDraft(
        product_system_id=uuid.UUID(int=1),
        at_hash="9c1d" + "0" * 60,
        demand=[],
        methods=[],
        config={"n_min": 30, "n_max": 200, "rel_se_target": 0.05, "seed": 1},
    )


def test_a_draft_carries_the_key_the_run_is_pinned_to() -> None:
    made = draft()
    assert made.at_hash.startswith("9c1d") and made.config.n_min == 30


def test_a_fresh_run_is_queued_with_no_progress_and_no_result() -> None:
    run = Run(id=uuid.uuid4(), posted_at=datetime.now(UTC), **draft().model_dump())
    assert run.status == "queued" and run.open is True
    assert run.progress == RunProgress(iterations=0, worst_rel_se=None)
    assert run.result is None and run.error is None
    assert run.finished_at is None and run.cancel_requested is False
    assert run.pid is None


def test_a_patch_names_only_what_changes() -> None:
    patch = RunPatch(status="running")
    assert patch.model_dump(exclude_unset=True) == {"status": "running"}


def test_a_status_the_vocabulary_does_not_name_is_refused() -> None:
    with pytest.raises(ValidationError):
        Run(id=uuid.uuid4(), posted_at=datetime.now(UTC), status="paused", **draft().model_dump())
