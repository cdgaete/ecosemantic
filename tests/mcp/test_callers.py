"""Each call reaches the store of the person it belongs to, and the store of no other person."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import uuid
from collections.abc import Mapping
from pathlib import Path

import httpx2
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST
from starlette.types import ASGIApp, Receive, Scope, Send

from ecosemantic.errors import Unavailable
from ecosemantic.events import Event
from ecosemantic.local import build_context
from ecosemantic.mcp import discovery
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.envelopes import bound, envelope_of
from ecosemantic.mcp.server import ROSTER, build_server
from ecosemantic.model.entities import Actor, Person, ProductSystem, method_id
from ecosemantic.ports.types import ProductSystemSummary, RequestDraft, RunPatch, trail
from ecosemantic.view.app import build_view
from tests.callers import (
    BASE,
    PATH,
    PERSON,
    Host,
    chat,
    posted,
    served,
    signed_in,
    store_of,
)
from tests.conftest import fixture_system
from tests.fixture_data import FIXTURE_DB, GWP
from tests.memory_storage import MemoryStorage

ANA = Person(id="ana", name="Ana")
BEN = Person(id="ben", name="Ben")
ADA = Person(id="ada", name="Ada")
GWP_ID = method_id(" > ".join(GWP))
CLAUDE = {"kind": "agent", "id": "claude", "name": "claude"}
LEGACY = "2025-06-18"
OPENING: dict[str, object] = {
    "protocolVersion": LEGACY,
    "capabilities": {},
    "clientInfo": {"name": "claude", "version": "1"},
}
DISCOVERY: dict[str, object] = {}
HANDSHAKES: tuple[tuple[str, dict[str, object]], ...] = (
    ("initialize", OPENING),
    ("server/discover", DISCOVERY),
)


def stores(context: ServerContext) -> tuple[ServerContext, ServerContext]:
    """Ana's store and Ben's, each with a page and ports of its own."""
    return (
        store_of(context, f"{BASE}/ana"),
        store_of(context, f"{BASE}/ben"),
    )


def one(context: ServerContext) -> Host:
    """Ana alone, on a store of her own."""
    return Host({"ana": (store_of(context, f"{BASE}/ana"), ANA)})


def kind_of(caught: pytest.ExceptionInfo[ToolError]) -> str:
    """The kind of typed error a client read from a refused call."""
    return envelope_of(caught.value).error


def answered(response: httpx2.Response) -> dict[str, object]:
    """The one JSON-RPC payload a raw post carried, from the body or the event stream."""
    body = next(
        (
            line.removeprefix("data: ")
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ),
        response.text,
    )
    return json.loads(body)


def value_of(response: httpx2.Response) -> list[dict[str, object]]:
    """What a raw post's listing answered, from the body or from the event stream."""
    return list(answered(response)["result"]["structuredContent"]["value"])


def refusal_of(response: httpx2.Response) -> str:
    """The kind of typed error a raw post's tool answered with."""
    return envelope_of(ToolError(str(answered(response)["result"]["content"][0]["text"]))).error


def rpc_code(response: httpx2.Response) -> int:
    """The JSON-RPC code a raw post answered with."""
    return code_of(answered(response))


def code_of(payload: dict[str, object]) -> int:
    """The JSON-RPC code an answer carried in place of a result."""
    error = payload["error"]
    assert isinstance(error, dict)
    return int(error["code"])


def ids_of(value: list[dict[str, object]]) -> list[str]:
    """The ids of the product systems a listing answered."""
    return [str(card["id"]) for card in value]


def seqs_of(events: list[Event]) -> set[int]:
    """The sequence numbers of the log entries the events carried."""
    return {event.entry.seq for event in events if event.entry is not None}


async def made(client: Client, name: str) -> str:
    """The id of a product system the client created."""
    created = await client.call_tool(
        "create_product_system", {"name": name, "database": FIXTURE_DB}
    )
    return str(created.structured_content["value"]["id"])


async def added(client: Client, system_id: str, code: str) -> dict[str, object]:
    """A process of that code, and the entry the write appended."""
    written = await client.call_tool(
        "create_process",
        {
            "product_system_id": system_id,
            "code": code,
            "name": code,
            "unit": "unit",
            "reference_product": code,
        },
    )
    return written.structured_content["entry"]


class Slow(MemoryStorage):
    """A store whose reads take a while, so a call in flight overlaps the one after it."""

    def __init__(self, answer: float) -> None:
        super().__init__()
        self.answer = answer

    async def list_product_systems(self) -> list[ProductSystemSummary]:
        await asyncio.sleep(self.answer)
        return await super().list_product_systems()

    async def get_product_system(self, product_system_id: uuid.UUID) -> ProductSystem:
        await asyncio.sleep(self.answer)
        return await super().get_product_system(product_system_id)


class Started:
    """A launcher whose worker is another process: it answers a pid and reports that worker
    alive."""

    def start(self, run_id: uuid.UUID) -> int:
        return 4242

    def alive(self, run_id: uuid.UUID) -> bool:
        return True


class _Personless(Host):
    """A host that answers its store's own context, naming no person."""

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        return self.stores["ana"][0]


class _Down(Host):
    """A host whose lookup fails, as one whose account store is down."""

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        raise Unavailable("the host's account store is down")


def _uncredentialed(app: ASGIApp) -> ASGIApp:
    """The app with the request's credential dropped, as a host that authenticates nothing
    serves it."""

    async def bare(scope: Scope, receive: Receive, send: Send) -> None:
        scope.pop("user", None)
        await app(scope, receive, send)

    return bare


def _as_ben(app: ASGIApp) -> ASGIApp:
    """The app with the request's credential naming another person."""

    async def other(scope: Scope, receive: Receive, send: Send) -> None:
        scope["user"] = AuthenticatedUser(
            AccessToken(token="t", client_id="chat", scopes=[], subject=BEN.id)
        )
        await app(scope, receive, send)

    return other


async def _legacy(
    app: ASGIApp,
    person: str | None,
    method: str,
    params: dict[str, object],
    session: str | None = None,
    rpc_id: int = 1,
    token: str | None = None,
) -> httpx2.Response:
    """One raw post on 2025-06-18, the protocol a session speaks."""
    headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    if person is not None:
        headers[PERSON] = person
    if token is not None:
        headers["x-test-token"] = token
    if session is not None:
        headers["mcp-session-id"] = session
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=BASE) as http:
        return await asyncio.wait_for(http.post(PATH, headers=headers, json=body), timeout=15)


async def _asked(
    app: ASGIApp, person: str | None, method: str, params: dict[str, object]
) -> dict[str, object]:
    """One method posted on the protocol that carries it, as the client that speaks it would."""
    if method == "initialize":
        return answered(await _legacy(app, person, method, params))
    return answered(await posted(app, person, method, params))


async def _session(app: ASGIApp, person: str) -> str:
    """The id of a session the person opened on 2025-06-18."""
    response = await _legacy(app, person, "initialize", OPENING)
    session = response.headers["mcp-session-id"]
    assert session
    return session


async def _of_kind(queue: asyncio.Queue[Event], kind: str, count: int = 1) -> list[Event]:
    """The first `count` events of that kind a queue receives."""
    seen: list[Event] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10
    while len(seen) < count:
        left = max(deadline - loop.time(), 0.01)
        event = await asyncio.wait_for(queue.get(), timeout=left)
        if event.kind == kind:
            seen.append(event)
    return seen


async def _until_status(queue: asyncio.Queue[Event], status: str) -> list[Event]:
    """Every run event a queue receives, up to and including one of that status."""
    seen: list[Event] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 15
    while True:
        left = max(deadline - loop.time(), 0.01)
        event = await asyncio.wait_for(queue.get(), timeout=left)
        if event.kind == "run" and event.run is not None:
            seen.append(event)
            if event.run.status == status:
                return seen


async def _carried(post: asyncio.Task[httpx2.Response]) -> str:
    """What one post answered, or nothing at all when it never answered."""
    try:
        return (await asyncio.wait_for(post, timeout=5)).text
    except TimeoutError:
        return ""


async def test_neither_caller_reaches_the_other_s_system(context: ServerContext) -> None:
    ana, ben = stores(context)
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    async with served(host) as app:
        async with chat(app, "ana") as mine, chat(app, "ben") as theirs:
            ana_id = await made(mine, "ana")
            ben_id = await made(theirs, "ben")
            by_ana = (await mine.call_tool("list_product_systems", {})).structured_content
            by_ben = (await theirs.call_tool("list_product_systems", {})).structured_content
            assert ids_of(by_ana["value"]) == [ana_id]
            assert ids_of(by_ben["value"]) == [ben_id]
            refused = (
                ("get_product_system", {"product_system_id": ben_id}),
                ("update_product_system", {"product_system_id": ben_id, "name": "mine now"}),
                (
                    "create_process",
                    {
                        "product_system_id": ben_id,
                        "code": "theirs",
                        "name": "theirs",
                        "unit": "unit",
                        "reference_product": "theirs",
                    },
                ),
                ("delete_product_system", {"product_system_id": ben_id}),
            )
            for tool, arguments in refused:
                with pytest.raises(ToolError) as caught:
                    await mine.call_tool(tool, arguments)
                assert kind_of(caught) == "not_found", tool
    assert len(await ben.storage.log(uuid.UUID(ben_id))) == 1


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_a_write_names_the_person_and_the_agent(context: ServerContext, mode: str) -> None:
    host = one(context)
    store = host.stores["ana"][0]
    async with served(host) as app, chat(app, "ana", mode=mode) as client:
        system_id = await made(client, "ana")
        entry = await added(client, system_id, "widget")
        request = await store.storage.post_request(
            uuid.UUID(system_id),
            RequestDraft(
                actor=Actor(kind="person", id=ANA.id, name=ANA.name),
                kind="return",
                at_hash="0",
                message="please check the transport",
            ),
        )
        answered = await client.call_tool(
            "resolve_request",
            {
                "product_system_id": system_id,
                "request_id": str(request.id),
                "resolution": "accepted",
                "message": "checked",
            },
        )
    on_behalf_of = {"id": ANA.id, "name": ANA.name}
    assert entry["actor"] == {**CLAUDE, "on_behalf_of": on_behalf_of}
    assert answered.structured_content["value"]["outcome"]["actor"] == {
        **CLAUDE,
        "on_behalf_of": on_behalf_of,
    }


async def test_a_session_answers_only_who_opened_it(context: ServerContext) -> None:
    ana = dataclasses.replace(store_of(context, f"{BASE}/ana"), storage=Slow(0.3))
    ben = store_of(context, f"{BASE}/ben")
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    listing = {"name": "list_product_systems", "arguments": {}}
    async with served(host) as app:
        async with chat(app, "ana") as mine:
            ana_id = await made(mine, "ana")
        session = await _session(app, "ana")
        in_flight = asyncio.create_task(
            _legacy(app, "ana", "tools/call", listing, session=session, rpc_id=11)
        )
        await asyncio.sleep(0.05)
        theirs = await _legacy(app, "ben", "tools/call", listing, session=session, rpc_id=11)
        assert theirs.status_code == 404
        answered = await in_flight
    assert ids_of(value_of(answered)) == [ana_id]


async def test_each_call_without_a_session_answers_its_own_person(
    context: ServerContext,
) -> None:
    ana, ben = stores(context)
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    listing = {"name": "list_product_systems", "arguments": {}}
    async with served(host) as app:
        async with chat(app, "ana") as mine, chat(app, "ben") as theirs:
            ana_id = await made(mine, "ana")
            ben_id = await made(theirs, "ben")
        by_ana, by_ben = await asyncio.gather(
            posted(app, "ana", "tools/call", listing),
            posted(app, "ben", "tools/call", listing),
        )
    assert ids_of(value_of(by_ana)) == [ana_id]
    assert ids_of(value_of(by_ben)) == [ben_id]


async def test_a_refreshed_token_keeps_its_session(context: ServerContext) -> None:
    host = one(context)
    listing = {"name": "list_product_systems", "arguments": {}}
    async with served(host) as app:
        async with chat(app, "ana") as mine:
            ana_id = await made(mine, "ana")
        session = await _session(app, "ana")
        refreshed = await _legacy(
            app, "ana", "tools/call", listing, session=session, rpc_id=12, token="renewed"
        )
    assert refreshed.status_code == 200
    assert ids_of(value_of(refreshed)) == [ana_id]


async def test_a_session_without_a_credential_carries_nothing_to_another(
    context: ServerContext,
) -> None:
    ana = store_of(context, f"{BASE}/ana")
    ben = store_of(context, f"{BASE}/ben")
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    held = fixture_system().product_system
    assert held is not None
    mine = held.model_copy(update={"name": "ana-only-widget"})
    await ana.storage.put_product_system(mine, ana.actor, "created")
    listing = {"name": "list_product_systems", "arguments": {}}
    raw = build_server(host).http_app(path=PATH)
    async with raw.lifespan(raw):
        app = signed_in(_uncredentialed(raw))
        opening = await _legacy(app, "ana", "initialize", OPENING)
        assert code_of(answered(opening)) == INVALID_REQUEST
        session = opening.headers["mcp-session-id"]
        assert session
        hers = asyncio.create_task(
            _legacy(app, "ana", "tools/call", listing, session=session, rpc_id=11)
        )
        his = asyncio.create_task(
            _legacy(app, "ben", "tools/call", listing, session=session, rpc_id=11)
        )
        carried = [await _carried(post) for post in (hers, his)]
    assert not [body for body in carried if str(mine.id) in body or mine.name in body]


async def test_a_broken_handshake_is_refused_as_invalid_params(
    context: ServerContext,
) -> None:
    host = one(context)
    broken = {**OPENING, "clientInfo": 5}
    async with served(host) as app:
        refused = await _asked(app, "ana", "initialize", broken)
    assert code_of(refused) == INVALID_PARAMS


async def test_a_person_without_a_credential_is_refused(context: ServerContext) -> None:
    ana = store_of(context, f"{BASE}/ana")
    host = Host({"ana": (ana, ANA)})
    listing = {"name": "list_product_systems", "arguments": {}}
    raw = build_server(host).http_app(path=PATH)
    async with raw.lifespan(raw), host.serving():
        for mark in (_uncredentialed, _as_ben):
            marked = signed_in(mark(raw))
            unheld = await posted(marked, "ana", "tools/call", listing)
            assert refusal_of(unheld) == "unauthorised"
            for method, params in HANDSHAKES:
                refused = await _asked(marked, "ana", method, params)
                assert code_of(refused) == INVALID_REQUEST, method
        for method, params in HANDSHAKES:
            held = await _asked(signed_in(raw), "ana", method, params)
            assert "error" not in held and "result" in held, method
    assert await ana.storage.list_product_systems() == []


@pytest.mark.parametrize(
    ("method", "params"),
    [("tools/call", {"name": name, "arguments": {}}) for name in ROSTER] + list(HANDSHAKES),
)
async def test_every_tool_refuses_a_caller_the_host_does_not_know(
    context: ServerContext, method: str, params: dict[str, object]
) -> None:
    host = one(context)
    async with served(host) as app:
        refused = await _asked(app, "mallory", method, params)
        if method != "tools/call":
            held = await _asked(app, "ana", method, params)
    if method == "tools/call":
        body = str(refused["result"]["content"][0]["text"])
        assert envelope_of(ToolError(body)).error == "unauthorised"
    else:
        assert code_of(refused) == INVALID_REQUEST
        assert "error" not in held and "result" in held


@pytest.mark.parametrize(
    ("method", "params"),
    [("tools/call", {"name": name, "arguments": {}}) for name in ROSTER] + list(HANDSHAKES),
)
async def test_a_host_s_context_without_a_person_is_refused(
    context: ServerContext, method: str, params: dict[str, object]
) -> None:
    ana = store_of(context, f"{BASE}/ana")
    host = _Personless({"ana": (ana, ANA)})
    async with served(host) as app:
        refused = await _asked(app, "ana", method, params)
    if method == "tools/call":
        assert code_of(refused) == INTERNAL_ERROR
    else:
        assert "error" in refused
    assert "result" not in refused
    assert await ana.storage.list_product_systems() == []


async def test_a_lookup_that_fails_answers_unavailable(context: ServerContext) -> None:
    host = _Down({"ana": (store_of(context, f"{BASE}/ana"), ANA)})
    async with served(host) as app:
        refused = await posted(
            app, "ana", "tools/call", {"name": "list_product_systems", "arguments": {}}
        )
    assert refusal_of(refused) == "unavailable"


async def test_two_people_on_one_store_write_at_once(context: ServerContext) -> None:
    store = dataclasses.replace(store_of(context, f"{BASE}/ana"), storage=Slow(0.03))
    host = Host({"ana": (store, ANA), "ada": (store, ADA)})
    async with served(host) as app:
        async with chat(app, "ana") as mine:
            system_id = await made(mine, "shared")
        system = uuid.UUID(system_id)
        seen_by_ana = store.for_person(ANA).events.subscribe(system)
        seen_by_ada = store.for_person(ADA).events.subscribe(system)
        async with chat(app, "ana") as mine, chat(app, "ada") as hers:
            first, second = await asyncio.gather(
                added(mine, system_id, "one"),
                added(hers, system_id, "two"),
            )
        by_ana = await _of_kind(seen_by_ana, "entry", 2)
        by_ada = await _of_kind(seen_by_ada, "entry", 2)
    stored = await store.storage.get_product_system(system)
    assert sorted(process.code for process in stored.processes) == ["one", "two"]
    written = {first["seq"], second["seq"]}
    assert seqs_of(by_ana) == written
    assert seqs_of(by_ada) == written


async def test_a_person_s_copy_shows_no_other_client(context: ServerContext) -> None:
    ana, ben = stores(context)
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    async with served(host) as app:
        async with chat(app, "ana", name="alpha"), chat(app, "ben", name="beta"):
            pass
    assert ana.client == {}
    assert ben.client == {}
    assert ana.for_person(ANA).client == {}
    assert ben.for_person(BEN).client == {}


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_each_caller_reads_their_own_link(context: ServerContext, mode: str) -> None:
    ana, ben = stores(context)
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    async with served(host) as app:
        async with chat(app, "ana", mode=mode) as mine, chat(app, "ben", mode=mode) as theirs:
            ana_reads = mine.instructions or ""
            ben_reads = theirs.instructions or ""
            ana_link = (await mine.call_tool("view_link", {})).structured_content["value"]
            ben_link = (await theirs.call_tool("view_link", {})).structured_content["value"]
    assert (ana_link, ben_link) == (f"{BASE}/ana", f"{BASE}/ben")
    assert ana_link in ana_reads and ben_link not in ana_reads
    assert ben_link in ben_reads and ana_link not in ben_reads


async def test_a_caller_s_database_list_is_the_one_bound(
    context: ServerContext, tmp_path: Path
) -> None:
    ana = store_of(context, f"{BASE}/ana")
    data = tmp_path / "data"
    systems = tmp_path / "systems"
    data.mkdir()
    systems.mkdir()
    empty = build_context(data, systems)
    try:
        ben = store_of(empty, f"{BASE}/ben")
        host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
        async with served(host) as app:
            async with chat(app, "ana") as mine, chat(app, "ben") as theirs:
                unheld = (await theirs.call_tool("list_databases", {})).structured_content
                with pytest.raises(ToolError) as caught:
                    await theirs.call_tool(
                        "search_processes", {"database": FIXTURE_DB, "query": "steel"}
                    )
                held = (await mine.call_tool("list_databases", {})).structured_content
                found = await mine.call_tool(
                    "search_processes", {"database": FIXTURE_DB, "query": "steel"}
                )
        assert unheld["value"] == []
        assert kind_of(caught) == "not_found"
        assert FIXTURE_DB in [database["name"] for database in held["value"]]
        assert found.structured_content["items"]
    finally:
        empty.close()


async def test_two_people_s_agents_keep_their_trails(context: ServerContext) -> None:
    store = store_of(context, f"{BASE}/ana")
    host = Host({"ana": (store, ANA), "ada": (store, ADA)})
    async with served(host) as app:
        async with chat(app, "ana") as mine:
            system_id = await made(mine, "shared")
            await mine.call_tool("get_product_system", {"product_system_id": system_id})
            by_ana = await added(mine, system_id, "ana")
        async with chat(app, "ada") as theirs:
            await theirs.call_tool("get_product_system", {"product_system_id": system_id})
            by_ada = await added(theirs, system_id, "ada")
    calls = await store.activity.list_calls()
    system = uuid.UUID(system_id)
    ana_trail = trail(calls, system, int(by_ana["seq"]))
    ada_trail = trail(calls, system, int(by_ada["seq"]))
    assert [call.tool for call in ana_trail] == ["get_product_system", "create_process"]
    assert [call.tool for call in ada_trail] == ["get_product_system", "create_process"]
    assert {call.person for call in ana_trail} == {ANA}
    assert {call.person for call in ada_trail} == {ADA}
    assert {call.id for call in ana_trail}.isdisjoint({call.id for call in ada_trail})


async def test_a_tool_that_reaches_the_host_is_refused_over_mcp(
    context: ServerContext, tmp_path: Path
) -> None:
    host = one(context)
    async with served(host) as app:
        async with chat(app, "ana") as mine:
            system_id = await made(mine, "ana")
        named = tmp_path / "named"
        reaching = (
            (
                "export_product_system",
                {"product_system_id": system_id, "path": str(named / "x.zip"), "replace": True},
            ),
            ("import_product_system", {"path": str(named / "x.zip")}),
            ("export_tables", {"product_system_id": system_id, "path": str(named)}),
            ("import_tables", {"path": str(named)}),
            ("install_database", {"source": "uslci", "version": "2024"}),
            ("cancel_install", {"install_id": str(uuid.uuid4())}),
        )
        for tool, arguments in reaching:
            answered = await posted(
                app, "ana", "tools/call", {"name": tool, "arguments": arguments}
            )
            assert refusal_of(answered) == "not_supported", tool
    assert list(tmp_path.iterdir()) == []


async def test_a_run_s_events_reach_its_own_store_alone(context: ServerContext) -> None:
    ana = dataclasses.replace(store_of(context, f"{BASE}/ana"), launcher=Started())
    ben = store_of(context, f"{BASE}/ben")
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    raw = build_server(host).http_app(path=PATH)
    async with raw.lifespan(raw):
        app = signed_in(raw)
        async with chat(app, "ana") as mine:
            system_id = await made(mine, "ana")
            await added(mine, system_id, "widget")
            await mine.call_tool(
                "update_product_system",
                {"product_system_id": system_id, "reference_process": "widget"},
            )
            system = uuid.UUID(system_id)
            seen_by_ana = ana.events.subscribe(system)
            seen_by_ben = ben.events.subscribe(system)
            started = await mine.call_tool(
                "start_monte_carlo",
                {
                    "product_system_id": system_id,
                    "method_id": GWP_ID,
                    "monte_carlo": {"n": 2, "n_min": 1, "seed": 1},
                },
            )
        run = uuid.UUID(started.structured_content["value"]["id"])
        await ana.runs.update_run(run, RunPatch(status="done"))
        moved = await _until_status(seen_by_ana, "done")
    left = list(ana.watchers)
    for task in left:
        task.cancel()
    await asyncio.gather(*left, return_exceptions=True)
    assert [event.run.status for event in moved if event.run is not None][-1] == "done"
    assert seen_by_ben.empty()


async def test_a_hash_reads_no_other_store_s_version(bundle_dir: Path, tmp_path: Path) -> None:
    built: list[ServerContext] = []
    for named in ("ana", "ben"):
        (tmp_path / named).mkdir()
        built.append(build_context(bundle_dir, tmp_path / named, environ={}))
    ana, ben = built
    held = fixture_system().product_system
    assert held is not None
    mine = held.model_copy(deep=True, update={"id": uuid.uuid4(), "name": "mine"})
    await ana.storage.put_product_system(mine, ana.actor, "created")
    entry = await ben.storage.put_product_system(held, ben.actor, "created")
    elsewhere = f"../../../../ben/{held.id}/ecosemantic/versions/{entry.result_hash}"
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    try:
        async with served(host) as app:
            read = await posted(
                app,
                "ana",
                "tools/call",
                {
                    "name": "get_parameters",
                    "arguments": {"product_system_id": str(mine.id), "content_hash": elsewhere},
                },
            )
        assert read.json()["result"].get("isError"), "Ana read Ben's version"
        assert refusal_of(read) == "not_found"
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=signed_in(build_view(host, build_server(host)))),
            base_url=BASE,
        ) as page:
            answered_page = await asyncio.wait_for(
                page.get(
                    f"/api/product-systems/{mine.id}/parameters",
                    params={"hash": elsewhere},
                    headers={PERSON: "ana"},
                ),
                timeout=15,
            )
        assert answered_page.status_code == 404
        assert answered_page.json()["error"] == "not_found"
    finally:
        for context in built:
            context.close()


async def test_a_tool_outside_a_call_raises() -> None:
    with pytest.raises(RuntimeError):
        await bound(discovery.list_databases)()
