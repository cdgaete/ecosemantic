"""What one server process holds: the ports, the resolver, who is writing, the person a copy of
it names, the locks, the event bus every write publishes to, the directories a run's worker is
started over, the accounts the environment carries, and the client that introduced itself.

What a server is given in place of one context is a `Callers`, and `ServerContext` is the one
that answers itself."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlencode

from ecosemantic.events import EventBus, following
from ecosemantic.mcp.calls import current
from ecosemantic.model.entities import Actor, ActorKind, Person
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

Start = Literal["tray", "terminal", "headless"]


def _nothing() -> None:
    return None


def _person_actor(person: Person) -> Actor:
    """The actor a write by the person names."""
    return Actor(kind="person", id=person.id, name=person.name)


@dataclass(frozen=True)
class AccountStart:
    """How the engine was started, the loopback address of the accounts screen it serves, and the
    bridge page's address when it is bridged."""

    start: Start = "headless"
    screen: str | None = None
    page: str | None = None


class Callers(Protocol):
    """What a server is given to reach the context of each request's caller, and to follow the
    stores it serves."""

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext: ...

    def serving(self) -> AbstractAsyncContextManager[None]: ...


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
    accounts: AccountStart = field(default_factory=AccountStart)
    client: dict[str, str] = field(default_factory=dict)
    release: Callable[[], None] = _nothing
    locks: dict[uuid.UUID, asyncio.Lock] = field(default_factory=dict)
    watchers: set[asyncio.Task[None]] = field(default_factory=set)
    events: EventBus = field(default_factory=EventBus)
    view_url: str | None = None
    agent: str | None = None
    person: Person | None = None

    def lock(self, product_system_id: uuid.UUID) -> asyncio.Lock:
        """The lock a write on one product system holds from its read to its write."""
        return self.locks.setdefault(product_system_id, asyncio.Lock())

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        """This context, which is the one a server given it answers every request with."""
        return self

    def for_person(self, person: Person) -> ServerContext:
        """A copy of this context that names the person and shares every port, the locks, the bus
        and the watchers, with a client of its own."""
        return replace(self, person=person, client={})

    def serving(self) -> AbstractAsyncContextManager[None]:
        """Publish what other processes write to this context's store, for as long as the caller
        serves it."""
        return following(self.storage, self.runs, self.installs, self.events)

    def acting(self) -> Actor:
        """Who a write is made by: without a person, the agent of the call in progress or else the
        context's own actor; with one, the calling agent on the person's behalf or else the
        person."""
        call = current()
        if self.person is None:
            if call is None:
                return self.actor
            return Actor(kind="agent", id=call.agent, name=call.client)
        if call is not None and call.origin == "agent":
            return Actor(kind="agent", id=call.agent, name=call.client, on_behalf_of=self.person)
        return _person_actor(self.person)

    def placing(self) -> ActorKind:
        """Who put a card where a write holds it: the person at the page for a call the page made,
        else the kind `acting` answers. `acting` alone is not enough, because the page's call
        without a signed-in person answers an agent, and a drag is the person at the browser."""
        call = current()
        if call is not None and call.origin == "view":
            return "person"
        return self.acting().kind

    def posted_by(self, stated: str) -> Actor:
        """Who a route's write is made by: the person this context names, or, when it names none,
        the person the form states."""
        if self.person is not None:
            return _person_actor(self.person)
        return Actor(kind="person", name=stated)

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
