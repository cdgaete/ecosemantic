"""The credential routes refuse every reach but this computer, saying why, and the entry route
answers every reach."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from ecosemantic.mcp.accounts import account_advice
from ecosemantic.mcp.context import AccountStart, ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.view.api import BRIDGE_EXTENSION, GATE_PARAMETER
from ecosemantic.view.app import build_view

NOWHERE = Path("/nonexistent-static")
LOOPBACK = ("127.0.0.1", 50000)
IPV6_LOOPBACK = ("::1", 50000)
ELSEWHERE = ("192.168.1.20", 50000)
SCREEN = "http://127.0.0.1:12266/accounts"
BRIDGE_PAGE = "https://carlosgaete.bridge.ecosemantic.com"
PROOF = "a proof"
ACCOUNT = {"username": "me", "password": "hunter2"}


def relayed(method: str, path: str, body: bytes) -> dict[str, Any]:
    """A scope built as the bridge builds one for a request it relays: an https request whose
    client is the bridge and whose extension carries the proof."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("latin-1"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")] if body else [],
        "client": ("bridge", 0),
        "server": ("bridge.ecosemantic.com", 443),
        "extensions": {BRIDGE_EXTENSION: {"proof": PROOF}},
    }


async def answered(app: Any, method: str, path: str, body: bytes = b"") -> tuple[int, str]:
    """The status and the body an application answers a bridged request."""
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(relayed(method, path, body), receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    text = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, text.decode()


def bridged_view(context: ServerContext, entry: AccountStart) -> tuple[Any, ServerContext]:
    """The view as a bridged engine serves it, over a context holding no credential."""
    over = dataclasses.replace(context, credentials={}, client={}, accounts=entry)
    return build_view(
        over, build_server(over), static=NOWHERE, bridged=lambda proof, path: True
    ), over


@pytest.fixture
def page(context: ServerContext) -> Iterator[tuple[TestClient, ServerContext]]:
    """The view answering a peer on this machine, over a context holding no credential."""
    over = dataclasses.replace(context, credentials={}, client={})
    with TestClient(
        build_view(over, build_server(over), static=NOWHERE), client=LOOPBACK
    ) as client:
        yield client, over


def test_a_credential_put_from_loopback_is_held_and_never_answered(
    page: tuple[TestClient, ServerContext],
) -> None:
    client, over = page
    put = client.put("/api/credentials/ecoinvent", json=ACCOUNT)
    assert put.status_code == 204 and put.content == b""
    held = over.credentials["ecoinvent"]
    assert held.username == "me" and held.password.get_secret_value() == "hunter2"
    assert held.token is None
    answered = client.get("/api/credentials")
    assert answered.json() == {"held": ["ecoinvent"]}
    assert "hunter2" not in answered.text and "hunter2" not in put.text


def test_the_credential_routes_refuse_a_peer_that_is_not_loopback(
    context: ServerContext,
) -> None:
    entry = AccountStart(start="tray", screen=SCREEN)
    advice = account_advice(entry, "network")
    over = dataclasses.replace(context, credentials={}, client={}, accounts=entry)
    app = build_view(over, build_server(over), static=NOWHERE)
    with TestClient(app, client=ELSEWHERE) as outside:
        answered_off = [
            outside.put("/api/credentials/ecoinvent", json=ACCOUNT),
            outside.get("/api/credentials"),
            outside.delete("/api/credentials/ecoinvent"),
        ]
    assert [(response.status_code, response.json()["error"]) for response in answered_off] == [
        (401, "unauthorised")
    ] * 3
    assert [response.json()["message"] for response in answered_off] == [advice.why] * 3
    assert [response.json()["details"]["hint"] for response in answered_off] == [advice.steps] * 3
    assert over.credentials == {}


async def test_a_bridged_request_to_every_credential_route_is_refused(
    context: ServerContext,
) -> None:
    entry = AccountStart(start="tray", screen=SCREEN)
    app, over = bridged_view(context, entry)
    asked = [
        ("GET", "/api/credentials", b""),
        ("PUT", "/api/credentials/ecoinvent", json.dumps(ACCOUNT).encode()),
        ("DELETE", "/api/credentials/ecoinvent", b""),
    ]
    answers = [await answered(app, method, path, body) for method, path, body in asked]
    assert [status for status, _ in answers] == [401] * 3
    arrival = account_advice(entry, "bridge").why
    assert arrival.startswith("This page reaches EcoSemantic through the bridge.")
    assert [json.loads(text)["message"] for _, text in answers] == [arrival] * 3
    assert [json.loads(text)["details"]["hint"] for _, text in answers] == [
        account_advice(entry, "bridge").steps
    ] * 3
    assert over.credentials == {}


async def test_the_entry_route_answers_every_reach(context: ServerContext) -> None:
    entry = AccountStart(start="tray", screen=SCREEN)
    over = dataclasses.replace(context, credentials={}, client={}, accounts=entry)
    app = build_view(over, build_server(over), static=NOWHERE)
    with TestClient(app, client=LOOPBACK) as inside:
        here = inside.get("/api/credentials/entry")
    assert here.status_code == 200
    assert here.json() == {
        "reach": "here",
        "here": True,
        "why": None,
        "steps": None,
        "page": None,
    }
    with TestClient(app, client=ELSEWHERE) as outside:
        away = outside.get("/api/credentials/entry")
    network = account_advice(entry, "network")
    assert away.json() == {
        "reach": "network",
        "here": False,
        "why": network.why,
        "steps": network.steps,
        "page": None,
    }
    paged = dataclasses.replace(entry, page=BRIDGE_PAGE)
    bridged_app, _ = bridged_view(context, paged)
    status, text = await answered(bridged_app, "GET", "/api/credentials/entry")
    across = account_advice(paged, "bridge")
    assert status == 200
    assert json.loads(text) == {
        "reach": "bridge",
        "here": False,
        "why": across.why,
        "steps": across.steps,
        "page": BRIDGE_PAGE,
    }


def test_ipv6_loopback_reads_here(context: ServerContext) -> None:
    over = dataclasses.replace(context, credentials={}, client={})
    with TestClient(
        build_view(over, build_server(over), static=NOWHERE), client=IPV6_LOOPBACK
    ) as inside:
        assert inside.put("/api/credentials/ecoinvent", json=ACCOUNT).status_code == 204
        entry = inside.get("/api/credentials/entry")
    assert entry.status_code == 200 and entry.json()["reach"] == "here"
    assert entry.json()["here"] is True
    assert sorted(over.credentials) == ["ecoinvent"]


def test_the_entry_route_never_answers_the_token(context: ServerContext) -> None:
    entry = AccountStart(start="tray", screen=SCREEN, page=BRIDGE_PAGE)
    over = dataclasses.replace(context, credentials={}, client={}, accounts=entry)
    app = build_view(over, build_server(over), static=NOWHERE, token="t0k3n")
    with TestClient(app, client=ELSEWHERE) as outside:
        answer = outside.get("/api/credentials/entry", params={GATE_PARAMETER: "t0k3n"})
    network = account_advice(entry, "network")
    assert answer.status_code == 200
    assert answer.json() == {
        "reach": "network",
        "here": False,
        "why": network.why,
        "steps": network.steps,
        "page": BRIDGE_PAGE,
    }
    assert "t0k3n" not in answer.text


def test_delete_clears_a_held_kind(page: tuple[TestClient, ServerContext]) -> None:
    client, over = page
    with_token = {**ACCOUNT, "token": "123456"}
    assert client.put("/api/credentials/nexus", json=with_token).status_code == 204
    assert over.credentials["nexus"].token is not None
    assert client.get("/api/credentials").json() == {"held": ["nexus"]}
    assert client.delete("/api/credentials/nexus").status_code == 204
    assert client.delete("/api/credentials/nexus").status_code == 204
    assert over.credentials == {} and client.get("/api/credentials").json() == {"held": []}


def test_an_unknown_kind_and_a_credential_without_its_password_are_invalid(
    page: tuple[TestClient, ServerContext],
) -> None:
    client, over = page
    refused = [
        client.put("/api/credentials/database", json=ACCOUNT),
        client.delete("/api/credentials/database"),
        client.put("/api/credentials/ecoinvent", json={"username": "me"}),
    ]
    assert [(response.status_code, response.json()["error"]) for response in refused] == [
        (400, "invalid")
    ] * 3
    assert over.credentials == {}


def test_a_refused_credential_answers_none_of_what_was_sent(
    page: tuple[TestClient, ServerContext],
) -> None:
    client, over = page
    refused = client.put("/api/credentials/ecoinvent", json={"password": 987654321})
    assert refused.status_code == 400
    assert "987654321" not in refused.text
    assert over.credentials == {}
