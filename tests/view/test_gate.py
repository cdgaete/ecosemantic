"""The view's gate: the local token on the query, and the bridge's proof in the request's scope."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from ecosemantic.mcp.context import ServerContext
from ecosemantic.mcp.server import build_server
from ecosemantic.serve import ViewSettings, listener_for
from ecosemantic.view.api import BRIDGE_EXTENSION
from ecosemantic.view.app import TokenGate, build_view

PROOF = "a proof"
REFUSED = "the bridge's proof is required"


def application() -> Starlette:
    """A two-route application: one path under /api and one outside it."""

    async def api(request: Request) -> Response:
        return PlainTextResponse("api")

    async def page(request: Request) -> Response:
        return PlainTextResponse("page")

    return Starlette(routes=[Route("/api/x", api), Route("/page", page)])


def bridged(proof: str, path: str) -> bool:
    """A verifier admitting one proof."""
    return proof == PROOF


async def answered(
    app: Any,
    path: str,
    token: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> tuple[int, str]:
    """The status and the body an application answers for a hand-built scope."""
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": f"token={token}".encode() if token is not None else b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 0),
        "server": ("test", 80),
    }
    if extensions is not None:
        scope["extensions"] = dict(extensions)
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], body.decode()


async def test_a_bridged_request_whose_proof_is_admitted_reaches_every_path_without_the_token() -> (
    None
):
    gate = TokenGate(application(), "secret", bridged=bridged)
    extensions = {BRIDGE_EXTENSION: {"proof": PROOF}}
    assert await answered(gate, "/api/x", extensions=extensions) == (200, "api")
    assert await answered(gate, "/page", extensions=extensions) == (200, "page")


async def test_a_bridged_request_whose_proof_is_refused_is_answered_401() -> None:
    gate = TokenGate(application(), "secret", bridged=bridged)
    refused = {BRIDGE_EXTENSION: {"proof": "another proof"}}
    for path in ("/api/x", "/page"):
        status, body = await answered(gate, path, extensions=refused)
        assert status == 401
        assert json.loads(body) == {
            "error": "unauthorised",
            "message": REFUSED,
            "details": {},
        }


async def test_a_bridged_request_reaching_a_gate_without_a_verifier_is_refused() -> None:
    gate = TokenGate(application(), "secret")
    extensions = {BRIDGE_EXTENSION: {"proof": PROOF}}
    status, body = await answered(gate, "/api/x", token="secret", extensions=extensions)
    assert status == 401
    assert json.loads(body)["message"] == REFUSED


async def test_the_verifier_receives_the_proof_and_the_path() -> None:
    seen: list[tuple[str, str]] = []

    def watch(proof: str, path: str) -> bool:
        seen.append((proof, path))
        return True

    gate = TokenGate(application(), "secret", bridged=watch)
    await answered(gate, "/api/x", extensions={BRIDGE_EXTENSION: {"proof": "one"}})
    await answered(gate, "/page", extensions={BRIDGE_EXTENSION: {"proof": "two"}})
    assert seen == [("one", "/api/x"), ("two", "/page")]


def test_a_request_over_the_network_cannot_carry_a_proof() -> None:
    called: list[str] = []

    def watch(proof: str, path: str) -> bool:
        called.append(proof)
        return True

    gate = TokenGate(application(), "secret", bridged=watch)
    with TestClient(gate) as client:
        refused = client.get("/api/x", headers={"ecosemantic.bridge": PROOF})
    assert refused.status_code == 401
    assert json.loads(refused.text)["message"] == "the token in the link is required"
    assert called == []


def test_the_local_token_still_gates_an_unbridged_request() -> None:
    gate = TokenGate(application(), "secret", bridged=bridged)
    with TestClient(gate) as client:
        assert client.get("/api/x").status_code == 401
        assert client.get("/api/x", params={"token": "wrong"}).status_code == 401
        assert client.get("/api/x", params={"token": "secret"}).status_code == 200
        assert client.get("/page").status_code == 200


async def test_a_gate_with_no_local_token_admits_an_unbridged_request() -> None:
    gate = TokenGate(application(), None, bridged=bridged)
    assert await answered(gate, "/api/x") == (200, "api")
    assert await answered(gate, "/api/x", token="") == (200, "api")
    assert await answered(gate, "/page") == (200, "page")
    refused = {BRIDGE_EXTENSION: {"proof": "another proof"}}
    assert (await answered(gate, "/api/x", extensions=refused))[0] == 401


async def test_a_token_that_is_not_ascii_is_refused_rather_than_breaking_the_gate() -> None:
    gate = TokenGate(application(), "secret")
    assert (await answered(gate, "/api/x", token="café"))[0] == 401
    assert (await answered(gate, "/api/x", token="secret"))[0] == 200


async def test_a_bridge_extension_carrying_no_proof_is_refused() -> None:
    gate = TokenGate(application(), "secret", bridged=bridged)
    for extension in (None, {}, {"proof": 7}):
        extensions = {BRIDGE_EXTENSION: extension}
        status, body = await answered(gate, "/api/x", token="secret", extensions=extensions)
        assert status == 401
        assert json.loads(body)["message"] == REFUSED


async def test_an_application_handed_only_a_verifier_is_wrapped_in_the_gate(
    context: ServerContext, systems_dir: Path
) -> None:
    built = build_view(context, build_server(context), bridged=bridged)
    assert isinstance(built, TokenGate)
    admitted = {BRIDGE_EXTENSION: {"proof": PROOF}}
    assert (await answered(built, "/api/nothing-here", extensions=admitted))[0] != 401
    refused = {BRIDGE_EXTENSION: {"proof": "another proof"}}
    assert (await answered(built, "/api/nothing-here", extensions=refused))[0] == 401
    listener = listener_for(context, ViewSettings(transport="http"), systems_dir, bridged=bridged)
    listener.socket.close()
    assert isinstance(listener.app, TokenGate)
    assert (await answered(listener.app, "/api/nothing-here", extensions=admitted))[0] != 401


async def test_a_listener_with_a_bridge_and_no_token_answers_a_local_call(
    context: ServerContext, systems_dir: Path
) -> None:
    listener = listener_for(context, ViewSettings(transport="http"), systems_dir, bridged=bridged)
    listener.socket.close()
    assert listener.token is None
    status, body = await answered(listener.app, "/api/product-systems")
    assert status == 200
    assert isinstance(json.loads(body)["value"], list)
