"""Each request of the view answers on the context the host binds to the person it names."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import re
import uuid
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from pydantic import SecretStr
from starlette.routing import Route
from starlette.types import ASGIApp

from ecosemantic.errors import Unavailable
from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.model.canonical import content_hash
from ecosemantic.model.entities import Person, ProductSystem, method_id
from ecosemantic.ports.types import Account, CallDraft, MonteCarloConfig, RunDraft
from ecosemantic.view.app import build_view
from tests.callers import BASE, PERSON, Host, signed_in, store_of
from tests.conftest import fixture_system
from tests.fixture_data import GWP
from tests.view.test_installs import OPENLCA, zipped
from tests.view.test_tables import rezipped

NOWHERE = Path("/nonexistent-static")
CATCH_ALL = "/api/{path:path}"
ANA = Person(id="ana", name="Ana")
BEN = Person(id="ben", name="Ben")
ADA = Person(id="ada", name="Ada")
STORED = {"kind": "person", "id": ANA.id, "name": ANA.name}
GWP_ID = method_id(" > ".join(GWP))
ACCOUNT = Account(username="me", password=SecretStr("hunter2"))
CREDENTIAL = {"username": "me", "password": "hunter2"}
PARAMETER = re.compile(r"\{([^{}]+)\}")
FILLED = {
    "int": "1",
    "float": "1.0",
    "path": "x",
    "uuid": "00000000-0000-0000-0000-000000000000",
}


def _filled(path: str) -> str:
    """A route's path with each parameter filled, so a request reaches the handler it names."""

    def placeholder(match: re.Match[str]) -> str:
        _, _, converter = match.group(1).partition(":")
        return FILLED.get(converter or "str", "x")

    return PARAMETER.sub(placeholder, path)


def _walks(view: ASGIApp) -> list[tuple[str, str]]:
    """Each method of each route under /api the catch-all apart, with the path it answers."""
    return [
        (method, _filled(route.path))
        for route in view.routes
        if isinstance(route, Route) and route.path.startswith("/api") and route.path != CATCH_ALL
        for method in sorted(route.methods or {"GET"})
        if method != "HEAD"
    ]


def _client(
    view: ASGIApp, person: str | None = None, *, raising: bool = True
) -> httpx2.AsyncClient:
    """A client of the view, each request signed in as the person it names."""
    headers = {} if person is None else {PERSON: person}
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=signed_in(view), raise_app_exceptions=raising),
        base_url=BASE,
        headers=headers,
    )


async def _stored(store: ServerContext, name: str) -> ProductSystem:
    """The fixture's product system under this store, named for the test that stores it."""
    held = fixture_system().product_system
    assert held is not None
    system = held.model_copy(deep=True, update={"id": uuid.uuid5(held.id, name), "name": name})
    await store.storage.put_product_system(system, store.actor, "created")
    return system


async def _write(store: ServerContext, system_id: uuid.UUID, message: str) -> None:
    """A write on one product system of this store, as another writer makes it."""
    current = await store.storage.get_product_system(system_id)
    current.description = message
    await store.storage.put_product_system(current, store.actor, message)


async def _recorded(store: ServerContext, agent: str, system: uuid.UUID) -> uuid.UUID:
    """The id of one call of that agent over that product system, as the recorder keeps it."""
    call = await store.activity.record(
        CallDraft(
            agent=agent,
            client=agent,
            origin="agent",
            tool="get_product_system",
            effect="read",
            arguments={"product_system_id": str(system)},
            product_system_id=system,
            started_at=datetime.now(UTC),
            duration_ms=1,
            outcome="ok",
        )
    )
    return call.id


async def _run(store: ServerContext, system: ProductSystem) -> uuid.UUID:
    """A run posted on this store's run port, queued and with no worker."""
    posted = await store.runs.post_run(
        RunDraft(
            product_system_id=system.id,
            at_hash=content_hash(system),
            config=MonteCarloConfig(),
        )
    )
    return posted.id


def _events(text: str) -> list[dict[str, object]]:
    """Each event a stream's frames carry, in order."""
    found: list[dict[str, object]] = []
    for block in re.split(r"\r?\n\r?\n", text):
        data = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if data:
            found.append(json.loads(data[0]))
    return found


class Stream:
    """One stream of the view read from a raw ASGI scope, since a transport holds a response
    until it ends."""

    def __init__(self, app: ASGIApp, path: str, person: str) -> None:
        self.app = app
        self.path = path
        self.person = person
        self.frames: list[bytes] = []
        self.status: int | None = None
        self.started = asyncio.Event()
        self.changed = asyncio.Event()
        self.disconnect = asyncio.Event()
        self.task: asyncio.Task[None] | None = None

    @property
    def text(self) -> str:
        return b"".join(self.frames).decode()

    async def __aenter__(self) -> Stream:
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self.path,
            "raw_path": self.path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"host", b"view"), (PERSON.encode(), self.person.encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
        }

        async def receive() -> dict[str, object]:
            await self.disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message: Mapping[str, object]) -> None:
            if message["type"] == "http.response.start":
                assert isinstance(message["status"], int)
                self.status = message["status"]
                self.started.set()
            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                assert isinstance(body, bytes)
                self.frames.append(body)
                self.changed.set()

        self.task = asyncio.create_task(self.app(scope, receive, send))
        await asyncio.wait_for(self.started.wait(), 5)
        if self.status != 200:
            self.disconnect.set()
            await asyncio.gather(self.task, return_exceptions=True)
            raise AssertionError(f"the stream at {self.path} answered {self.status}")
        return self

    async def until(
        self, done: Callable[[list[dict[str, object]]], bool]
    ) -> list[dict[str, object]]:
        """The events read once they satisfy the predicate, or a failure naming the path."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10
        while not done(_events(self.text)):
            left = deadline - loop.time()
            if left <= 0:
                raise TimeoutError(f"the stream at {self.path} carried no such frame")
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), left)
            except TimeoutError:
                continue
        return _events(self.text)

    async def __aexit__(self, *raised: object) -> None:
        self.disconnect.set()
        assert self.task is not None
        await asyncio.wait_for(self.task, 5)


class _Down(Host):
    """A host whose lookup fails, as one whose account store is down."""

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        raise Unavailable("the host's account store is down")


class _Personless(Host):
    """A host that answers its store's own context, naming no person."""

    async def caller(self, scope: Mapping[str, object] | None) -> ServerContext:
        return self.stores["ana"][0]


def _view(callers: Host) -> ASGIApp:
    """The page served over a host of several people."""
    return build_view(callers, build_server(callers), static=NOWHERE)


async def test_every_route_refuses_a_caller_the_host_does_not_know(
    context: ServerContext,
) -> None:
    host = Host({"ana": (store_of(context, f"{BASE}/ana"), ANA)})
    view = _view(host)
    walked = _walks(view)
    async with view.router.lifespan_context(view), _client(view, "mallory") as http:
        for method, path in walked:
            answered = await asyncio.wait_for(http.request(method, path), timeout=10)
            assert answered.status_code == 401, (method, path)
            assert answered.json()["error"] == "unauthorised", (method, path)
    assert len(walked) > 50


async def test_every_route_refuses_a_host_that_forgets_the_person(
    context: ServerContext, tmp_path: Path
) -> None:
    ana = dataclasses.replace(
        store_of(context, f"{BASE}/ana"),
        uploads_dir=tmp_path / "uploads",
    )
    host = _Personless({"ana": (ana, ANA)})
    view = _view(host)
    walked = _walks(view)
    async with view.router.lifespan_context(view):
        async with _client(view, "ana", raising=False) as http:
            for method, path in walked:
                answered = await asyncio.wait_for(http.request(method, path), timeout=10)
                assert answered.status_code == 500, (method, path)
    assert len(walked) > 50
    assert await ana.storage.list_product_systems() == []
    assert await ana.activity.list_calls() == []
    assert not (tmp_path / "uploads").exists()


async def test_the_page_resolves_no_caller(context: ServerContext) -> None:
    host = Host({"ana": (store_of(context, f"{BASE}/ana"), ANA)})
    async with _client(_view(host)) as http:
        answered = await asyncio.wait_for(http.get("/"), timeout=10)
    assert answered.status_code == 200


async def test_a_lookup_that_fails_answers_unavailable(context: ServerContext) -> None:
    store = store_of(context, f"{BASE}/ana")
    down = _Down({"ana": (store, ANA)})
    async with _client(_view(down), "ana") as http:
        refused = await asyncio.wait_for(http.get("/api/home"), timeout=10)
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"] == "unavailable"
    held = Host({"ana": (store, ANA)})
    async with _client(_view(held), "ana") as http:
        answered = await asyncio.wait_for(http.get("/api/home"), timeout=10)
    assert answered.status_code == 200


async def test_each_caller_s_pages_hold_their_store_alone(context: ServerContext) -> None:
    ana = store_of(context, f"{BASE}/ana")
    ben = store_of(context, f"{BASE}/ben")
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    ana_system = await _stored(ana, "ana-system")
    ben_system = await _stored(ben, "ben-system")
    ana_call = await _recorded(ana, "ana-agent", ana_system.id)
    await _recorded(ben, "ben-agent", ben_system.id)
    ana_run = await _run(ana, ana_system)
    ben_run = await _run(ben, ben_system)
    view = _view(host)
    async with _client(view, "ana") as mine, _client(view, "ben") as theirs:
        mine_home = (await mine.get("/api/home")).json()["value"]
        theirs_home = (await theirs.get("/api/home")).json()["value"]
        mine_systems = (await mine.get("/api/product-systems")).json()["value"]
        theirs_systems = (await theirs.get("/api/product-systems")).json()["value"]
        mine_calls = (await mine.get("/api/activity")).json()["value"]
        theirs_calls = (await theirs.get("/api/activity")).json()["value"]
        mine_agents = (await mine.get("/api/agents")).json()["value"]
        theirs_agents = (await theirs.get("/api/agents")).json()["value"]
        mine_runs = (await mine.get(f"/api/product-systems/{ana_system.id}/runs")).json()["value"]
        theirs_runs = (await theirs.get(f"/api/product-systems/{ben_system.id}/runs")).json()[
            "value"
        ]
        stray_runs = (await theirs.get(f"/api/product-systems/{ana_system.id}/runs")).json()[
            "value"
        ]
        missing = await theirs.get(f"/api/product-systems/{ana_system.id}")
        crossed = [
            await theirs.get(f"/api/runs/{ana_run}"),
            await theirs.post(f"/api/runs/{ana_run}/cancel"),
            await theirs.post(f"/api/activity/{ana_call}/rerun"),
        ]
        mine_run = await mine.get(f"/api/runs/{ana_run}")
    assert [row["system"]["id"] for row in mine_home] == [str(ana_system.id)]
    assert [row["system"]["id"] for row in theirs_home] == [str(ben_system.id)]
    assert [card["id"] for card in mine_systems] == [str(ana_system.id)]
    assert [card["id"] for card in theirs_systems] == [str(ben_system.id)]
    assert [call["agent"] for call in mine_calls] == ["ana-agent"]
    assert [call["agent"] for call in theirs_calls] == ["ben-agent"]
    assert [agent["agent"] for agent in mine_agents] == ["ana-agent"]
    assert [agent["agent"] for agent in theirs_agents] == ["ben-agent"]
    assert [run["id"] for run in mine_runs] == [str(ana_run)]
    assert [run["id"] for run in theirs_runs] == [str(ben_run)]
    assert stray_runs == []
    assert missing.status_code == 404
    assert [response.status_code for response in crossed] == [404] * 3
    assert [response.json()["error"] for response in crossed] == ["not_found"] * 3
    assert mine_run.status_code == 200
    assert mine_run.json()["value"]["status"] == "queued"
    assert (await ana.runs.get_run(ana_run)).status == "queued"


async def test_a_stream_receives_nothing_of_another_store(context: ServerContext) -> None:
    ana = store_of(context, f"{BASE}/ana")
    ben = store_of(context, f"{BASE}/ben")
    host = Host({"ana": (ana, ANA), "ben": (ben, BEN)})
    system = await _stored(ana, "shared")
    held = fixture_system().product_system
    assert held is not None
    await ben.storage.put_product_system(
        held.model_copy(deep=True, update={"id": system.id, "name": system.name}),
        ben.actor,
        "created",
    )
    view = _view(host)
    app = signed_in(view)
    on_ana = ana.events.subscribe(system.id)
    async with view.router.lifespan_context(view):
        one = Stream(app, f"/api/product-systems/{system.id}/events", "ben")
        all_of = Stream(app, "/api/events", "ben")
        async with one, all_of:
            await _write(ana, system.id, "written by Ana")
            hers = await asyncio.wait_for(on_ana.get(), timeout=10)
            assert hers.entry is not None and hers.entry.message == "written by Ana"
            await _write(ben, system.id, "written by Ben")
            first = await one.until(lambda seen: len(seen) >= 1)
            everything = await all_of.until(lambda seen: len(seen) >= 1)
    assert [str(event["entry"]["message"]) for event in first] == ["written by Ben"]
    assert [str(event["entry"]["message"]) for event in everything] == ["written by Ben"]


async def test_the_server_route_names_no_client_to_a_person(context: ServerContext) -> None:
    host = Host({"ana": (store_of(context, f"{BASE}/ana"), ANA)})
    async with _client(_view(host), "ana") as http:
        answered = await http.get("/api/server")
    assert answered.status_code == 200
    assert answered.json()["client"] is None


async def test_a_request_and_a_return_name_who_is_signed_in(context: ServerContext) -> None:
    ana = store_of(context, f"{BASE}/ana")
    host = Host({"ana": (ana, ANA)})
    system = await _stored(ana, "requests")
    base = f"/api/product-systems/{system.id}"
    async with _client(_view(host), "ana") as http:
        current = (await http.get(base)).json()["value"]["hash"]
        posted = await http.post(
            f"{base}/requests",
            json={
                "actor": "Mallory",
                "kind": "return",
                "at_hash": current,
                "message": "too heavy",
            },
        )
        downloaded = await http.get(f"{base}/tables.zip")
        grown = zipfile.ZipFile(io.BytesIO(downloaded.content)).read("inputs/input_parameters.csv")
        returned = await http.post(
            f"{base}/tables",
            files={
                "tables": (
                    "tables.zip",
                    rezipped(
                        downloaded.content,
                        "inputs/input_parameters.csv",
                        grown + b"signed_in_marker,0.8,,\n",
                    ),
                    "application/zip",
                )
            },
            data={"actor": "Mallory"},
        )
    assert posted.status_code == 201, posted.text
    assert posted.json()["actor"] == STORED
    assert returned.status_code == 201, returned.text
    assert returned.json()["actor"] == STORED


async def test_a_person_s_upload_and_accounts_are_refused(
    context: ServerContext, tmp_path: Path
) -> None:
    store = dataclasses.replace(
        store_of(context, f"{BASE}/ana"),
        uploads_dir=tmp_path / "uploads",
        credentials={"ecoinvent": ACCOUNT},
    )
    host = Host({"ana": (store, ANA)})
    async with _client(_view(host), "ana") as http:
        answered = [
            await http.get("/api/credentials"),
            await http.put("/api/credentials/ecoinvent", json=CREDENTIAL),
            await http.delete("/api/credentials/ecoinvent"),
            await http.post(
                "/api/installs/openlca",
                files={"file": ("database.zip", zipped(), "application/zip")},
                data=OPENLCA,
            ),
        ]
    assert [response.status_code for response in answered] == [501] * 4
    assert [response.json()["error"] for response in answered] == ["not_supported"] * 4
    assert store.credentials == {"ecoinvent": ACCOUNT}
    assert not (tmp_path / "uploads").exists()
    async with _client(build_view(store, build_server(store), static=NOWHERE)) as http:
        held = await http.get("/api/credentials")
    assert held.status_code == 200
    assert held.json()["held"] == ["ecoinvent"]


async def test_a_rerun_runs_as_the_person_who_asks(context: ServerContext, tmp_path: Path) -> None:
    store = dataclasses.replace(
        store_of(context, f"{BASE}/ana"),
        uploads_dir=tmp_path / "uploads",
    )
    host = Host({"ana": (store, ANA), "ada": (store, ADA)})
    system = await _stored(store, "rerun")
    base = f"/api/product-systems/{system.id}"
    view = _view(host)
    async with _client(view, "ana") as mine, _client(view, "ada") as hers:
        scored = await mine.post(f"{base}/impact?started=true", json={"method_id": GWP_ID})
        assert scored.status_code == 200, scored.text
        recorded = await store.activity.list_calls()
        calculation = next(
            call for call in recorded if call.tool == "calculate_impact" and call.person == ANA
        )
        again = await hers.post(f"/api/activity/{calculation.id}/rerun")
        by_ada = [
            call
            for call in await store.activity.list_calls()
            if call.tool == "calculate_impact" and call.id != calculation.id
        ]
        named = tmp_path / "exported"
        exported = await store.activity.record(
            CallDraft(
                agent="view",
                client="view",
                origin="view",
                person=ANA,
                tool="export_tables",
                effect="read",
                arguments={"product_system_id": str(system.id), "path": str(named)},
                product_system_id=system.id,
                started_at=datetime.now(UTC),
                duration_ms=1,
                outcome="ok",
            )
        )
        refused = await hers.post(f"/api/activity/{exported.id}/rerun")
    assert again.status_code == 200, again.text
    assert [call.person for call in by_ada] == [ADA]
    assert refused.status_code == 501, refused.text
    assert refused.json()["error"] == "not_supported"
    assert not named.exists()
