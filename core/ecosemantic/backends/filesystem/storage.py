"""The storage port over a directory of packages: one package directory per product system."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from filelock import FileLock

from ecosemantic.backends.filesystem.watching import touched
from ecosemantic.compute.links import pinned, pins
from ecosemantic.errors import Conflict, NotFound
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
from ecosemantic.package.sidecar import LAYOUT_FILE, SIDECAR_DIR, read_sidecar
from ecosemantic.ports.resolver import Resolver
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
            raise NotFound(f"no product_system {product_system_id}")
        return path

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
        with self._lock(str(product_system_id)):
            return read_package(self._dir(product_system_id))[0]

    def _version(self, product_system_id: uuid.UUID, content_hash: str) -> ProductSystem:
        with self._lock(str(product_system_id)):
            return read_version(self._dir(product_system_id), content_hash)

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
        with self._lock(str(product_system_id)):
            shutil.rmtree(self._dir(product_system_id))

    def _log(self, product_system_id: uuid.UUID) -> list[LogEntry]:
        with self._lock(str(product_system_id)):
            return read_log(self._dir(product_system_id))

    def _layout(self, product_system_id: uuid.UUID) -> Layout:
        with self._lock(str(product_system_id)):
            stored = self._dir(product_system_id) / SIDECAR_DIR / LAYOUT_FILE
            if not stored.is_file():
                return Layout()
            return Layout.model_validate_json(stored.read_bytes())

    def _put_layout(self, product_system_id: uuid.UUID, layout: Layout) -> Layout:
        with self._lock(str(product_system_id)):
            stored = self._dir(product_system_id) / SIDECAR_DIR / LAYOUT_FILE
            stored.write_bytes(layout.model_dump_json(indent=1).encode("utf-8"))
            return layout

    def _requests(self, product_system_id: uuid.UUID) -> list[Request]:
        with self._lock(str(product_system_id)):
            return read_requests(self._dir(product_system_id))

    def _post(self, product_system_id: uuid.UUID, draft: RequestDraft) -> Request:
        with self._lock(str(product_system_id)):
            root = self._dir(product_system_id)
            queue = read_requests(root)
            request = next_request(queue, draft)
            write_requests(root, [*queue, request])
            return request

    def _resolve(
        self, product_system_id: uuid.UUID, request_id: uuid.UUID, outcome: Outcome
    ) -> Request:
        with self._lock(str(product_system_id)):
            root = self._dir(product_system_id)
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
        with self._lock(str(product_system_id)):
            root = self._dir(product_system_id)
            return write_returned(
                exported_root, root, actor, self.resolver, linked=linked, at_entry=at_entry
            )

    def _owner(self, path: Path) -> uuid.UUID | None:
        """The product system a written path belongs to, or none for a path that names no
        system: the lock files, the token, the activity directory."""
        try:
            first = path.resolve().relative_to(self.root.resolve()).parts[0]
        except (ValueError, IndexError):
            return None
        try:
            return uuid.UUID(first)
        except ValueError:
            return None

    async def _watch(
        self, batches: AsyncIterator[set[Path]], queue: asyncio.Queue[StoreChange]
    ) -> None:
        async for batch in batches:
            owners = {owner for path in batch if (owner := self._owner(path)) is not None}
            for owner in sorted(owners, key=str):
                queue.put_nowait(
                    StoreChange(
                        product_system_id=owner,
                        gone=not (self.root / str(owner) / SIDECAR_DIR).is_dir(),
                    )
                )

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
        with self._lock(str(product_system_id)):
            zip_package(self._dir(product_system_id), destination)

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
