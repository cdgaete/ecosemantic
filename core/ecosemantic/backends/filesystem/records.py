"""A record folder: one directory per record under its kind's directory, the record replaced
whole under a lock both processes take."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

from filelock import AsyncFileLock, FileLock
from pydantic import BaseModel, ValidationError

from ecosemantic.backends.filesystem.watching import touched
from ecosemantic.backends.retry import read_bytes, replace
from ecosemantic.errors import NotFound, Unavailable

SLOT_FILE = "slot.lock"
POST_LOCK = "post.lock"


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


class RecordFolder[T: BaseModel]:
    """The records of one kind, as one JSON file per record in a folder of its own.

    A record is written from another process while this one reads it, so it is replaced whole,
    never rewritten in place, and every change is read and written under a lock both take.
    """

    def __init__(self, root: Path, kind: str, record_file: str, model: type[T], noun: str) -> None:
        self.root = root
        self.kind = kind
        self.record_file = record_file
        self.model = model
        self.noun = noun

    def folder(self, record_id: uuid.UUID) -> Path:
        """The directory of one record under its kind's directory, whether or not it exists."""
        return self.root / self.kind / str(record_id)

    def lock(self, record_id: uuid.UUID) -> FileLock:
        """The record's file lock, taken by every read-and-write of it, from either process."""
        folder = self.root / self.kind
        folder.mkdir(parents=True, exist_ok=True)
        return FileLock(folder / f"{record_id}.lock")

    def post_lock(self) -> FileLock:
        """The lock every poster of this kind takes, so two cannot mint the same posted time."""
        folder = self.root / self.kind
        folder.mkdir(parents=True, exist_ok=True)
        return FileLock(folder / POST_LOCK)

    def read(self, record_id: uuid.UUID) -> T:
        """One record, or NotFound when no folder holds it."""
        record = self.folder(record_id) / self.record_file
        if not record.is_file():
            raise NotFound(f"no {self.noun} {record_id}")
        return self._parsed(record)

    def write(self, record_id: uuid.UUID, record: T) -> T:
        """The record written, staged beside its file and moved over it within the bounded
        retry, so a reader sees the whole of one version or the whole of the other."""
        folder = self.folder(record_id)
        folder.mkdir(parents=True, exist_ok=True)
        staged = folder / f"{self.record_file}.tmp"
        staged.write_bytes(record.model_dump_json(indent=1).encode("utf-8"))
        replace(staged, folder / self.record_file)
        return record

    def patch(self, record_id: uuid.UUID, change: Callable[[T], T]) -> T:
        """The record with the change applied, read and written under its lock."""
        with self.lock(record_id):
            return self.write(record_id, change(self.read(record_id)))

    def post(self, construct: Callable[[datetime], T]) -> T:
        """A new record posted under the kind's lock, its posted time advanced past the newest
        stored so two posters cannot mint the same instant."""
        with self.post_lock():
            record = construct(self._next_posted_at())
            return self.write(cast(Posted, record).id, record)

    def _next_posted_at(self) -> datetime:
        """The posted time of the next record of this kind: the clock, advanced past the newest."""
        newest = max(
            (record.posted_at for record in cast(Iterable[Posted], self.all())), default=None
        )
        return next_posted_at(now(), newest)

    def all(self) -> list[T]:
        """Every record of this kind."""
        folder = self.root / self.kind
        if not folder.is_dir():
            return []
        return [
            self._parsed(path / self.record_file)
            for path in folder.iterdir()
            if (path / self.record_file).is_file()
        ]

    def changed(self) -> AsyncGenerator[uuid.UUID]:
        """Every record any process wrote under this kind's directory, from the moment this is
        called: the watch is armed eagerly, so a write between this call and the first read is
        announced."""
        queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        watching = asyncio.create_task(self._watch(touched(self.root / self.kind), queue))

        async def iterate() -> AsyncGenerator[uuid.UUID]:
            try:
                while True:
                    yield await queue.get()
            finally:
                watching.cancel()

        return iterate()

    async def _watch(
        self, batches: AsyncIterator[set[Path]], queue: asyncio.Queue[uuid.UUID]
    ) -> None:
        async for batch in batches:
            found = {record for path in batch if (record := self._record_of(path)) is not None}
            for record_id in sorted(found, key=str):
                if (self.folder(record_id) / self.record_file).is_file():
                    queue.put_nowait(record_id)

    def _record_of(self, path: Path) -> uuid.UUID | None:
        """The record a written path belongs to, or none for a path that names no record."""
        folder = self.root / self.kind
        try:
            first = path.resolve().relative_to(folder.resolve()).parts[0]
        except (ValueError, IndexError):
            return None
        try:
            return uuid.UUID(first)
        except ValueError:
            return None

    def slot(self) -> AsyncFileLock:
        """The single slot every process over this directory takes, released when its holder's
        process ends. Each try is non-blocking on the event loop, so a caller cancelled while it
        waits holds nothing."""
        folder = self.root / self.kind
        folder.mkdir(parents=True, exist_ok=True)
        return AsyncFileLock(folder / SLOT_FILE, run_in_executor=False)

    def _parsed(self, record: Path) -> T:
        """The record parsed, or Unavailable naming it and the first field this version cannot
        read in it."""
        try:
            return self.model.model_validate_json(read_bytes(record))
        except ValidationError as error:
            first = error.errors(include_url=False)[0]
            field = ".".join(str(part) for part in first["loc"])
            raise Unavailable(
                f"{self.noun} {record.parent.name} cannot be read by this version: "
                f"{field}: {first['msg']}",
                hint=f"remove {record.parent} to list and start {self.noun}s again",
            ) from error
