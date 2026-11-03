"""What orders the records of a listing: the time each was posted, newest first."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Posted(Protocol):
    """What a record carries for a listing: its id, and the time it was posted."""

    id: uuid.UUID
    posted_at: datetime


def newest_first[T: Posted](records: Iterable[T]) -> list[T]:
    """Records newest first, the id breaking a tie between two posted at once."""
    return sorted(records, key=lambda record: (record.posted_at, str(record.id)), reverse=True)


def now() -> datetime:
    """The current instant in UTC, the clock a record's posted time is measured from."""
    return datetime.now(UTC)


def next_posted_at(now: datetime, newest: datetime | None) -> datetime:
    """A new record's posted time, newest-first independent of the clock's resolution: the
    clock, or one microsecond past the store's newest when the clock would tie two."""
    if newest is None:
        return now
    return max(now, newest + timedelta(microseconds=1))
