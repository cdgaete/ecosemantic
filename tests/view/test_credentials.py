from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.view.app import build_view

NOWHERE = Path("/nonexistent-static")
LOOPBACK = ("127.0.0.1", 50000)
ELSEWHERE = ("192.168.1.20", 50000)
HINT = "run ecosemantic setup, or reach the page through an SSH tunnel"
ACCOUNT = {"username": "me", "password": "hunter2"}


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
    over = dataclasses.replace(context, credentials={}, client={})
    app = build_view(over, build_server(over), static=NOWHERE)
    with TestClient(app, client=ELSEWHERE) as outside:
        answered = [
            outside.put("/api/credentials/ecoinvent", json=ACCOUNT),
            outside.get("/api/credentials"),
            outside.delete("/api/credentials/ecoinvent"),
        ]
    assert [(response.status_code, response.json()["error"]) for response in answered] == [
        (401, "unauthorised")
    ] * 3
    assert [response.json()["details"]["hint"] for response in answered] == [HINT] * 3
    assert over.credentials == {}


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
