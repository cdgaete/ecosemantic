"""The token a tunnel opens with: the interactive credential renewed with its rotating refresh
token, saved before it is answered, and the engine token an unattended server carries instead."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest

from ecosemantic.bridge.credentials import Credential
from ecosemantic.bridge.session import EngineTokenSession, Session, TunnelSession
from ecosemantic.bridge.signin import OpenIdProvider, discover, provider
from ecosemantic.errors import Invalid, Unauthorised
from ecosemantic.relay.discovery import BridgeConfiguration
from tests.bridge.fake_logto import (
    ACCOUNT,
    BRIDGE,
    BROWSER_CLIENT_ID,
    HANDLE,
    PAGE_URL,
    TOKEN_PATH,
    FakeLogto,
)

ENGINE = uuid4()
OTHER_ENGINE = uuid4()


def a_credential(**given: object) -> Credential:
    """A credential this systems directory keeps for one engine."""
    fields: dict[str, object] = {
        "bridge_url": BRIDGE,
        "client_id": BROWSER_CLIENT_ID,
        "engine": ENGINE,
        "account": ACCOUNT,
        "handle": HANDLE,
        "page_url": PAGE_URL,
        "refresh_token": "rt-old",
    }
    fields.update(given)
    return Credential.model_validate(fields)


def now() -> datetime:
    """This machine's clock."""
    return datetime.now(UTC)


class TraceStore:
    """A credential store that records each thing asked of it into a trace shared with the fake
    authorization server, so a test can read the order of them."""

    where = "the trace store"

    def __init__(self, credential: Credential | None, trace: list[str]) -> None:
        self.credential = credential
        self.trace = trace
        self.saved = asyncio.Event()

    def load(self) -> Credential | None:
        self.trace.append("load")
        return self.credential

    def save(self, credential: Credential) -> None:
        self.trace.append("save")
        self.credential = credential
        self.saved.set()

    def delete(self) -> None:
        self.trace.append("delete")
        self.credential = None


async def a_bridge(http: httpx2.AsyncClient) -> tuple[BridgeConfiguration, OpenIdProvider]:
    """The bridge's discovery document and Logto's endpoints, as the sessions read them."""
    config = await discover(http, BRIDGE)
    return config, await provider(http, config.issuer)


async def test_a_refreshed_token_is_stored_before_it_is_used() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        token = await session.access_token()
    trace.append("used")
    assert trace == ["load", "refreshed", "save", "used"]
    assert logto.access_tokens[token] == ACCOUNT
    assert store.credential is not None
    assert logto.live_refresh == {store.credential.refresh_token}


async def test_a_fresh_token_is_answered_without_renewing_it() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        first = await session.access_token()
        assert await session.access_token() == first
        assert len(logto.forms[TOKEN_PATH]) == 1
        assert await session.access_token(force=True) != first
        assert len(logto.forms[TOKEN_PATH]) == 2


async def test_a_token_expiring_within_a_minute_is_refreshed() -> None:
    logto = FakeLogto()
    logto.expires_in = 30
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, [])
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        first = await session.access_token()
        second = await session.access_token()
    assert second != first
    assert len(logto.forms[TOKEN_PATH]) == 2


async def test_a_refused_refresh_forgets_the_credential_and_signs_the_engine_out() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    credential = a_credential(refresh_token="rt-dead")
    store = TraceStore(credential, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        with pytest.raises(Unauthorised) as refused:
            await session.access_token()
    assert str(refused.value) == (
        "the bridge signed this engine out; run ecosemantic bridge sign-in"
    )
    assert store.credential is None
    assert trace == ["load", "delete"]


async def test_a_renewal_refused_for_another_reason_keeps_the_credential() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    credential = a_credential()
    store = TraceStore(credential, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        logto.overrides[TOKEN_PATH] = {"error": "invalid_client", "error_description": "gone"}
        session = TunnelSession(http, config, oidc, store, credential, now)
        with pytest.raises(Invalid) as refused:
            await session.access_token()
    assert "invalid_client" in str(refused.value)
    assert store.credential == credential
    assert trace == ["load"]


async def test_two_callers_share_one_renewal() -> None:
    logto = FakeLogto()
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, [])
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        first, second = await asyncio.gather(session.access_token(), session.access_token())
    assert first == second
    assert len(logto.forms[TOKEN_PATH]) == 1


async def test_a_cancelled_caller_leaves_the_rotated_token_in_the_store() -> None:
    logto = FakeLogto()
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, [])
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        logto.holding = asyncio.Event()
        caller = asyncio.create_task(session.access_token())
        await asyncio.wait_for(logto.reached.wait(), 5)
        caller.cancel()
        logto.holding.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        await asyncio.wait_for(store.saved.wait(), 5)
        assert store.credential is not None
        assert store.credential.refresh_token != credential.refresh_token
        assert store.credential.refresh_token in logto.live_refresh
        restarted = TunnelSession(http, config, oidc, store, store.credential, now)
        assert await restarted.access_token()


async def test_a_confirmation_racing_a_renewal_keeps_the_rotated_token() -> None:
    logto = FakeLogto()
    credential = a_credential()
    logto.live_refresh.add(credential.refresh_token)
    store = TraceStore(credential, [])
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        logto.holding = asyncio.Event()
        renewal = asyncio.create_task(session.access_token())
        await asyncio.wait_for(logto.reached.wait(), 5)
        confirmation = asyncio.create_task(session.confirmed("ana", "https://ana.bridge.test"))
        await asyncio.sleep(0)
        logto.holding.set()
        await renewal
        await confirmation
    assert store.credential is not None
    assert store.credential.refresh_token != credential.refresh_token
    assert store.credential.refresh_token in logto.live_refresh
    assert (store.credential.handle, store.credential.page_url) == (
        "ana",
        "https://ana.bridge.test",
    )


async def test_a_session_never_overwrites_a_credential_signed_in_again_meanwhile() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    mine = a_credential()
    signed_in_again = a_credential(engine=OTHER_ENGINE, refresh_token="rt-theirs")
    logto.live_refresh.add(signed_in_again.refresh_token)
    store = TraceStore(signed_in_again, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, mine, now)
        with pytest.raises(Unauthorised) as refused:
            await session.access_token()
    assert str(refused.value) == (
        "this systems directory was signed in again; this server's bridge stops"
    )
    assert store.credential == signed_in_again
    assert trace == ["load"]
    assert logto.forms.get(TOKEN_PATH) is None


async def test_a_session_whose_credential_was_signed_out_stops() -> None:
    trace: list[str] = []
    logto = FakeLogto(trace)
    credential = a_credential()
    store = TraceStore(None, trace)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config, oidc = await a_bridge(http)
        session = TunnelSession(http, config, oidc, store, credential, now)
        with pytest.raises(Unauthorised) as refused:
            await session.access_token()
    assert str(refused.value) == (
        "this systems directory was signed out; this server's bridge stops"
    )
    assert trace == ["load"]
    assert logto.forms.get(TOKEN_PATH) is None


async def test_an_engine_token_session_answers_its_token_and_refuses_to_renew_it() -> None:
    session: Session = EngineTokenSession(token="the-engine-token")
    assert await session.access_token() == "the-engine-token"
    with pytest.raises(Unauthorised) as refused:
        await session.access_token(force=True)
    assert str(refused.value) == (
        "the bridge refused this engine's engine token; the bridge's account page issues a new one"
    )
