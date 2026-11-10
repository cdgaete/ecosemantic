"""How an engine signs in to the bridge through Logto: the browser with a loopback redirect, the
device flow on a machine without a browser, the registration, and the sign-out."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
import threading
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx2
import jwt
import pytest
import truststore
from cryptography.hazmat.primitives import serialization

from ecosemantic.bridge.credentials import Credential, store_for
from ecosemantic.bridge.signin import (
    TIMEOUT,
    SignedOut,
    browser_sign_in,
    client,
    device_sign_in,
    discover,
    provider,
    refresh,
    secure,
    sign_in,
    sign_out,
)
from ecosemantic.errors import Invalid, Unauthorised, Unavailable
from ecosemantic.relay.discovery import WELL_KNOWN
from tests.bridge.fake_logto import (
    ACCOUNT,
    ALGORITHM,
    BRIDGE,
    BROWSER_CLIENT_ID,
    CODE,
    DEVICE_CLIENT_ID,
    DEVICE_CODE,
    DEVICE_PATH,
    EDDSA_KEY,
    HANDLE,
    ISSUER,
    JWKS_PATH,
    KEY,
    KID,
    OPENID_PATH,
    OTHER_KEY,
    PAGE_URL,
    REGISTER_PATH,
    REVOKE_PATH,
    RSA_KEY,
    TOKEN_PATH,
    TUNNEL_RESOURCE,
    TUNNEL_SCOPE,
    USER_CODE,
    VERIFICATION_URI,
    FakeLogto,
)


def a_credential(**given: object) -> Credential:
    """A credential a sign-in of this engine leaves behind."""
    fields: dict[str, object] = {
        "bridge_url": BRIDGE,
        "client_id": BROWSER_CLIENT_ID,
        "engine": uuid4(),
        "account": ACCOUNT,
        "handle": HANDLE,
        "page_url": PAGE_URL,
        "refresh_token": "rt-1",
    }
    fields.update(given)
    return Credential.model_validate(fields)


class Browser:
    """The browser a sign-in opens: it carries the authorization request to the fake Logto, then
    answers the loopback callback from another thread, as a browser of this machine would."""

    def __init__(
        self,
        logto: FakeLogto,
        code: str | None = CODE,
        state: str | None = None,
        error: str | None = None,
        prefetch: tuple[str, str] | None = None,
    ) -> None:
        self.logto = logto
        self.code = code
        self.state = state
        self.error = error
        self.prefetch = prefetch
        self.urls: list[str] = []
        self.pages: list[str] = []
        self.prefetched: list[int] = []
        self.failures: list[BaseException] = []
        self.threads: list[threading.Thread] = []

    def __call__(self, authorization_url: str) -> None:
        """Visit the authorization URL, then ask for the redirect it names."""
        self.urls.append(authorization_url)
        self.logto.visited(authorization_url)
        query = parse_qs(urlsplit(authorization_url).query)
        answer = {"state": query["state"][0] if self.state is None else self.state}
        if self.code is not None:
            answer["code"] = self.code
        if self.error is not None:
            answer["error"] = self.error
        redirect = query["redirect_uri"][0]
        origin = redirect.removesuffix("/callback")
        thread = threading.Thread(
            target=self._ask, args=(origin, f"{redirect}?{urlencode(answer)}")
        )
        self.threads.append(thread)
        thread.start()

    def finished(self) -> None:
        """Wait for the browser's requests, and the page the callback answered with."""
        for thread in self.threads:
            thread.join(timeout=10)
        assert self.failures == []

    def _ask(self, origin: str, target: str) -> None:
        try:
            with httpx2.Client(trust_env=False, timeout=10) as browser:
                if self.prefetch is not None:
                    method, path = self.prefetch
                    self.prefetched.append(browser.request(method, f"{origin}{path}").status_code)
                self.pages.append(browser.get(target).text)
        except BaseException as failure:
            self.failures.append(failure)


class Shown:
    """What a sign-in answers the person with: the code and the address that takes it."""

    def __init__(self) -> None:
        self.codes: list[tuple[str, str]] = []

    def __call__(self, user_code: str, verification_uri_complete: str) -> None:
        self.codes.append((user_code, verification_uri_complete))


def no_browser(authorization_url: str) -> None:
    """An opener that opens nothing, for a sign-in nobody finishes."""


def an_id_token(**given: object) -> str:
    """An ID token this fake's key signs, with the claims a test names."""
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": BROWSER_CLIENT_ID,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(given)
    kid = claims.pop("kid", KID)
    algorithm = str(claims.pop("algorithm", ALGORITHM))
    key = claims.pop("key", KEY)
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid})


def url_segment(document: Mapping[str, object]) -> str:
    """One segment of a token, base64url without padding."""
    raw = json.dumps(document, separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def a_token_naming_its_key_s_algorithm_but_signed_with_its_bytes() -> str:
    """An ID token whose header names the algorithm the JWKS publishes for its `kid`, signed HS256
    with that key's public bytes as the secret, which is how an algorithm-confusion attack is
    built."""
    secret = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    now = int(datetime.now(UTC).timestamp())
    claims = url_segment(
        {
            "iss": ISSUER,
            "sub": ACCOUNT,
            "aud": BROWSER_CLIENT_ID,
            "iat": now,
            "exp": now + 300,
        }
    )
    signed = f"{url_segment({'alg': ALGORITHM, 'kid': KID, 'typ': 'JWT'})}.{claims}"
    signature = hmac.new(secret, signed.encode("ascii"), hashlib.sha256).digest()
    return f"{signed}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


async def a_signing_in_credential(tmp_path: Path, logto: FakeLogto) -> Credential:
    """The credential a browser sign-in at this fake leaves in this systems directory."""
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        return await sign_in(
            http,
            BRIDGE,
            store_for(BRIDGE, tmp_path, None),
            False,
            "workstation",
            "0.1.12",
            Browser(logto),
            Shown(),
        )


async def test_a_browser_sign_in_sends_pkce_the_resource_and_the_scopes_and_stores_the_engine(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        credential = await sign_in(
            http, BRIDGE, store, False, "workstation", "0.1.12", browser, Shown()
        )
    browser.finished()
    exchange = logto.forms[TOKEN_PATH][-1]
    assert logto.authorized["client_id"] == BROWSER_CLIENT_ID
    assert logto.authorized["code_challenge_method"] == "S256"
    assert logto.authorized["resource"] == TUNNEL_RESOURCE
    assert logto.authorized["scope"] == f"openid offline_access {TUNNEL_SCOPE}"
    assert logto.authorized["redirect_uri"].startswith("http://127.0.0.1:")
    assert logto.authorized["redirect_uri"].endswith("/callback")
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["code"] == CODE
    assert len(exchange["code_verifier"]) == 64
    assert exchange["resource"] == TUNNEL_RESOURCE
    assert exchange["redirect_uri"] == logto.authorized["redirect_uri"]
    assert browser.pages == ["Signed in to the EcoSemantic bridge. You can close this tab."]
    assert store.load() == credential
    assert credential.bridge_url == BRIDGE
    assert credential.client_id == BROWSER_CLIENT_ID
    assert credential.account == ACCOUNT
    assert credential.handle == HANDLE
    assert credential.page_url == PAGE_URL
    assert credential.refresh_token in logto.live_refresh
    assert logto.registrations == [
        {"engine": str(credential.engine), "name": "workstation", "version": "0.1.12"}
    ]


async def test_the_browser_is_opened_at_a_request_that_asks_for_consent_with_offline_access(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    browser = Browser(logto)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        await sign_in(
            http,
            BRIDGE,
            store_for(BRIDGE, tmp_path, None),
            False,
            "workstation",
            "0.1.12",
            browser,
            Shown(),
        )
    browser.finished()
    query = parse_qs(urlsplit(browser.urls[0]).query)
    assert query["prompt"] == ["consent"]
    assert "offline_access" in query["scope"][0].split()


async def test_a_request_that_is_no_get_callback_does_not_end_the_sign_in(
    tmp_path: Path,
) -> None:
    for method, path in (("GET", "/favicon.ico"), ("POST", "/callback")):
        logto = FakeLogto()
        browser = Browser(logto, prefetch=(method, path))
        store = store_for(BRIDGE, tmp_path, None)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            credential = await sign_in(
                http, BRIDGE, store, False, "workstation", "0.1.12", browser, Shown()
            )
        browser.finished()
        assert browser.prefetched == [404]
        assert store.load() == credential


async def test_a_callback_with_another_state_is_refused(tmp_path: Path) -> None:
    logto = FakeLogto()
    browser = Browser(logto, state="another-sign-in")
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unauthorised) as refused:
            await sign_in(http, BRIDGE, store, False, "workstation", "0.1.12", browser, Shown())
    browser.finished()
    assert "another sign-in" in str(refused.value)
    assert store.load() is None
    assert logto.forms.get(TOKEN_PATH) is None


async def test_a_callback_carrying_an_error_or_no_code_is_refused(tmp_path: Path) -> None:
    for answer in ({"error": "access_denied"}, {"code": None}):
        logto = FakeLogto()
        store = store_for(BRIDGE, tmp_path, None)
        browser = Browser(logto, **answer)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            with pytest.raises(Unauthorised) as refused:
                await sign_in(http, BRIDGE, store, False, "workstation", "0.1.12", browser, Shown())
        browser.finished()
        assert "the sign-in" in str(refused.value)
        assert store.load() is None


async def test_a_code_the_authorization_server_refuses_is_unauthorised(tmp_path: Path) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unauthorised) as refused:
            await sign_in(
                http,
                BRIDGE,
                store,
                False,
                "workstation",
                "0.1.12",
                Browser(logto, code="stale"),
                Shown(),
            )
    assert "invalid_grant" in str(refused.value)
    assert store.load() is None


async def test_a_sign_in_not_finished_in_time_is_unavailable() -> None:
    logto = FakeLogto()
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await browser_sign_in(http, config, oidc, no_browser, wait=0.1)
    assert str(refused.value) == "the sign-in was not finished within 5 minutes"


async def test_a_device_sign_in_shows_the_code_and_polls_through_pending_and_slow_down() -> None:
    logto = FakeLogto()
    logto.interval = None
    sleeps: list[float] = []
    shown = Shown()

    async def slept(seconds: float) -> None:
        sleeps.append(seconds)

    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        tokens = await device_sign_in(http, config, oidc, shown, sleep=slept)
    assert shown.codes == [(USER_CODE, f"{VERIFICATION_URI}?user_code={USER_CODE}")]
    assert sleeps == [5, 5, 10]
    assert logto.forms[DEVICE_PATH][-1]["client_id"] == DEVICE_CLIENT_ID
    assert logto.forms[DEVICE_PATH][-1]["resource"] == TUNNEL_RESOURCE
    assert tokens.account == ACCOUNT
    assert tokens.refresh_token in logto.live_refresh


async def test_a_device_sign_in_polls_at_the_interval_it_is_given() -> None:
    logto = FakeLogto()
    logto.interval = 2
    logto.device_states = deque(["slow_down", "granted"])
    sleeps: list[float] = []

    async def slept(seconds: float) -> None:
        sleeps.append(seconds)

    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        await device_sign_in(http, config, oidc, Shown(), sleep=slept)
    assert sleeps == [2, 7]


async def test_a_device_sign_in_that_will_not_be_granted_is_unauthorised() -> None:
    async def slept(seconds: float) -> None:
        return None

    for state in ("expired_token", "access_denied"):
        logto = FakeLogto()
        logto.device_states = deque([state])
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            config = await discover(http, BRIDGE)
            oidc = await provider(http, config.issuer)
            with pytest.raises(Unauthorised) as refused:
                await device_sign_in(http, config, oidc, Shown(), sleep=slept)
        assert state in str(refused.value)


async def test_a_device_sign_in_polls_on_past_a_failed_poll() -> None:
    logto = FakeLogto()
    logto.device_states = deque(["authorization_pending", "granted"])
    sleeps: list[float] = []
    failed: list[bool] = []

    async def slept(seconds: float) -> None:
        sleeps.append(seconds)

    async def answer(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == TOKEN_PATH and not failed:
            failed.append(True)
            return httpx2.Response(503)
        return await logto.answer(request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(answer)) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        tokens = await device_sign_in(http, config, oidc, Shown(), sleep=slept)
    assert failed == [True]
    assert sleeps == [5, 5, 5]
    assert tokens.account == ACCOUNT
    assert tokens.refresh_token in logto.live_refresh


async def test_a_device_sign_in_gives_up_when_its_code_expires() -> None:
    logto = FakeLogto()
    logto.overrides[DEVICE_PATH] = {
        "device_code": DEVICE_CODE,
        "user_code": USER_CODE,
        "verification_uri": VERIFICATION_URI,
        "verification_uri_complete": f"{VERIFICATION_URI}?user_code={USER_CODE}",
        "expires_in": 100,
    }
    logto.failures = {TOKEN_PATH}
    slept_for = [0.0]
    sleeps: list[float] = []

    async def slept(seconds: float) -> None:
        sleeps.append(seconds)
        slept_for[0] += seconds

    def clock() -> float:
        """A clock each poll carries 30 seconds further than the sleeps, as a request may."""
        return slept_for[0] + TIMEOUT * len(logto.forms.get(TOKEN_PATH, []))

    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await device_sign_in(http, config, oidc, Shown(), sleep=slept, clock=clock)
    assert sleeps == [5, 5, 5]
    assert len(logto.forms[TOKEN_PATH]) == 3
    assert "100" in str(refused.value)
    assert "503" in str(refused.value)


async def test_a_device_authorization_answer_without_an_expiry_is_refused() -> None:
    logto = FakeLogto()
    logto.overrides[DEVICE_PATH] = {
        "device_code": DEVICE_CODE,
        "user_code": USER_CODE,
        "verification_uri": VERIFICATION_URI,
        "verification_uri_complete": f"{VERIFICATION_URI}?user_code={USER_CODE}",
    }
    shown = Shown()

    async def slept(seconds: float) -> None:
        return None

    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await device_sign_in(http, config, oidc, shown, sleep=slept)
    assert "expires_in" in str(refused.value)
    assert shown.codes == []
    assert logto.forms.get(TOKEN_PATH) is None


async def test_a_transport_error_with_no_message_is_named_by_its_class() -> None:
    logto = FakeLogto()
    logto.overrides[DEVICE_PATH] = {
        "device_code": DEVICE_CODE,
        "user_code": USER_CODE,
        "verification_uri": VERIFICATION_URI,
        "verification_uri_complete": f"{VERIFICATION_URI}?user_code={USER_CODE}",
        "expires_in": 10,
    }
    slept_for = [0.0]

    async def slept(seconds: float) -> None:
        slept_for[0] += seconds

    async def answer(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == TOKEN_PATH:
            raise httpx2.ReadTimeout("")
        return await logto.answer(request)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(answer)) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await device_sign_in(
                http, config, oidc, Shown(), sleep=slept, clock=lambda: slept_for[0]
            )
    assert "ReadTimeout" in str(refused.value)


async def test_a_device_sign_in_registers_the_engine_and_stores_it(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.interval = 0
    logto.device_states = deque(["granted"])
    store = store_for(BRIDGE, tmp_path, None)
    shown = Shown()
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        credential = await sign_in(
            http, BRIDGE, store, True, "workstation", "0.1.12", no_browser, shown
        )
    assert shown.codes == [(USER_CODE, f"{VERIFICATION_URI}?user_code={USER_CODE}")]
    assert credential.client_id == DEVICE_CLIENT_ID
    assert store.load() == credential
    assert logto.forms[TOKEN_PATH][-1]["client_id"] == DEVICE_CLIENT_ID
    assert str(credential.engine) == logto.registrations[-1]["engine"]


async def test_an_id_token_signed_by_another_key_is_refused(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.signing_key = OTHER_KEY
    store = store_for(BRIDGE, tmp_path, None)
    browser = Browser(logto)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unauthorised) as refused:
            await sign_in(http, BRIDGE, store, False, "workstation", "0.1.12", browser, Shown())
    browser.finished()
    assert "the ID token" in str(refused.value)
    assert store.load() is None
    assert logto.registrations == []


async def test_an_id_token_signed_eddsa_by_a_key_naming_eddsa_verifies(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.signs_with(EDDSA_KEY, "EdDSA")
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        credential = await sign_in(
            http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
        )
    assert store.load() == credential
    assert credential.account == ACCOUNT


async def test_an_id_token_signed_rs256_by_a_key_naming_rs256_verifies(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.signs_with(RSA_KEY, "RS256")
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        credential = await sign_in(
            http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
        )
    assert logto.jwk["kty"] == "RSA" and logto.jwk["alg"] == "RS256"
    assert store.load() == credential
    assert credential.account == ACCOUNT


async def test_a_token_naming_its_key_s_algorithm_but_signed_with_its_bytes_is_refused(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    forged = a_token_naming_its_key_s_algorithm_but_signed_with_its_bytes()
    assert jwt.get_unverified_header(forged)["alg"] == ALGORITHM
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        logto.overrides[TOKEN_PATH] = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 60,
            "id_token": forged,
        }
        with pytest.raises(Unauthorised) as refused:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
    assert "no key Logto publishes verifies it" in str(refused.value)
    assert store.load() is None


@pytest.mark.parametrize(
    "minted",
    [
        pytest.param(
            an_id_token(algorithm="HS256", key="the-shared-secret-of-this-fake-01"),
            id="an HS256 token",
        ),
        pytest.param(
            an_id_token(algorithm="EdDSA", key=EDDSA_KEY),
            id="another algorithm than its key's",
        ),
        pytest.param(an_id_token(algorithm="none", key=None), id="an unsecured token"),
    ],
)
async def test_an_id_token_signed_with_another_algorithm_than_its_key_s_names_is_refused(
    minted: str, tmp_path: Path
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        logto.overrides[TOKEN_PATH] = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 60,
            "id_token": minted,
        }
        with pytest.raises(Unauthorised) as refused:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
    assert jwt.get_unverified_header(minted)["alg"] in str(refused.value)
    assert ALGORITHM in str(refused.value)
    assert store.load() is None


async def test_a_key_naming_an_algorithm_outside_the_asymmetric_ones_is_refused(
    tmp_path: Path,
) -> None:
    for named in ("HS256", "none", "ES256K"):
        logto = FakeLogto()
        logto.jwk = {**logto.jwk, "alg": named}
        store = store_for(BRIDGE, tmp_path, None)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            with pytest.raises(Unauthorised) as refused:
                await sign_in(
                    http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
                )
        assert named in str(refused.value)
        assert store.load() is None


async def test_a_key_without_an_algorithm_takes_the_one_its_curve_implies(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    del logto.jwk["alg"]
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        credential = await sign_in(
            http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
        )
    assert store.load() == credential


async def test_a_key_without_an_algorithm_that_implies_none_is_refused(tmp_path: Path) -> None:
    logto = FakeLogto()
    without_curve = {name: value for name, value in logto.jwk.items() if name not in ("alg", "crv")}
    for key in (without_curve, {"kty": "oct", "kid": KID, "k": "dGhlLXNoYXJlZC1zZWNyZXQ"}):
        logto = FakeLogto()
        logto.jwk = dict(key)
        store = store_for(BRIDGE, tmp_path, None)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            with pytest.raises(Unauthorised) as refused:
                await sign_in(
                    http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
                )
        assert "names no algorithm" in str(refused.value)
        assert store.load() is None


async def test_a_key_whose_published_fields_are_no_key_is_refused(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.jwk = {**logto.jwk, "x": "not-a-coordinate"}
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unauthorised) as refused:
            await sign_in(
                http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
            )
    assert "is no key this sign-in can verify with" in str(refused.value)
    assert store.load() is None


async def test_a_registration_answering_another_engine_or_account_is_refused(
    tmp_path: Path,
) -> None:
    for answer in ({"engine": str(uuid4())}, {"account": "someone-else"}):
        logto = FakeLogto()
        logto.register_as = answer
        store = store_for(BRIDGE, tmp_path, None)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            with pytest.raises(Unauthorised) as refused:
                await sign_in(
                    http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
                )
        assert "registered" in str(refused.value)
        assert store.load() is None


async def test_a_page_address_that_is_no_https_is_refused(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.register_as = {"page_url": "http://carlos.bridge.test"}
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Invalid) as refused:
            await sign_in(
                http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
            )
    assert "http://carlos.bridge.test" in str(refused.value)
    assert store.load() is None


async def test_a_registration_refused_with_a_token_the_bridge_does_not_know_is_unauthorised(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    logto.broken[REGISTER_PATH] = (401, '{"error": "invalid_token"}')
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unauthorised) as refused:
            await sign_in(
                http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
            )
    assert "answered 401" in str(refused.value)
    assert "invalid_token" in str(refused.value)
    assert store.load() is None


async def test_a_registration_the_bridge_refuses_is_unavailable(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.failures.add(REGISTER_PATH)
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as refused:
            await sign_in(
                http, BRIDGE, store, False, "workstation", "0.1.12", Browser(logto), Shown()
            )
    assert "503" in str(refused.value)
    assert store.load() is None


async def test_sign_out_revokes_the_refresh_token_and_forgets_the_credential(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    credential = await a_signing_in_credential(tmp_path, logto)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        assert await sign_out(http, store) == credential
    assert logto.revoked == [credential.refresh_token]
    assert logto.forms[REVOKE_PATH][-1] == {
        "token": credential.refresh_token,
        "token_type_hint": "refresh_token",
        "client_id": BROWSER_CLIENT_ID,
    }
    assert credential.refresh_token not in logto.live_refresh
    assert store.load() is None


async def test_a_sign_out_with_a_store_holding_no_credential_answers_none(tmp_path: Path) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        assert await sign_out(http, store) is None
    assert logto.requests == []


async def test_a_revocation_the_authorization_server_fails_leaves_the_credential(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    logto.failures.add(REVOKE_PATH)
    store = store_for(BRIDGE, tmp_path, None)
    credential = await a_signing_in_credential(tmp_path, logto)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as refused:
            await sign_out(http, store)
    assert "503" in str(refused.value)
    assert refused.value.hint is None
    assert store.load() == credential


async def test_a_sign_out_whose_bridge_cannot_be_reached_keeps_the_credential(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    store = store_for(BRIDGE, tmp_path, None)
    credential = await a_signing_in_credential(tmp_path, logto)
    logto.failures.add(WELL_KNOWN)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as refused:
            await sign_out(http, store)
    assert refused.value.hint is None
    assert store.load() == credential


async def test_a_bridge_or_authorization_server_that_fails_is_unavailable() -> None:
    logto = FakeLogto()
    logto.failures.add(WELL_KNOWN)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as refused:
            await discover(http, BRIDGE)
    assert "503" in str(refused.value)
    logto = FakeLogto()
    logto.failures.add(OPENID_PATH)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as hollow:
            await provider(http, "https://auth.test/oidc")
    assert "503" in str(hollow.value)


async def test_a_sign_in_whose_requests_fail_is_unavailable(tmp_path: Path) -> None:
    logto = FakeLogto()
    logto.failures.add(DEVICE_PATH)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await device_sign_in(http, config, oidc, Shown())
        assert "503" in str(refused.value)
        logto.failures = {TOKEN_PATH}
        with pytest.raises(Unavailable) as hollow:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "answered 503" in str(hollow.value)
        logto.failures = {JWKS_PATH}
        with pytest.raises(Unavailable) as keys:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "answered 503" in str(keys.value)
        logto.broken[JWKS_PATH] = (401, '{"error": "invalid_token"}')
        with pytest.raises(Unavailable) as denied:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "answered 401" in str(denied.value)
        assert "invalid_token" in str(denied.value)


async def test_a_renewal_refused_as_invalid_grant_is_signed_out(tmp_path: Path) -> None:
    logto = FakeLogto()
    credential = a_credential(refresh_token="rt-dead")
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(SignedOut) as refused:
            await refresh(http, oidc, config, credential)
    assert isinstance(refused.value, Unauthorised)
    assert str(refused.value) == (
        "the bridge signed this engine out; run ecosemantic bridge sign-in"
    )


async def test_a_renewal_refused_for_another_reason_is_invalid(tmp_path: Path) -> None:
    logto = FakeLogto()
    credential = a_credential()
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        logto.overrides[TOKEN_PATH] = {"error": "invalid_client", "error_description": "gone"}
        with pytest.raises(Invalid) as refused:
            await refresh(http, oidc, config, credential)
    assert "invalid_client" in str(refused.value)


async def test_a_proxy_answering_html_to_the_token_request_is_unavailable(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    logto.broken[TOKEN_PATH] = (502, "<html><body>Bad gateway</body></html>")
    store = store_for(BRIDGE, tmp_path, None)
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        with pytest.raises(Unavailable) as refused:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
    assert "answered 502" in str(refused.value)
    assert store.load() is None
    logto.broken[TOKEN_PATH] = (500, '{"status": "down"}')
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as status:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
    assert str(status.value) == "Logto at https://auth.test/oidc/token answered 500"


async def test_a_discovery_answer_that_is_no_document_is_unavailable() -> None:
    logto = FakeLogto()
    logto.broken[WELL_KNOWN] = (200, "the bridge is down for maintenance")
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as refused:
            await discover(http, BRIDGE)
        assert "answered 200" in str(refused.value)
        assert "no JSON document" in str(refused.value)
        logto.broken[WELL_KNOWN] = (500, '{"status": "down"}')
        with pytest.raises(Unavailable) as status:
            await discover(http, BRIDGE)
        assert str(status.value) == "the bridge at https://bridge.test answered 500"
        logto.broken[WELL_KNOWN] = (503, '{"error": "maintenance"}')
        with pytest.raises(Unavailable) as named:
            await discover(http, BRIDGE)
        assert str(named.value) == "the bridge at https://bridge.test answered 503 (maintenance)"


async def test_an_id_token_that_is_no_token_or_names_no_account_is_refused(
    tmp_path: Path,
) -> None:
    for minted in (
        lambda: "not-a-token",
        lambda: an_id_token(),
        lambda: an_id_token(sub=ACCOUNT, kid="logto-99"),
    ):
        logto = FakeLogto()
        store = store_for(BRIDGE, tmp_path, None)
        async with httpx2.AsyncClient(transport=logto.transport) as http:
            config = await discover(http, BRIDGE)
            oidc = await provider(http, config.issuer)
            logto.overrides[TOKEN_PATH] = {
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 60,
                "id_token": minted(),
            }
            with pytest.raises(Unauthorised) as refused:
                await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "the ID token" in str(refused.value)
        assert store.load() is None


async def test_a_document_without_the_fields_a_sign_in_needs_is_refused() -> None:
    logto = FakeLogto()
    logto.overrides[WELL_KNOWN] = {"issuer": "https://auth.test/oidc"}
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Invalid) as refused:
            await discover(http, BRIDGE)
    assert "browser_client_id" in str(refused.value)
    logto = FakeLogto()
    logto.overrides[OPENID_PATH] = {**logto.openid(), "revocation_endpoint": None}
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        with pytest.raises(Unavailable) as hollow:
            await provider(http, "https://auth.test/oidc")
    assert "revocation_endpoint" in str(hollow.value)


async def test_a_grant_that_carries_no_refresh_token_or_lifetime_is_unavailable(
    tmp_path: Path,
) -> None:
    logto = FakeLogto()
    async with httpx2.AsyncClient(transport=logto.transport) as http:
        config = await discover(http, BRIDGE)
        oidc = await provider(http, config.issuer)
        logto.overrides[TOKEN_PATH] = {
            "access_token": "at",
            "expires_in": 60,
            "id_token": logto.mint(),
        }
        with pytest.raises(Unavailable) as refused:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "refresh_token" in str(refused.value)
        logto.overrides[TOKEN_PATH] = {
            "access_token": "at",
            "refresh_token": "rt",
            "id_token": logto.mint(),
        }
        with pytest.raises(Unavailable) as hollow:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "lifetime" in str(hollow.value)
        logto.overrides[TOKEN_PATH] = ["at", "rt"]
        with pytest.raises(Unavailable) as no_grant:
            await browser_sign_in(http, config, oidc, Browser(logto), wait=5)
        assert "with no grant" in str(no_grant.value)


def test_a_bridge_address_neither_https_nor_loopback_is_refused() -> None:
    for accepted in (
        "https://bridge.ecosemantic.com",
        "wss://bridge.ecosemantic.com/tunnel",
        "http://127.0.0.1:8000",
        "http://localhost:8000/api",
        "http://[::1]:9000",
        "ws://127.0.0.1:9000/tunnel",
    ):
        assert secure(accepted) == accepted
    for refused in (
        "http://bridge.example.com",
        "ws://bridge.example.com/tunnel",
        "http://192.0.2.10:9876/",
        "http://127.0.0.1.example.com",
        "/callback",
    ):
        with pytest.raises(Invalid) as refusal:
            secure(refused)
        assert refused in str(refusal.value)
    with pytest.raises(Invalid):
        secure("")


async def test_the_client_verifies_with_the_operating_system_s_trust_store() -> None:
    async with client() as made:
        assert made.timeout == httpx2.Timeout(30.0)
        context = made._transport._pool._ssl_context
        assert isinstance(context, truststore.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
