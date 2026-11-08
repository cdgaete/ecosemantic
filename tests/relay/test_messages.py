from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from ecosemantic.relay.errors import RelayError
from ecosemantic.relay.messages import (
    PROTOCOL,
    Hello,
    Message,
    RequestStart,
    Reset,
    ResponseStart,
    Welcome,
    decode,
    door_of,
    encode,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ENGINE = UUID("6f3d1e2a-0000-4000-8000-000000000001")
KEY = {
    "kty": "OKP",
    "crv": "Ed25519",
    "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
    "kid": "bridge-1",
    "alg": "EdDSA",
    "use": "sig",
}
MESSAGES = [
    Hello(protocol=PROTOCOL, engine=ENGINE, version="0.1.12"),
    Welcome(
        protocol=PROTOCOL,
        engine=ENGINE,
        account="acct_1",
        handle="widgets",
        now=NOW,
        keys=[KEY],
    ),
    RequestStart(
        stream=1,
        door="mcp",
        method="POST",
        path="/mcp",
        query="",
        headers=[("accept", "application/json")],
        proof="proof",
    ),
    ResponseStart(stream=1, status=200, headers=[("content-type", "application/json")]),
    Reset(stream=1, reason="cancelled"),
    Reset(stream=2, reason="failed"),
]


@pytest.mark.parametrize("message", MESSAGES)
def test_every_message_round_trips_through_its_text(message: Message) -> None:
    assert decode(encode(message)) == message


@pytest.mark.parametrize("text", ["{}", "not json", '{"type": "goodbye"}'])
def test_a_text_that_is_no_message_is_a_relay_error(text: str) -> None:
    with pytest.raises(RelayError):
        decode(text)


def test_mcp_and_its_subpaths_belong_to_the_chats_door() -> None:
    assert door_of("/mcp") == "mcp"
    assert door_of("/mcp/x") == "mcp"
    assert door_of("/mcpx") == "page"
    assert door_of("/api/mcp") == "page"
    assert door_of("/") == "page"
