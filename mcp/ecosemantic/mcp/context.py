"""What one server process holds: the ports, the resolver, who is writing, the locks, the event
bus every write publishes to, the directories a run's worker is started over, the accounts the
environment carries, and the client that introduced itself."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from ecosemantic.events import EventBus
from ecosemantic.mcp.calls import current
from ecosemantic.model.entities import Actor
from ecosemantic.ports.activity import ActivityPort
from ecosemantic.ports.calculation import CalculationPort
from ecosemantic.ports.install import InstallLauncher, InstallPort
from ecosemantic.ports.inventory import InventoryPort
from ecosemantic.ports.resolver import Resolver
from ecosemantic.ports.run import RunLauncher, RunPort
from ecosemantic.ports.search import SearchPort
from ecosemantic.ports.storage import StoragePort
from ecosemantic.ports.types import Account, CredentialKind

AGENT = Actor(kind="agent", id="mcp")


def _nothing() -> None:
    return None


def page_under(view_url: str, path: str, params: Sequence[tuple[str, str]] = ()) -> str:
    """A page at the path under the announced URL, carrying the query parameters given and the
    token the announced URL carries."""
    base, _, token = view_url.partition("?")
    link = f"{base.rstrip('/')}{path}"
    query = "&".join(part for part in (urlencode(list(params)), token) if part)
    return f"{link}?{query}" if query else link


@dataclass(frozen=True)
class ServerContext:
    """The bound ports a tool function is called with; it names no backend."""

    inventory: InventoryPort
    search: SearchPort
    calculation: CalculationPort
    storage: StoragePort
    resolver: Resolver
    actor: Actor
    runs: RunPort
    activity: ActivityPort
    launcher: RunLauncher
    installs: InstallPort
    installer: InstallLauncher
    systems_dir: Path
    data_dir: Path
    uploads_dir: Path
    credentials: dict[CredentialKind, Account] = field(default_factory=dict)
    client: dict[str, str] = field(default_factory=dict)
    release: Callable[[], None] = _nothing
    locks: dict[uuid.UUID, asyncio.Lock] = field(default_factory=dict)
    watchers: set[asyncio.Task[None]] = field(default_factory=set)
    events: EventBus = field(default_factory=EventBus)
    view_url: str | None = None
    agent: str | None = None

    def lock(self, product_system_id: uuid.UUID) -> asyncio.Lock:
        """The lock a write on one product system holds from its read to its write."""
        return self.locks.setdefault(product_system_id, asyncio.Lock())

    def acting(self) -> Actor:
        """Who a write is made by: the agent of the tool call in progress, or the context's own
        actor outside one."""
        call = current()
        if call is None:
            return self.actor
        return Actor(kind="agent", id=call.agent, name=call.client)

    def page_link(
        self,
        product_system_id: uuid.UUID,
        path: str = "",
        params: Sequence[tuple[str, str]] = (),
    ) -> str | None:
        """A page under one product system with the page's own query parameters, keeping the
        token the announced URL carries; None where no view is served."""
        if self.view_url is None:
            return None
        return page_under(self.view_url, f"/systems/{product_system_id}{path}", params)

    def page_at(self, path: str) -> str | None:
        """A page at the path given, keeping the token the announced URL carries; None where no
        view is served."""
        if self.view_url is None:
            return None
        return page_under(self.view_url, path)

    def deep_link(self, product_system_id: uuid.UUID) -> str | None:
        """The page of one product system, keeping the token the announced URL carries."""
        return self.page_link(product_system_id)

    def keep_watching(self, run: Coroutine[object, object, None]) -> None:
        """Keep a run's watcher running past the call that started it, until the run settles."""
        task = asyncio.create_task(run)
        self.watchers.add(task)
        task.add_done_callback(self.watchers.discard)

    def close(self) -> None:
        """Stop watching runs, which carry on without this process, and release what the bound
        backends hold."""
        for task in self.watchers:
            task.cancel()
        self.release()
