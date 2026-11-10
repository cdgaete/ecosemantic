"""What a bridged start learns before the listener is built: the registration an engine token
buys, the credential the store keeps, and the sign-in a terminal makes when there is none."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest

from ecosemantic.bridge.credentials import Credential, store_for
from ecosemantic.bridge.session import EngineTokenSession, TunnelSession
from ecosemantic.bridge.signin import SignedOut
from ecosemantic.bridge.start import bridge_start, engine_name, engine_version
from ecosemantic.errors import Invalid, Unauthorised, Unavailable
from tests.bridge.fake_bridge import FakeBridge
from tests.bridge.fake_logto import (
    ACCOUNT,
    BRIDGE,
    BROWSER_CLIENT_ID,
    HANDLE,
    PAGE_URL,
    REGISTER_PATH,
    TOKEN_PATH,
    TUNNEL_URL,
    USER_CODE,
    VERIFICATION_URI,
    FakeLogto,
)
from tests.bridge.test_signin import Browser, Shown

ENGINE_BEARER = "the-engine-token"
DISPLAYED = {"DISPLAY": ":0"}
NOT_SIGNED_IN = "this engine is not signed in to the bridge"
SIGN_IN = "run ecosemantic bridge sign-in"
SIGNED_IN_AGAIN = "this systems directory was signed in again; this server's bridge stops"
SIGNED_OUT = "this systems directory was signed out; this server's bridge stops"
CHANGED_HANDLE = {"handle": "ana", "page_url": "https://ana.bridge.test"}


def opening(url: str) -> None:
    """An opener a start with no credential off a terminal never reaches."""
    raise AssertionError(f"a start off a terminal opens no browser: {url}")


def showing(code: str, address: str) -> None:
    """A device sign-in's code and address, which a start never shows."""
    raise AssertionError(f"a start shows no device code ({code} at {address})")


async def test_an_engine_token_start_registers_and_never_signs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    logto.access_tokens[ENGINE_BEARER] = ACCOUNT
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        started = await bridge_start(
            f"{BRIDGE}/",
            tmp_path,
            None,
            {"ECOSEMANTIC_BRIDGE_TOKEN": ENGINE_BEARER},
            False,
            opening,
            showing,
        )
    finally:
        await http.aclose()
    assert isinstance(started.session, EngineTokenSession)
    assert started.session.token == ENGINE_BEARER
    assert started.account == ACCOUNT
    assert started.handle == HANDLE
    assert started.page_url == PAGE_URL
    assert started.config.tunnel_url == TUNNEL_URL
    assert logto.forms.get(TOKEN_PATH) is None
    assert logto.registrations == [
        {"engine": None, "name": engine_name(), "version": engine_version()}
    ]
    bridge = FakeBridge(started.engine)
    started.check.welcome(bridge.welcome())
    assert started.check(bridge.proof("/api/product-systems"), "/api/product-systems") is True


async def test_a_token_start_keeps_a_secure_page_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    logto.access_tokens[ENGINE_BEARER] = ACCOUNT
    logto.register_as = {"page_url": "http://evil.example/"}
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        with pytest.raises(Invalid) as refused:
            await bridge_start(
                f"{BRIDGE}/",
                tmp_path,
                None,
                {"ECOSEMANTIC_BRIDGE_TOKEN": ENGINE_BEARER},
                False,
                opening,
                showing,
            )
    finally:
        await http.aclose()
    assert "http://evil.example/" in str(refused.value)


async def test_a_credential_start_keeps_a_secure_page_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    logto.register_as = {"page_url": "http://evil.example/"}
    credential_file = tmp_path / "credential.json"
    store_for(BRIDGE, tmp_path, credential_file).save(
        Credential(
            bridge_url=BRIDGE,
            client_id=BROWSER_CLIENT_ID,
            engine=uuid4(),
            account=ACCOUNT,
            handle=HANDLE,
            page_url=PAGE_URL,
            refresh_token="rt-kept",
        )
    )
    logto.live_refresh.add("rt-kept")
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        with pytest.raises(Invalid) as refused:
            await bridge_start(BRIDGE, tmp_path, credential_file, {}, False, opening, showing)
    finally:
        await http.aclose()
    assert "http://evil.example/" in str(refused.value)


async def test_a_start_without_a_credential_off_a_terminal_names_sign_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[str] = []

    async def unreachable(request: httpx2.Request) -> httpx2.Response:
        reached.append(str(request.url))
        raise AssertionError(f"a start with no credential reaches {request.url}")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(unreachable)) as http:
        monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
        with pytest.raises(Unavailable) as refused:
            await bridge_start(
                BRIDGE, tmp_path, tmp_path / "credential.json", {}, False, opening, showing
            )
    assert str(refused.value) == NOT_SIGNED_IN
    assert refused.value.hint == SIGN_IN
    assert reached == []


async def test_a_start_without_a_credential_at_a_terminal_signs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    credential_file = tmp_path / "credential.json"
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        started = await bridge_start(
            f"{BRIDGE}/", tmp_path, credential_file, DISPLAYED, True, browser, showing
        )
    finally:
        await http.aclose()
    browser.finished()
    credential = store_for(BRIDGE, tmp_path, credential_file).load()
    assert credential is not None
    assert isinstance(started.session, TunnelSession)
    assert started.engine == credential.engine
    assert started.account == ACCOUNT
    assert started.handle == HANDLE
    assert started.page_url == PAGE_URL
    assert credential.refresh_token in logto.live_refresh
    assert logto.registrations == [
        {"engine": str(credential.engine), "name": engine_name(), "version": engine_version()}
    ]


async def test_a_start_that_finds_a_changed_handle_takes_it_and_saves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    credential_file = tmp_path / "credential.json"
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        signed_in = await bridge_start(
            f"{BRIDGE}/", tmp_path, credential_file, DISPLAYED, True, browser, showing
        )
        browser.finished()
        logto.register_as = {"handle": "ana", "page_url": "https://ana.bridge.test"}
        started = await bridge_start(BRIDGE, tmp_path, credential_file, {}, False, opening, showing)
    finally:
        await http.aclose()
    stored = store_for(BRIDGE, tmp_path, credential_file).load()
    assert [registration["engine"] for registration in logto.registrations] == [
        str(signed_in.engine),
        str(signed_in.engine),
    ]
    assert started.engine == signed_in.engine
    assert started.account == ACCOUNT
    assert started.handle == "ana"
    assert started.page_url == "https://ana.bridge.test"
    assert stored is not None
    assert (stored.handle, stored.page_url) == ("ana", "https://ana.bridge.test")
    assert stored.refresh_token in logto.live_refresh


async def test_a_sign_in_during_the_registration_keeps_its_credential_and_stops_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    credential_file = tmp_path / "credential.json"
    store = store_for(BRIDGE, tmp_path, credential_file)
    signed_in_again = Credential(
        bridge_url=BRIDGE,
        client_id=BROWSER_CLIENT_ID,
        engine=uuid4(),
        account=ACCOUNT,
        handle=HANDLE,
        page_url=PAGE_URL,
        refresh_token="rt-signed-in-again",
    )

    async def signing_in_again(request: httpx2.Request) -> httpx2.Response:
        """A sign-in of another engine landing between a start's load and its confirmation."""
        if request.url.path == REGISTER_PATH:
            store.save(signed_in_again)
        return await logto.answer(request)

    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        await bridge_start(
            f"{BRIDGE}/", tmp_path, credential_file, DISPLAYED, True, browser, showing
        )
        browser.finished()
        logto.register_as = CHANGED_HANDLE
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(signing_in_again)
        ) as signing_in:
            monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: signing_in)
            with pytest.raises(Unauthorised) as refused:
                await bridge_start(BRIDGE, tmp_path, credential_file, {}, False, opening, showing)
    finally:
        await http.aclose()
    assert str(refused.value) == SIGNED_IN_AGAIN
    assert store.load() == signed_in_again


async def test_a_sign_out_during_the_registration_stops_the_start_as_signed_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    credential_file = tmp_path / "credential.json"
    store = store_for(BRIDGE, tmp_path, credential_file)
    store.save(
        Credential(
            bridge_url=BRIDGE,
            client_id=BROWSER_CLIENT_ID,
            engine=uuid4(),
            account=ACCOUNT,
            handle=HANDLE,
            page_url=PAGE_URL,
            refresh_token="rt-signed-out",
        )
    )
    logto.live_refresh.add("rt-signed-out")

    async def signing_out(request: httpx2.Request) -> httpx2.Response:
        """A sign-out emptying the store between a start's load and its confirmation."""
        if request.url.path == REGISTER_PATH:
            store.delete()
        return await logto.answer(request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(signing_out)) as http:
        monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
        with pytest.raises(SignedOut) as refused:
            await bridge_start(BRIDGE, tmp_path, credential_file, {}, False, opening, showing)
    assert str(refused.value) == SIGNED_OUT
    assert store.load() is None


async def test_a_registration_that_names_another_engine_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    credential_file = tmp_path / "credential.json"
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        await bridge_start(
            f"{BRIDGE}/", tmp_path, credential_file, DISPLAYED, True, browser, showing
        )
        browser.finished()
        logto.register_as = {"engine": str(uuid4())}
        with pytest.raises(Unauthorised) as refused:
            await bridge_start(BRIDGE, tmp_path, credential_file, {}, False, opening, showing)
    finally:
        await http.aclose()
    assert "not " in str(refused.value)


async def test_a_start_at_a_terminal_that_can_show_a_browser_signs_in_through_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    shown = Shown()
    credential_file = tmp_path / "credential.json"
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    try:
        await bridge_start(f"{BRIDGE}/", tmp_path, credential_file, DISPLAYED, True, browser, shown)
    finally:
        await http.aclose()
    browser.finished()
    assert len(browser.urls) == 1
    assert shown.codes == []


async def test_a_start_at_a_terminal_that_cannot_show_a_browser_takes_the_device_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logto = FakeLogto()
    logto.interval = 0
    logto.device_states = deque(["granted"])
    shown = Shown()
    credential_file = tmp_path / "credential.json"
    http = httpx2.AsyncClient(transport=logto.transport)
    monkeypatch.setattr("ecosemantic.bridge.start.client", lambda: http)
    monkeypatch.setattr(
        "ecosemantic.bridge.start.browser_reachable", lambda environ, platform: False
    )
    try:
        started = await bridge_start(
            f"{BRIDGE}/",
            tmp_path,
            credential_file,
            {"SSH_CONNECTION": "a b c d"},
            True,
            opening,
            shown,
        )
    finally:
        await http.aclose()
    assert shown.codes == [(USER_CODE, f"{VERIFICATION_URI}?user_code={USER_CODE}")]
    assert started.handle == HANDLE
    stored = store_for(BRIDGE, tmp_path, credential_file).load()
    assert stored is not None and stored.page_url == PAGE_URL
