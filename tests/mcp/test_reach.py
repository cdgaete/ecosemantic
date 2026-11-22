"""How a request reached the engine, a proxy on the engine's computer included."""

from __future__ import annotations

import pytest
from starlette.types import Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from ecosemantic.mcp.reach import BRIDGE_EXTENSION, reach

LOCAL = ("127.0.0.1", 50000)


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1"])
def test_a_loopback_peer_is_on_this_computer(peer: str) -> None:
    assert reach({"client": (peer, 50000), "headers": []}) == "here"


@pytest.mark.parametrize("client", [("192.0.2.7", 50000), ("", 0), None])
def test_any_other_peer_is_across_the_network(client: tuple[str, int] | None) -> None:
    assert reach({"client": client, "headers": []}) == "network"


@pytest.mark.parametrize(
    "header",
    [
        "forwarded",
        "via",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-forwarded-server",
        "x-original-forwarded-for",
        "x-real-ip",
        "x-client-ip",
        "true-client-ip",
        "cf-connecting-ip",
        "cf-ray",
        "tailscale-user-login",
    ],
)
async def test_what_a_proxy_on_this_computer_forwards_is_across_the_network(header: str) -> None:
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(reach(scope))

    async def receive() -> dict[str, str]:
        return {"type": "http.request"}

    async def send(message: object) -> None:
        pass

    # the value claims loopback, which uvicorn's own middleware keeps as the peer
    scope = {
        "type": "http",
        "scheme": "http",
        "client": LOCAL,
        "headers": [(header.encode(), b"127.0.0.1")],
    }
    await ProxyHeadersMiddleware(app)(scope, receive, send)
    assert seen == ["network"]


def test_the_bridge_is_the_bridge_whatever_it_forwards() -> None:
    scope = {
        "client": LOCAL,
        "headers": [(b"x-forwarded-for", b"192.0.2.7")],
        "extensions": {BRIDGE_EXTENSION: {"proof": "proof"}},
    }
    assert reach(scope) == "bridge"
