"""What an answer held, in short: enough to show what a call returned without keeping it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

SUMMARY_ITEMS = 5


class SummaryItem(BaseModel):
    """One thing an answer listed: what to call it, and the kind of reference that opens it."""

    label: str
    detail: str | None = None
    kind: Literal["background", "elementary_flow"] | None = None
    database: str | None = None
    ref: str | None = None


class SummaryScore(BaseModel):
    """One score an answer carried."""

    method: str
    value: float
    unit: str


class Summary(BaseModel):
    """How many items an answer held and whether there were more, its first items, its scores."""

    count: int | None = None
    more: bool = False
    items: list[SummaryItem] = Field(default_factory=list)
    scores: list[SummaryScore] = Field(default_factory=list)


@runtime_checkable
class Itemised(Protocol):
    def summary_item(self) -> SummaryItem: ...


@runtime_checkable
class Summarising(Protocol):
    def summarise(self) -> Summary | None: ...


def listed(items: Sequence[object], more: bool) -> Summary:
    """The summary of a listing: its count, whether it went on, and its first items."""
    first = [item for item in items[:SUMMARY_ITEMS] if isinstance(item, Itemised)]
    return Summary(count=len(items), more=more, items=[item.summary_item() for item in first])
