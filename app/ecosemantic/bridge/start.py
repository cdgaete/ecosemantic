"""Starting the bridge: the discovery document a start reads, the registration an engine token
buys, the credential the store keeps, and the sign-in a terminal makes when it holds none."""

from __future__ import annotations

import importlib.metadata
import socket
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx2

from ecosemantic.bridge.credentials import Credential, CredentialStore, engine_token, store_for
from ecosemantic.bridge.proofs import ProofCheck
from ecosemantic.bridge.session import EngineTokenSession, Session, TunnelSession
from ecosemantic.bridge.signin import client, discover, provider, register, sign_in
from ecosemantic.errors import Unauthorised, Unavailable
from ecosemantic.relay.discovery import BridgeConfiguration, Registration
from ecosemantic.settings import browser_reachable

DEFAULT_BRIDGE_URL = "https://bridge.ecosemantic.com"


@dataclass(frozen=True)
class BridgeStart:
    """What a start learned: the bridge's document, the session the tunnel opens with, and the
    engine, account, handle and page address the server announces and admits proofs for."""

    config: BridgeConfiguration
    session: Session
    engine: UUID
    account: str
    handle: str
    page_url: str
    check: ProofCheck


def engine_name() -> str:
    """The name this engine registers with the bridge, which is this machine's."""
    return socket.gethostname()


def engine_version() -> str:
    """The version this engine registers and opens its tunnel with."""
    return importlib.metadata.version("ecosemantic")


def now() -> datetime:
    """This machine's clock."""
    return datetime.now(UTC)


async def bridge_start(
    bridge_url: str,
    systems_dir: Path,
    credential_file: Path | None,
    environ: Mapping[str, str],
    interactive: bool,
    opener: Callable[[str], None],
    show: Callable[[str, str], None],
) -> BridgeStart:
    """This engine's start on the bridge: the registration its engine token buys, or the stored
    credential, or a sign-in when a person is at a terminal to finish one."""
    token = engine_token(environ)
    if token is not None:
        return await _by_token(token, bridge_url)
    store = store_for(bridge_url, systems_dir, credential_file)
    credential = store.load()
    if credential is None and not interactive:
        raise Unavailable(
            "this engine is not signed in to the bridge",
            hint="run ecosemantic bridge sign-in",
        )
    return await _by_credential(store, credential, bridge_url, environ, opener, show)


async def _by_token(token: str, bridge_url: str) -> BridgeStart:
    """The start an engine token buys: the engine registered by that token, which never signs in
    and never renews."""
    async with client() as http:
        config = await discover(http, bridge_url)
        registered = await register(
            http,
            config,
            token,
            Registration(engine=None, name=engine_name(), version=engine_version()),
        )
    return BridgeStart(
        config=config,
        session=EngineTokenSession(token),
        engine=registered.engine,
        account=registered.account,
        handle=registered.handle,
        page_url=registered.page_url,
        check=_check(bridge_url, registered.account, registered.engine),
    )


async def _by_credential(
    store: CredentialStore,
    credential: Credential | None,
    bridge_url: str,
    environ: Mapping[str, str],
    opener: Callable[[str], None],
    show: Callable[[str, str], None],
) -> BridgeStart:
    """The start a stored credential buys, signing this systems directory in first when the store
    holds none and registering the engine the credential names with the bridge, so a changed handle
    takes effect here. A sign-in is the device flow where this machine can show no browser. The
    session renews the token through the client opened here, so the client is left open with it."""
    http = client()
    config = await discover(http, bridge_url)
    stored = credential is not None
    if credential is None:
        credential = await sign_in(
            http,
            bridge_url,
            store,
            not browser_reachable(environ, sys.platform),
            engine_name(),
            engine_version(),
            opener,
            show,
        )
    oidc = await provider(http, config.issuer)
    session = TunnelSession(http, config, oidc, store, credential, now)
    if stored:
        credential = await _registered(http, config, session, credential)
    return BridgeStart(
        config=config,
        session=session,
        engine=credential.engine,
        account=credential.account,
        handle=credential.handle,
        page_url=credential.page_url,
        check=_check(bridge_url, credential.account, credential.engine),
    )


async def _registered(
    http: httpx2.AsyncClient,
    config: BridgeConfiguration,
    session: TunnelSession,
    credential: Credential,
) -> Credential:
    """The credential as the bridge registers the engine this start, refused when the answer names
    another engine or another account than the ones it was registered with."""
    registered = await register(
        http,
        config,
        await session.access_token(),
        Registration(engine=credential.engine, name=engine_name(), version=engine_version()),
    )
    if registered.engine != credential.engine or registered.account != credential.account:
        raise Unauthorised(
            f"the bridge registered the engine {registered.engine} for {registered.account!r}, "
            f"not {credential.engine} for {credential.account!r}"
        )
    return await session.confirmed(registered.handle, registered.page_url)


def _check(bridge_url: str, account: str, engine: UUID) -> ProofCheck:
    """The gate every bridged request is judged by: the bridge's address without a trailing slash,
    this account, this engine and this machine's clock."""
    return ProofCheck(bridge_url.rstrip("/"), account, engine, now)
