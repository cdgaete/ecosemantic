"""The storage port over a directory of packages: one package directory per product system."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from ecosemantic.backends.filesystem.records import record_of, sweep_locks
from ecosemantic.backends.filesystem.watching import touched
from ecosemantic.compute.links import pinned, pins
from ecosemantic.errors import Conflict
from ecosemantic.files import forget
from ecosemantic.model.entities import Actor, ProductSystem
from ecosemantic.package.log import read_log
from ecosemantic.package.package import (
    read_package,
    read_version,
    unzip_package,
    write_package,
    write_returned,
    zip_package,
)
from ecosemantic.package.requests import next_request, read_requests, resolve, write_requests
from ecosemantic.package.sidecar import SIDECAR_DIR, read_layout, read_sidecar, write_layout
from ecosemantic.ports.resolver import Resolver
from ecosemantic.ports.storage import no_product_system
from ecosemantic.ports.types import (
    Layout,
    LogEntry,
    Outcome,
    ProductSystemSummary,
    Request,
    RequestDraft,
    Restored,
    Source,
    StoreChange,
)


class FilesystemStorage:
    """Product systems as package directories under one root; the directory is the package."""

    def __init__(self, root: Path, resolver: Resolver) -> None:
        self.root = root
        self.resolver = resolver

    def _lock(self, name: str) -> FileLock:
        self.root.mkdir(parents=True, exist_ok=True)
        return FileLock(self.root / f"{name}.lock")

    def _dir(self, product_system_id: uuid.UUID) -> Path:
        path = self.root / str(product_system_id)
        if not (path / SIDECAR_DIR).is_dir():
            raise no_product_system(product_system_id)
        return path

    @contextmanager
    def _held(self, product_system_id: uuid.UUID) -> Iterator[Path]:
        """The folder of a stored product system under its lock; a system the store does not
        hold is refused before a lock is made for it, and again once the lock is held."""
        self._dir(product_system_id)
        with self._lock(str(product_system_id)):
            yield self._dir(product_system_id)

    def sweep(self) -> None:
        """Remove the lock file of every product system this store does not hold."""
        sweep_locks(self.root)

    def _list(self) -> list[ProductSystemSummary]:
        if not self.root.is_dir():
            return []
        summaries = []
        for path in sorted(self.root.iterdir()):
            if (path / SIDECAR_DIR).is_dir():
                with self._lock(path.name):
                    summaries.append(ProductSystemSummary.of(read_sidecar(path).product_system))
        return summaries

    def _read(self, product_system_id: uuid.UUID) -> ProductSystem:
        with self._held(product_system_id) as root:
            return read_package(root)[0]

    def _version(self, product_system_id: uuid.UUID, content_hash: str) -> ProductSystem:
        with self._held(product_system_id) as root:
            return read_version(root, product_system_id, content_hash)

    def _pinned(self, product_system: ProductSystem) -> dict[uuid.UUID, ProductSystem]:
        """Each system the document links, as the store holds it at the pin; each is read under
        its own lock, before the writer takes the document's."""
        return {
            ref.product_system_id: self._version(ref.product_system_id, pinned(ref))
            for ref in pins(product_system)
        }

    def _put(
        self, product_system: ProductSystem, actor: Actor, message: str, source: Source
    ) -> LogEntry:
        root = self.root / str(product_system.id)
        linked = self._pinned(product_system)
        with self._lock(str(product_system.id)):
            return write_package(
                product_system, root, actor, message, self.resolver, source, linked=linked
            )

    def _delete(self, product_system_id: uuid.UUID) -> None:
        self._dir(product_system_id)
        lock = self._lock(str(product_system_id))
        with lock:
            shutil.rmtree(self._dir(product_system_id))
            forget(lock)

    def _log(self, product_system_id: uuid.UUID) -> list[LogEntry]:
        with self._held(product_system_id) as root:
            return read_log(root)

    def _layout(self, product_system_id: uuid.UUID) -> Layout:
        with self._held(product_system_id) as root:
            return read_layout(root)

    def _put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout:
        with self._held(product_system_id) as root:
            write_layout(root, layout)
            return layout

    def _requests(self, product_system_id: uuid.UUID) -> list[Request]:
        with self._held(product_system_id) as root:
            return read_requests(root)

    def _post(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request:
        with self._held(product_system_id) as root:
            queue = read_requests(root)
            request = next_request(queue, draft)
            write_requests(root, [*queue, request])
            return request

    def _resolve(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request:
        with self._held(product_system_id) as root:
            queue = resolve(read_requests(root), request_id, outcome)
            write_requests(root, queue)
            return next(r for r in queue if r.id == request_id)

    def _return(
        self,
        product_system_id: uuid.UUID,
        exported_root: Path,
        actor: Actor,
        at_entry: int | None,
    ) -> LogEntry:
        linked = self._pinned(self._read(product_system_id))
        with self._held(product_system_id) as root:
            return write_returned(
                exported_root, root, actor, self.resolver, linked=linked, at_entry=at_entry
            )

    def _owner(self, path: Path) -> uuid.UUID | None:
        """The product system a written path belongs to, or none for a path that names no
        system: the lock files, the token, the activity directory."""
        return record_of(path, self.root)

    async def _watch(
        self, batches: AsyncIterator[set[Path]], queue: asyncio.Queue[StoreChange]
    ) -> None:
        async for batch in batches:
            owners = {owner for path in batch if (owner := self._owner(path)) is not None}
            for owner in sorted(owners, key=str):
                directory = self.root / str(owner)
                if directory.is_dir() and not (directory / SIDECAR_DIR).is_dir():
                    continue
                queue.put_nowait(StoreChange(product_system_id=owner, gone=not directory.is_dir()))

    def changes(self) -> AsyncIterator[StoreChange]:
        """What any process wrote under the root, from the moment this is called: the watch is
        armed eagerly, so a write between this call and the first read is announced."""
        queue: asyncio.Queue[StoreChange] = asyncio.Queue()
        watching = asyncio.create_task(self._watch(touched(self.root), queue))

        async def iterate() -> AsyncIterator[StoreChange]:
            try:
                while True:
                    yield await queue.get()
            finally:
                watching.cancel()

        return iterate()

    async def list_product_systems(self) -> list[ProductSystemSummary]:
        return await asyncio.to_thread(self._list)

    async def get_product_system(self, product_system_id: uuid.UUID) -> ProductSystem:
        return await asyncio.to_thread(self._read, product_system_id)

    async def get_version(self, product_system_id: uuid.UUID, content_hash: str) -> ProductSystem:
        return await asyncio.to_thread(self._version, product_system_id, content_hash)

    async def put_product_system(
        self, product_system: ProductSystem, actor: Actor, message: str, source: Source = "mcp"
    ) -> LogEntry:
        return await asyncio.to_thread(self._put, product_system, actor, message, source)

    async def delete_product_system(self, product_system_id: uuid.UUID, actor: Actor) -> None:
        await asyncio.to_thread(self._delete, product_system_id)

    async def log(self, product_system_id: uuid.UUID) -> list[LogEntry]:
        return await asyncio.to_thread(self._log, product_system_id)

    async def get_layout(self, product_system_id: uuid.UUID) -> Layout:
        return await asyncio.to_thread(self._layout, product_system_id)

    async def put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout:
        return await asyncio.to_thread(self._put_layout, product_system_id, layout)

    async def post_request(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request:
        return await asyncio.to_thread(self._post, product_system_id, draft)

    async def list_requests(
        self, product_system_id: uuid.UUID, open_only: bool = False
    ) -> list[Request]:
        queue = await asyncio.to_thread(self._requests, product_system_id)
        return [r for r in queue if r.open] if open_only else queue

    async def resolve_request(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request:
        return await asyncio.to_thread(self._resolve, product_system_id, request_id, outcome)

    async def return_package(
        self,
        product_system_id: uuid.UUID,
        exported_root: Path,
        actor: Actor,
        at_entry: int | None = None,
    ) -> LogEntry:
        return await asyncio.to_thread(
            self._return, product_system_id, exported_root, actor, at_entry
        )

    def _export(self, product_system_id: uuid.UUID, destination: Path) -> None:
        with self._held(product_system_id) as root:
            zip_package(root, destination)

    def _restore(self, source: Path) -> Restored:
        with tempfile.TemporaryDirectory() as work:
            staged = Path(work) / "package"
            unzip_package(source, staged)
            system, _ = read_package(staged)
            with self._lock(str(system.id)):
                held = self.root / str(system.id)
                if (held / SIDECAR_DIR).is_dir():
                    current = read_package(held)[0].hash
                    if current == system.hash:
                        return "unchanged"
                    raise Conflict(
                        f"{system.name} is held at {current}; "
                        f"the model package carries {system.hash}"
                    )
                shutil.copytree(staged, held)
                return "added"

    async def export_package(self, product_system_id: uuid.UUID, destination: Path) -> None:
        await asyncio.to_thread(self._export, product_system_id, destination)

    async def restore_package(self, source: Path) -> Restored:
        return await asyncio.to_thread(self._restore, source)
