"""Signing this systems directory's engine in to the bridge through Logto: the browser with a
loopback redirect or the device flow, the registration that names the engine, and the renewal of its
tunnel access token with a rotating refresh token."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import ssl
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx2
import jwt
import truststore
from pydantic import ValidationError

from ecosemantic.bridge.credentials import Credential, CredentialStore
from ecosemantic.errors import Invalid, Unauthorised, Unavailable, field_error
from ecosemantic.relay.discovery import WELL_KNOWN, BridgeConfiguration, Registered, Registration

VERIFIED_ALGORITHMS = frozenset(
    {
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
    }
)
IMPLIED_ALGORITHMS = {
    "EC": {"P-256": "ES256", "P-384": "ES384", "P-521": "ES512"},
    "OKP": {"Ed25519": "EdDSA"},
}
LOOPBACK = "127.0.0.1"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
SECURE_SCHEMES = frozenset({"https", "wss"})
LOOPBACK_SCHEMES = frozenset({"http", "ws"})
CALLBACK_PATH = "/callback"
CALLBACK_METHOD = "GET"
NOT_FOUND = b"HTTP/1.1 404 Not Found\r\ncontent-length: 0\r\nconnection: close\r\n\r\n"
SIGNED_IN_PAGE = "Signed in to the EcoSemantic bridge. You can close this tab."
ENGINE_SIGNED_OUT = "the bridge signed this engine out; run ecosemantic bridge sign-in"
SIGN_IN_REFUSED = "the sign-in was not finished within 5 minutes"
CREDENTIAL_KEPT = (
    "the credential is kept: run ecosemantic bridge sign-out again once the bridge answers, or "
    "revoke the engine on the bridge's account page"
)
TIMEOUT = 30.0
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
DEFAULT_INTERVAL = 5.0
SLOW_DOWN_STEP = 5.0
GRANT = "Logto's grant"
UNAUTHORISED_STATUSES = frozenset({401, 403})
VERIFIER_BYTES = 48


class SignedOut(Unauthorised):
    """This engine has no usable credential: Logto refused its refresh token and revoked the grant
    with it, or the store holds none for it, so the person signs in again."""


@dataclass(frozen=True)
class OpenIdProvider:
    """Logto's endpoints, and the address the keys it signs with are published at."""

    authorization_endpoint: str
    token_endpoint: str
    device_authorization_endpoint: str
    revocation_endpoint: str
    jwks_uri: str


@dataclass(frozen=True)
class Tokens:
    """What a sign-in grants: the tunnel's access token, the refresh token that renews it, when it
    expires and the account it names."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    account: str


@dataclass(frozen=True)
class SigningKey:
    """The key a JWKS publishes under an ID token's `kid`, and the asymmetric algorithm it signs
    with."""

    key: jwt.PyJWK
    algorithm: str


def secure(url: str) -> str:
    """The address, refused unless it is https or wss, or http or ws to this machine's loopback."""
    held = urlsplit(url)
    if held.scheme in SECURE_SCHEMES:
        return url
    if held.scheme in LOOPBACK_SCHEMES and held.hostname in LOOPBACK_HOSTS:
        return url
    raise Invalid(
        f"{url!r} is neither https nor a loopback address; the bridge's addresses are https"
    )


def client() -> httpx2.AsyncClient:
    """The client a sign-in makes its requests with: the operating system's trust store, and a
    30-second timeout."""
    return httpx2.AsyncClient(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=TIMEOUT
    )


async def discover(http: httpx2.AsyncClient, bridge_url: str) -> BridgeConfiguration:
    """The bridge's discovery document, each address it publishes refused unless it is https or
    loopback."""
    where = _address(bridge_url)
    what = f"the bridge at {where}"
    document = _document(await _reached(http.get(f"{where}{WELL_KNOWN}"), what), what)
    try:
        config = BridgeConfiguration.model_validate(document)
    except ValidationError as error:
        raise Invalid(
            f"{where} does not publish the bridge's discovery document: {field_error(error)}"
        ) from error
    for address in (
        config.issuer,
        config.tunnel_url,
        config.connector_url,
        config.registration_url,
    ):
        secure(address)
    return config


async def provider(http: httpx2.AsyncClient, issuer: str) -> OpenIdProvider:
    """Logto's endpoints, from the OpenID configuration at the issuer's well-known address."""
    where = _address(issuer)
    document = _document(
        await _reached(http.get(f"{where}/.well-known/openid-configuration"), f"Logto at {where}"),
        f"Logto at {where}",
    )
    return OpenIdProvider(
        authorization_endpoint=secure(_named(document, "authorization_endpoint", where)),
        token_endpoint=secure(_named(document, "token_endpoint", where)),
        device_authorization_endpoint=secure(
            _named(document, "device_authorization_endpoint", where)
        ),
        revocation_endpoint=secure(_named(document, "revocation_endpoint", where)),
        jwks_uri=secure(_named(document, "jwks_uri", where)),
    )


async def browser_sign_in(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    oidc: OpenIdProvider,
    opener: Callable[[str], None],
    wait: float = 300,
) -> Tokens:
    """The tokens a browser sign-in grants: PKCE with a 64-character verifier, the browser's one
    request answered on a loopback listener, and its code exchanged for the tunnel's tokens."""
    verifier = secrets.token_urlsafe(VERIFIER_BYTES)
    state = secrets.token_urlsafe(16)
    answered: asyncio.Future[dict[str, str]] = asyncio.get_running_loop().create_future()
    server = await asyncio.start_server(_one_callback(answered), host=LOOPBACK, port=0)
    try:
        port = server.sockets[0].getsockname()[1]
        redirect_uri = f"http://{LOOPBACK}:{port}{CALLBACK_PATH}"
        opener(_authorization_url(config, oidc, redirect_uri, state, _challenge(verifier)))
        query = await _answered(answered, wait)
        refused = query.get("error")
        if refused is not None:
            raise Unauthorised(f"Logto refused the sign-in: {refused}")
        if query.get("state") != state:
            raise Unauthorised("the callback answers another sign-in; nothing was signed in")
        code = query.get("code")
        if code is None:
            raise Unauthorised("the sign-in's callback carried no code")
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config.browser_client_id,
            "code_verifier": verifier,
            "resource": config.tunnel_resource,
        }
        try:
            body = await _grant_body(http, oidc.token_endpoint, form)
        except _Refused as refusal:
            raise Unauthorised(_refusal_message(refusal, "the sign-in")) from refusal
        return await _signed_in(http, config, oidc, body, config.browser_client_id)
    finally:
        server.close()
        await server.wait_closed()


async def device_sign_in(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    oidc: OpenIdProvider,
    show: Callable[[str, str], None],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Tokens:
    """The tokens a device sign-in grants: the code the person is shown, then the poll the device
    flow runs until the provider grants them."""
    held = _document(
        await _reached(
            http.post(
                oidc.device_authorization_endpoint,
                data={
                    "client_id": config.device_client_id,
                    "scope": _scope(config),
                    "resource": config.tunnel_resource,
                },
            ),
            f"Logto at {oidc.device_authorization_endpoint}",
        ),
        f"Logto at {oidc.device_authorization_endpoint}",
    )
    where = "Logto's device authorization"
    device_code = _named(held, "device_code", where)
    show(_named(held, "user_code", where), _named(held, "verification_uri_complete", where))
    interval = held.get("interval")
    waits = DEFAULT_INTERVAL if not isinstance(interval, int) else float(interval)
    while True:
        await sleep(waits)
        try:
            body = await _grant_body(
                http,
                oidc.token_endpoint,
                {
                    "grant_type": DEVICE_GRANT,
                    "device_code": device_code,
                    "client_id": config.device_client_id,
                    "resource": config.tunnel_resource,
                },
            )
        except _Refused as refusal:
            if refusal.error == "authorization_pending":
                continue
            if refusal.error == "slow_down":
                waits += SLOW_DOWN_STEP
                continue
            raise Unauthorised(_refusal_message(refusal, "the device sign-in")) from refusal
        return await _signed_in(http, config, oidc, body, config.device_client_id)


async def register(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    access_token: str,
    registration: Registration,
) -> Registered:
    """The engine as the bridge registers it: its id, its account, its handle and its page."""
    where = secure(config.registration_url)
    answered = await _reached(
        http.post(
            where,
            json=registration.model_dump(mode="json"),
            headers={"authorization": f"Bearer {access_token}"},
        ),
        f"the bridge at {where}",
    )
    return Registered.model_validate(
        _document(answered, f"the bridge at {where}", unauthorised=UNAUTHORISED_STATUSES)
    )


async def refresh(
    http: httpx2.AsyncClient,
    oidc: OpenIdProvider,
    config: BridgeConfiguration,
    credential: Credential,
) -> Tokens:
    """The tokens the credential's refresh token buys, the one that replaces it carried along."""
    try:
        body = await _grant_body(
            http,
            oidc.token_endpoint,
            {
                "grant_type": "refresh_token",
                "refresh_token": credential.refresh_token,
                "client_id": credential.client_id,
                "resource": config.tunnel_resource,
            },
        )
    except _Refused as refusal:
        if refusal.error == "invalid_grant":
            raise SignedOut(ENGINE_SIGNED_OUT) from refusal
        raise Invalid(_refusal_message(refusal, "the renewal")) from refusal
    return _tokens_granted(body, credential.account)


async def revoke(http: httpx2.AsyncClient, oidc: OpenIdProvider, credential: Credential) -> None:
    """Have Logto revoke the credential's refresh token, and the grant that carries it."""
    response = await _reached(
        http.post(
            oidc.revocation_endpoint,
            data={
                "token": credential.refresh_token,
                "token_type_hint": "refresh_token",
                "client_id": credential.client_id,
            },
        ),
        f"Logto at {oidc.revocation_endpoint}",
    )
    if not response.is_success:
        raise Unavailable(f"Logto answered {response.status_code} to the revocation")


async def sign_in(
    http: httpx2.AsyncClient,
    bridge_url: str,
    store: CredentialStore,
    device: bool,
    name: str,
    version: str,
    opener: Callable[[str], None],
    show: Callable[[str, str], None],
) -> Credential:
    """Sign this systems directory's engine in, register it with the bridge and keep it: a new
    engine id, and the handle and page address the bridge answers the registration with."""
    config = await discover(http, bridge_url)
    oidc = await provider(http, config.issuer)
    if device:
        tokens = await device_sign_in(http, config, oidc, show)
        client_id = config.device_client_id
    else:
        tokens = await browser_sign_in(http, config, oidc, opener)
        client_id = config.browser_client_id
    engine = uuid4()
    registered = await register(
        http,
        config,
        tokens.access_token,
        Registration(engine=engine, name=name, version=version),
    )
    if registered.engine != engine or registered.account != tokens.account:
        raise Unauthorised(
            f"the bridge registered the engine {registered.engine} for {registered.account!r}, "
            f"not {engine} for {tokens.account!r}"
        )
    credential = Credential(
        bridge_url=_address(bridge_url),
        client_id=client_id,
        engine=registered.engine,
        account=registered.account,
        handle=registered.handle,
        page_url=secure(registered.page_url),
        refresh_token=tokens.refresh_token,
    )
    store.save(credential)
    return credential


async def sign_out(http: httpx2.AsyncClient, store: CredentialStore) -> Credential | None:
    """Revoke the credential's refresh token at the bridge's Logto, forget the credential, and
    answer the credential revoked, or None when the store holds none. A revocation that does not
    happen leaves the credential stored and travels as the refusal it is."""
    credential = store.load()
    if credential is None:
        return None
    await _revoked(http, credential)
    store.delete()
    return credential


async def _revoked(http: httpx2.AsyncClient, credential: Credential) -> None:
    """Have Logto revoke the credential's refresh token and the grant that carries it, at the
    endpoints the bridge's discovery document and Logto's own name."""
    config = await discover(http, credential.bridge_url)
    oidc = await provider(http, config.issuer)
    await revoke(http, oidc, credential)


def _address(url: str) -> str:
    """An address the bridge or its authorization server answers at, without a trailing slash."""
    return secure(url).rstrip("/")


def _scope(config: BridgeConfiguration) -> str:
    """The scopes an engine asks for: the account it signs in as, and the tunnel it may open."""
    return f"openid offline_access {config.tunnel_scope}"


def _authorization_url(
    config: BridgeConfiguration,
    oidc: OpenIdProvider,
    redirect_uri: str,
    state: str,
    challenge: str,
) -> str:
    """The address the browser is opened at: the code flow with PKCE, for the tunnel's resource and
    the scopes the engine needs."""
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.browser_client_id,
            "redirect_uri": redirect_uri,
            "scope": _scope(config),
            "resource": config.tunnel_resource,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{oidc.authorization_endpoint}?{query}"


def _challenge(verifier: str) -> str:
    """The S256 challenge a PKCE verifier answers."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _one_callback(
    answered: asyncio.Future[dict[str, str]],
) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]:
    """The listener's handler: answer a `GET /callback` with the page and hand the query it carried
    to the sign-in, and answer any other request 404 so the sign-in keeps waiting."""
    page = SIGNED_IN_PAGE.encode("utf-8")
    header = (
        b"HTTP/1.1 200 OK\r\n"
        b"content-type: text/plain; charset=utf-8\r\n"
        b"content-length: " + str(len(page)).encode("ascii") + b"\r\n"
        b"connection: close\r\n\r\n"
    )

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        parts = line.split(b" ")
        method = parts[0].decode("ascii", "replace") if parts else ""
        target = parts[1].decode("ascii", "replace") if len(parts) > 1 else ""
        callback = method == CALLBACK_METHOD and urlsplit(target).path == CALLBACK_PATH
        writer.write(header + page if callback else NOT_FOUND)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        if callback and not answered.done():
            query = parse_qs(urlsplit(target).query)
            answered.set_result({name: values[-1] for name, values in query.items()})

    return answer


async def _answered(answered: asyncio.Future[dict[str, str]], wait: float) -> dict[str, str]:
    """What the browser's one request carried, refused when none arrives within `wait` seconds."""
    try:
        return await asyncio.wait_for(answered, wait)
    except TimeoutError as expired:
        raise Unavailable(SIGN_IN_REFUSED) from expired


async def _signed_in(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    oidc: OpenIdProvider,
    body: Mapping[str, Any],
    client_id: str,
) -> Tokens:
    """The tokens a granted sign-in answer carries, the account its ID token names among them."""
    account = await _account(http, config, oidc, _named(body, "id_token", GRANT), client_id)
    return _tokens_granted(body, account)


def _tokens_granted(body: Mapping[str, Any], account: str) -> Tokens:
    """The tokens a granted answer carries, and the lifetime they are given."""
    lifetime = body.get("expires_in")
    if not isinstance(lifetime, int) or isinstance(lifetime, bool):
        raise Unavailable("Logto granted no lifetime")
    return Tokens(
        access_token=_named(body, "access_token", GRANT),
        refresh_token=_named(body, "refresh_token", GRANT),
        expires_at=datetime.now(UTC) + timedelta(seconds=lifetime),
        account=account,
    )


async def _account(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    oidc: OpenIdProvider,
    id_token: str,
    client_id: str,
) -> str:
    """The account an ID token names, once the key Logto publishes under its `kid` verifies it with
    the algorithm that key signs with, and the issuer and the audience are this sign-in's."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as error:
        raise _untrusted(f"it cannot be read ({error})") from error
    kid = header.get("kid")
    signing = await _key(http, oidc.jwks_uri, kid)
    named = header.get("alg")
    if named != signing.algorithm:
        raise _untrusted(
            f"it says it is signed with {named!r} and the key {kid!r} it names signs with "
            f"{signing.algorithm}"
        )
    try:
        claims = jwt.decode(
            id_token,
            key=signing.key,
            algorithms=[signing.algorithm],
            audience=client_id,
            issuer=config.issuer,
        )
    except jwt.PyJWTError as error:
        raise _untrusted(f"no key Logto publishes verifies it ({error})") from error
    account = claims.get("sub")
    if not isinstance(account, str) or not account:
        raise _untrusted("it names no account")
    return account


async def _key(http: httpx2.AsyncClient, jwks_uri: str, kid: object) -> SigningKey:
    """The key an ID token names, of the keys Logto publishes, with the algorithm it signs with."""
    held = _document(
        await _reached(http.get(secure(jwks_uri)), f"Logto at {jwks_uri}"), f"Logto at {jwks_uri}"
    )
    keys = held.get("keys") if isinstance(held, Mapping) else None
    for entry in keys if isinstance(keys, list) else []:
        if isinstance(entry, Mapping) and entry.get("kid") == kid:
            return _signing_key(entry, kid)
    raise _untrusted(f"it is signed with the key {kid!r}, which Logto does not publish")


def _signing_key(entry: Mapping[str, Any], kid: object) -> SigningKey:
    """The key a JWKS publishes, read for the algorithm it signs with."""
    algorithm = _algorithm(entry, kid)
    try:
        return SigningKey(key=jwt.PyJWK(dict(entry), algorithm=algorithm), algorithm=algorithm)
    except jwt.PyJWTError as error:
        raise _untrusted(
            f"the key {kid!r} is no key this sign-in can verify with ({error})"
        ) from error


def _algorithm(entry: Mapping[str, Any], kid: object) -> str:
    """The asymmetric algorithm a JWKS key signs with: the one it names, or the one its type and
    curve imply where they imply only one."""
    named = entry.get("alg")
    if named is not None:
        if isinstance(named, str) and named in VERIFIED_ALGORITHMS:
            return named
        raise _untrusted(
            f"the key {kid!r} names the algorithm {named!r}, which is no algorithm this sign-in "
            "verifies"
        )
    kind = entry.get("kty")
    curve = entry.get("crv")
    implied = IMPLIED_ALGORITHMS.get(kind) if isinstance(kind, str) else None
    algorithm = implied.get(curve) if implied is not None and isinstance(curve, str) else None
    if algorithm is None:
        raise _untrusted(
            f"the key {kid!r} names no algorithm, and its type {kind!r} and curve {curve!r} "
            "imply none this sign-in verifies"
        )
    return algorithm


class _Refused(Exception):
    """The error Logto named in a refused answer, and what it said about it."""

    def __init__(self, error: str, description: str) -> None:
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}" if description else error)


async def _grant_body(
    http: httpx2.AsyncClient,
    endpoint: str,
    form: Mapping[str, str],
) -> Mapping[str, Any]:
    """The body of a granted answer, a refusal Logto names raised as `_Refused` and any other answer
    as unavailable."""
    response = await _reached(http.post(endpoint, data=dict(form)), f"Logto at {endpoint}")
    held = _json(response, f"Logto at {endpoint}")
    named = held.get("error") if isinstance(held, Mapping) else None
    if isinstance(named, str):
        description = held.get("error_description")
        raise _Refused(named, description if isinstance(description, str) else "")
    if not response.is_success:
        raise Unavailable(_failed_answer(response, held, f"Logto at {endpoint}"))
    if not isinstance(held, Mapping):
        raise Unavailable(f"Logto at {endpoint} answered {response.status_code} with no grant")
    return held


async def _reached(send: Awaitable[httpx2.Response], what: str) -> httpx2.Response:
    """The answer to a request, a failure to reach the address at all refused as unavailable, naming
    what was being reached and what failed."""
    try:
        return await send
    except httpx2.HTTPError as failure:
        raise Unavailable(f"{what} could not be reached: {failure}") from failure


def _refusal_message(refusal: _Refused, what: str) -> str:
    """The sentence a refusal is read as, naming what was refused and what Logto said of it."""
    said = f" ({refusal.description})" if refusal.description else ""
    return f"Logto refused {what}: {refusal.error}{said}"


def _json(response: httpx2.Response, what: str) -> Any:
    """The JSON document a body carries, refused as `Unavailable` when it carries none."""
    try:
        return response.json()
    except ValueError as error:
        raise Unavailable(
            f"{what} answered {response.status_code} with no JSON document"
        ) from error


def _failed_answer(response: httpx2.Response, held: object, what: str) -> str:
    """The sentence a failed answer is read as: what answered, with what status, and the error the
    body names when it names one."""
    named = held.get("error") if isinstance(held, Mapping) else None
    said = f" ({named})" if isinstance(named, str) else ""
    return f"{what} answered {response.status_code}{said}"


def _document(
    response: httpx2.Response, what: str, unauthorised: frozenset[int] = frozenset()
) -> Any:
    """The JSON document an answer carries. A status that is no success is refused naming what
    answered, its status and the error the body names when it names one: `Unauthorised` for a status
    `unauthorised` names, `Unavailable` for every other."""
    held = _json(response, what)
    if response.is_success:
        return held
    said = _failed_answer(response, held, what)
    if response.status_code in unauthorised:
        raise Unauthorised(said)
    raise Unavailable(said)


def _untrusted(why: str) -> Unauthorised:
    """The ID token a sign-in will not trust, and why."""
    return Unauthorised(f"the ID token is not one this sign-in can trust: {why}")


def _named(document: object, name: str, where: str) -> str:
    """The string a document holds under `name`, refused when it holds none."""
    held = document.get(name) if isinstance(document, Mapping) else None
    if not isinstance(held, str) or not held:
        raise Unavailable(f"{where} names no {name}")
    return held
