"""The request queue beside the log: JSON lines under root/ecosemantic/, and the steps over it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from ecosemantic.errors import Conflict, Invalid, NotFound
from ecosemantic.package.sidecar import read_lines, write_lines
from ecosemantic.ports.types import Outcome, Request, RequestDraft

REQUESTS_FILE = "requests.jsonl"


def next_request(
    requests: list[Request], draft: RequestDraft, now: datetime | None = None
) -> Request:
    """The request that follows the last one: a fresh id, the next seq, no outcome."""
    return Request(
        id=uuid.uuid4(),
        seq=(requests[-1].seq + 1) if requests else 1,
        timestamp=now or datetime.now(UTC),
        actor=draft.actor,
        kind=draft.kind,
        at_hash=draft.at_hash,
        message=draft.message,
        entity=draft.entity,
        entity_id=draft.entity_id,
    )


def resolve(requests: list[Request], request_id: uuid.UUID, outcome: Outcome) -> list[Request]:
    """The queue with one request carrying its outcome; unknown, approval and resolved raise."""
    for index, request in enumerate(requests):
        if request.id != request_id:
            continue
        if request.kind == "approve":
            raise Invalid(f"request {request_id} is an approval and is never open")
        if request.outcome is not None:
            raise Conflict(f"request {request_id} is already {request.outcome.resolution}")
        resolved = request.model_copy(update={"outcome": outcome})
        return [*requests[:index], resolved, *requests[index + 1 :]]
    raise NotFound(f"no request {request_id}")


def write_requests(root: Path, requests: list[Request]) -> None:
    """Write the queue as JSON lines under root/ecosemantic/."""
    lines = (request.model_dump_json(exclude={"open"}) for request in requests)
    write_lines(root, REQUESTS_FILE, lines)


def read_requests(root: Path) -> list[Request]:
    """The queue under root/ecosemantic/, or an empty list when the file does not exist."""
    return [Request.model_validate_json(line) for line in read_lines(root, REQUESTS_FILE)]
