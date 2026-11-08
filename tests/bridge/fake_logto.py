"""The bridge's discovery document and Logto behind one transport, answering from memory and
recording what each request asked and sent, so a sign-in, a renewal and a sign-out reach no
network."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ecosemantic.relay.discovery import WELL_KNOWN
from ecosemantic.relay.proof import public_jwk

BRIDGE = "https://bridge.test"
AUTH = "https://auth.test"
ISSUER = f"{AUTH}/oidc"
ISSUER_PATH = urlsplit(ISSUER).path
OPENID_PATH = f"{ISSUER_PATH}/.well-known/openid-configuration"
AUTHORIZATION_PATH = f"{ISSUER_PATH}/auth"
TOKEN_PATH = f"{ISSUER_PATH}/token"
DEVICE_PATH = f"{ISSUER_PATH}/device"
REVOKE_PATH = f"{ISSUER_PATH}/revoke"
JWKS_PATH = f"{ISSUER_PATH}/jwks"
REGISTER_PATH = "/register"
TUNNEL_RESOURCE = f"{BRIDGE}/tunnel"
TUNNEL_SCOPE = "tunnel"
TUNNEL_URL = "wss://bridge.test/tunnel"
CONNECTOR_URL = f"{BRIDGE}/mcp"
BROWSER_CLIENT_ID = "the-engine-browser"
DEVICE_CLIENT_ID = "the-engine-device"
ACCOUNT = "account-1"
HANDLE = "carlos"
PAGE_URL = "https://carlos.bridge.test"
CODE = "the-code"
DEVICE_CODE = "the-device-code"
USER_CODE = "ABCD-EFGH"
VERIFICATION_URI = f"{AUTH}/device"
KID = "logto-1"
ALGORITHM = "ES384"
KEY = ec.derive_private_key(int.from_bytes(bytes(range(48)), "big"), ec.SECP384R1())
OTHER_KEY = ec.derive_private_key(int.from_bytes(bytes(range(48, 96)), "big"), ec.SECP384R1())
EDDSA_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CURVES = {256: "P-256", 384: "P-384", 521: "P-521"}

SigningKey = ec.EllipticCurvePrivateKey | Ed25519PrivateKey | rsa.RSAPrivateKey


def _coordinate(value: int, width: int) -> str:
    """A public key coordinate as a JWK carries it: base64url of its fixed-width bytes."""
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


def published(key: SigningKey, kid: str, algorithm: str) -> dict[str, str]:
    """The JWK this server publishes for a key it signs with, under the algorithm it signs it
    with."""
    if isinstance(key, rsa.RSAPrivateKey):
        numbers = key.public_key().public_numbers()
        return {
            "kty": "RSA",
            "n": _coordinate(numbers.n, (numbers.n.bit_length() + 7) // 8),
            "e": _coordinate(numbers.e, (numbers.e.bit_length() + 7) // 8),
            "kid": kid,
            "alg": algorithm,
            "use": "sig",
        }
    if isinstance(key, ec.EllipticCurvePrivateKey):
        numbers = key.public_key().public_numbers()
        width = (key.curve.key_size + 7) // 8
        return {
            "kty": "EC",
            "crv": CURVES[key.curve.key_size],
            "x": _coordinate(numbers.x, width),
            "y": _coordinate(numbers.y, width),
            "kid": kid,
            "alg": algorithm,
            "use": "sig",
        }
    return public_jwk(key.public_key(), kid)


def pkce_challenge(verifier: str) -> str:
    """The S256 challenge a verifier answers."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def form_of(request: httpx2.Request) -> dict[str, str]:
    """The fields of a form-encoded request, the last value of each name."""
    if not request.content:
        return {}
    decoded = parse_qs(request.content.decode("ascii"))
    return {name: values[-1] for name, values in decoded.items()}


def refused(error: str, description: str, status: int = 400) -> httpx2.Response:
    """An answer that names a refusal, as Logto's do."""
    return httpx2.Response(status, json={"error": error, "error_description": description})


class FakeLogto:
    """Logto's OpenID configuration, keys, token, device and revocation endpoints, and the bridge's
    discovery document and registration endpoint, beside the requests made to them."""

    def __init__(self, trace: list[str] | None = None) -> None:
        self.account = ACCOUNT
        self.expires_in = 3600
        self.interval: int | None = 5
        self.signing_key: SigningKey = KEY
        self.algorithm = ALGORITHM
        self.kid = KID
        self.jwk = published(KEY, KID, ALGORITHM)
        self.device_states: deque[str] = deque(["authorization_pending", "slow_down", "granted"])
        self.register_as: dict[str, Any] = {}
        self.overrides: dict[str, Any] = {}
        self.failures: set[str] = set()
        self.broken: dict[str, tuple[int, str]] = {}
        self.trace: list[str] = [] if trace is None else trace
        self.requests: list[httpx2.Request] = []
        self.forms: dict[str, list[dict[str, str]]] = {}
        self.authorized: dict[str, str] = {}
        self.registrations: list[dict[str, Any]] = []
        self.access_tokens: dict[str, str] = {}
        self.live_refresh: set[str] = set()
        self.revoked: list[str] = []
        self.minted = 0
        self.holding: asyncio.Event | None = None
        self.reached = asyncio.Event()

    @property
    def transport(self) -> httpx2.MockTransport:
        """The transport a client makes every request through."""
        return httpx2.MockTransport(self.answer)

    async def answer(self, request: httpx2.Request) -> httpx2.Response:
        """The answer this server gives one request, recorded first; answering a moment later, so a
        caller's awaits interleave as they do against a server on the network. A token request is
        answered at the rate `holding` allows, so a test can cancel a caller mid-renewal."""
        await asyncio.sleep(0)
        self.requests.append(request)
        path = request.url.path
        form = form_of(request)
        self.forms.setdefault(path, []).append(form)
        response = self._answer_for(path, form, request)
        if self.holding is not None and path == TOKEN_PATH:
            self.reached.set()
            await self.holding.wait()
        return response

    def _answer_for(
        self, path: str, form: Mapping[str, str], request: httpx2.Request
    ) -> httpx2.Response:
        if path in self.overrides:
            return httpx2.Response(200, json=self.overrides[path])
        if path in self.broken:
            status, body = self.broken[path]
            return httpx2.Response(status, text=body)
        if path in self.failures:
            return httpx2.Response(503)
        if path == WELL_KNOWN:
            return httpx2.Response(200, json=self.configuration())
        if path == OPENID_PATH:
            return httpx2.Response(200, json=self.openid())
        if path == JWKS_PATH:
            return httpx2.Response(200, json=self.jwks())
        if path == TOKEN_PATH:
            return self._token(form)
        if path == DEVICE_PATH:
            return self._device()
        if path == REVOKE_PATH:
            return self._revoke(form)
        if path == REGISTER_PATH:
            return self._registered(request)
        return refused("not_found", f"nothing answers {path}", status=404)

    def visited(self, authorization_url: str) -> None:
        """What a browser carried to the authorization endpoint, which is where the challenge the
        engine's token exchange answers comes from."""
        query = parse_qs(urlsplit(authorization_url).query)
        self.authorized = {name: values[-1] for name, values in query.items()}

    def configuration(self) -> dict[str, str]:
        """The bridge's discovery document."""
        return {
            "issuer": ISSUER,
            "browser_client_id": BROWSER_CLIENT_ID,
            "device_client_id": DEVICE_CLIENT_ID,
            "tunnel_resource": TUNNEL_RESOURCE,
            "tunnel_scope": TUNNEL_SCOPE,
            "tunnel_url": TUNNEL_URL,
            "connector_url": CONNECTOR_URL,
            "registration_url": f"{BRIDGE}{REGISTER_PATH}",
        }

    def openid(self) -> dict[str, str]:
        """Logto's OpenID configuration."""
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{AUTH}{AUTHORIZATION_PATH}",
            "token_endpoint": f"{AUTH}{TOKEN_PATH}",
            "device_authorization_endpoint": f"{AUTH}{DEVICE_PATH}",
            "revocation_endpoint": f"{AUTH}{REVOKE_PATH}",
            "jwks_uri": f"{AUTH}{JWKS_PATH}",
        }

    def jwks(self) -> dict[str, Any]:
        """The keys Logto publishes."""
        return {"keys": [self.jwk]}

    def signs_with(self, key: SigningKey, algorithm: str) -> None:
        """Sign ID tokens with this key and algorithm, and publish the key under it."""
        self.signing_key = key
        self.algorithm = algorithm
        self.jwk = published(key, self.kid, algorithm)

    def mint(
        self,
        client_id: str = BROWSER_CLIENT_ID,
        sub: str | None = None,
        issuer: str | None = None,
        key: SigningKey | None = None,
        algorithm: str | None = None,
    ) -> str:
        """An ID token this server signs."""
        now = int(datetime.now(UTC).timestamp())
        claims = {
            "iss": ISSUER if issuer is None else issuer,
            "sub": self.account if sub is None else sub,
            "aud": client_id,
            "iat": now,
            "exp": now + 300,
        }
        return jwt.encode(
            claims,
            self.signing_key if key is None else key,
            algorithm=self.algorithm if algorithm is None else algorithm,
            headers={"kid": self.kid},
        )

    def _token(self, form: Mapping[str, str]) -> httpx2.Response:
        grant = form.get("grant_type")
        if grant == "authorization_code":
            if form.get("code") != CODE:
                return refused("invalid_grant", "the code is not one this server issued")
            verifier = form.get("code_verifier", "")
            if self.authorized.get("code_challenge") != pkce_challenge(verifier):
                return refused("invalid_grant", "the verifier does not answer the challenge")
            consent = "consent" in self.authorized.get("prompt", "").split()
            asked = "offline_access" in self.authorized.get("scope", "").split()
            return self._granted(
                form.get("client_id", BROWSER_CLIENT_ID), offline=consent and asked
            )
        if grant == "refresh_token":
            presented = form.get("refresh_token", "")
            if presented not in self.live_refresh:
                return refused("invalid_grant", "the refresh token is dead")
            self.live_refresh.discard(presented)
            self.trace.append("refreshed")
            return self._granted(form.get("client_id", BROWSER_CLIENT_ID))
        if grant == "urn:ietf:params:oauth:grant-type:device_code":
            if form.get("device_code") != DEVICE_CODE:
                return refused("invalid_grant", "the device code is not one this server issued")
            state = self.device_states.popleft() if self.device_states else "granted"
            if state != "granted":
                return refused(state, "the device sign-in is not finished")
            return self._granted(DEVICE_CLIENT_ID)
        return refused("unsupported_grant_type", f"{grant} is no grant this server runs")

    def _granted(self, client_id: str, offline: bool = True) -> httpx2.Response:
        """The tokens of one grant, a refresh token beside them only while the grant keeps
        `offline_access`, as Logto issues one."""
        self.minted += 1
        access = f"at-{self.minted}"
        refresh = f"rt-{self.minted}"
        self.access_tokens[access] = self.account
        scope = f"openid offline_access {TUNNEL_SCOPE}" if offline else f"openid {TUNNEL_SCOPE}"
        body: dict[str, Any] = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "scope": scope,
            "id_token": self.mint(client_id),
        }
        if offline:
            self.live_refresh.add(refresh)
            body["refresh_token"] = refresh
        return httpx2.Response(200, json=body)

    def _device(self) -> httpx2.Response:
        body: dict[str, Any] = {
            "device_code": DEVICE_CODE,
            "user_code": USER_CODE,
            "verification_uri": VERIFICATION_URI,
            "verification_uri_complete": f"{VERIFICATION_URI}?user_code={USER_CODE}",
            "expires_in": 300,
        }
        if self.interval is not None:
            body["interval"] = self.interval
        return httpx2.Response(200, json=body)

    def _revoke(self, form: Mapping[str, str]) -> httpx2.Response:
        """Revoke the grant a refresh token belongs to."""
        token = form.get("token", "")
        self.revoked.append(token)
        self.live_refresh.discard(token)
        return httpx2.Response(200)

    def _registered(self, request: httpx2.Request) -> httpx2.Response:
        bearer = request.headers.get("authorization", "")
        account = self.access_tokens.get(bearer.removeprefix("Bearer "))
        if account is None:
            return refused("invalid_token", "no such access token", status=401)
        held = json.loads(request.content.decode("utf-8"))
        self.registrations.append(held)
        answer: dict[str, Any] = {
            "engine": held["engine"] or str(uuid4()),
            "account": account,
            "handle": HANDLE,
            "page_url": PAGE_URL,
        }
        answer.update(self.register_as)
        return httpx2.Response(200, json=answer)
