"""A host of several signed-in people: the stores it serves, the caller each request names, and
the clients a test reaches its endpoint with."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.shared._httpx_utils import McpHttpClientFactory
from mcp.shared.inbound import (
    CLIENT_CAPABILITIES_META_KEY,
    CLIENT_INFO_META_KEY,
    MCP_METHOD_HEADER,
    MCP_NAME_HEADER,
    MCP_PROTOCOL_VERSION_HEADER,
    NAME_BEARING_METHODS,
    PROTOCOL_VERSION_META_KEY,
)
from mcp.types import Implementation
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from ecosemantic.errors import Unauthorised
from ecosemantic.events import EventBus, following
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.entities import Person
from tests.memory_activity import MemoryActivity
from tests.memory_installs import MemoryInstaller, MemoryInstalls
from tests.memory_runs import MemoryLauncher, MemoryRuns
from tests.memory_storage import MemoryStorage

PERSON = "x-test-person"
CHOSEN = "test.person"
CARRIED = "x-test-token"
PROTOCOL = "2026-07-28"
PATH = "/mcp"
BASE = "http://127.0.0.1"


def store_of(base: ServerContext, view_url: str) -> ServerContext:
    """One store's context: memory storage, activity, runs, launcher and installs of its own, its
    own bus, locks, watchers and client, the ports of the host's background, and the page it
    serves."""
    return dataclasses.replace(
        base,
        storage=MemoryStorage(),
        activity=MemoryActivity(),
        runs=MemoryRuns(),
        launcher=MemoryLauncher(),
        installs=MemoryInstalls(),
        installer=MemoryInstaller([]),
        events=EventBus(),
        locks={},
        watchers=set(),
        client={},
        view_url=view_url,
    )


class Host:
    """The stores of several signed-in people, and the pumps that follow them while it serves."""

    def __init__(self, stores: Mapping[str, tuple[ServerContext, Person]]) -> None:
        self.stores = dict(stores)

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        """The copy of the person's store that names them."""
        named = None if scope is None else scope.get(CHOSEN)
        if not isinstance(named, str) or named not in self.stores:
            raise Unauthorised("this host serves no such caller")
        store, person = self.stores[named]
        return store.for_person(person)

    @asynccontextmanager
    async def serving(self) -> AsyncIterator[None]:
        """Follow every store the host serves, each once however many people it holds."""
        async with AsyncExitStack() as stack:
            for store in self._distinct():
                await stack.enter_async_context(
                    following(store.storage, store.runs, store.installs, store.events)
                )
            yield

    def _distinct(self) -> list[ServerContext]:
        seen: dict[int, ServerContext] = {}
        for store, _person in self.stores.values():
            seen[id(store)] = store
        return list(seen.values())


@asynccontextmanager
async def served(host: Host) -> AsyncIterator[ASGIApp]:
    """The host's MCP endpoint, following the host's stores while it answers."""
    app = build_server(host).http_app(path=PATH)
    async with app.lifespan(app), host.serving():
        yield signed_in(app)


def signed_in(app: ASGIApp) -> ASGIApp:
    """The app with each request marked by the person its header names and the credential it
    carries, as a host's middleware does."""

    async def marked(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            person = headers.get(PERSON)
            scope[CHOSEN] = person
            scope["user"] = AuthenticatedUser(
                AccessToken(
                    token=headers.get(CARRIED) or "t",
                    client_id="chat",
                    scopes=[],
                    subject=person,
                )
            )
        await app(scope, receive, send)

    return marked


def chat(app: ASGIApp, person: str, name: str = "claude", mode: str = "auto") -> Client:
    """One chat's client, signed in as the person, answering from the app in this process."""
    transport = StreamableHttpTransport(
        f"{BASE}{PATH}",
        headers={PERSON: person},
        httpx_client_factory=_answering(app),
    )
    return Client(transport, client_info=Implementation(name=name, version="1"), mode=mode)


def _answering(app: ASGIApp) -> McpHttpClientFactory:
    """An HTTP client the app answers, so the test bounds each answer itself."""

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        follow_redirects: bool = True,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers=headers,
            timeout=timeout or httpx2.Timeout(30.0),
            auth=auth,
            follow_redirects=follow_redirects,
        )

    return factory


async def posted(
    app: ASGIApp,
    person: str | None,
    method: str,
    params: dict[str, object],
    client: str = "claude",
) -> httpx2.Response:
    """One raw post on 2026-07-28, carrying the person's headers, the client's name in `_meta`,
    and the headers the method's envelope states."""
    headers = {
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: PROTOCOL,
        MCP_METHOD_HEADER: method,
    }
    if person is not None:
        headers[PERSON] = person
    named = NAME_BEARING_METHODS.get(method)
    if named is not None and isinstance(params.get(named), str):
        headers[MCP_NAME_HEADER] = str(params[named])
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            **params,
            "_meta": {
                PROTOCOL_VERSION_META_KEY: PROTOCOL,
                CLIENT_CAPABILITIES_META_KEY: {},
                CLIENT_INFO_META_KEY: {"name": client, "version": "1"},
            },
        },
    }
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE) as http:
        return await asyncio.wait_for(http.post(PATH, headers=headers, json=body), timeout=15)
