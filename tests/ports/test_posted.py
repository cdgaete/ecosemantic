from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from ecosemantic.ports.posted import newest_first, next_posted_at


class Item(BaseModel):
    id: uuid.UUID
    posted_at: datetime


def test_a_first_record_is_posted_at_the_clock() -> None:
    clock = datetime(2024, 1, 1, tzinfo=UTC)
    assert next_posted_at(clock, None) == clock


def test_a_record_posted_at_a_tied_clock_is_one_microsecond_past_the_newest() -> None:
    clock = datetime(2024, 1, 1, tzinfo=UTC)
    assert next_posted_at(clock, clock) == clock + timedelta(microseconds=1)


def test_records_list_newest_first_the_id_breaking_a_tie() -> None:
    at = datetime(2024, 1, 1, tzinfo=UTC)
    low, high = Item(id=uuid.UUID(int=1), posted_at=at), Item(id=uuid.UUID(int=2), posted_at=at)
    later = Item(id=uuid.UUID(int=0), posted_at=at + timedelta(seconds=1))
    assert newest_first([low, later, high]) == [later, high, low]
