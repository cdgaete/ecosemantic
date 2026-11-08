"""The token a tunnel opens with: the interactive credential renewed with its rotating refresh token
and saved before it is answered, or the engine token an unattended server carries instead."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import httpx2

from ecosemantic.bridge.credentials import Credential, CredentialStore
from ecosemantic.bridge.signin import OpenIdProvider, SignedOut, Tokens, refresh
from ecosemantic.errors import Unauthorised
from ecosemantic.relay.discovery import BridgeConfiguration

RENEW_BEFORE = timedelta(seconds=60)
SIGNED_IN_AGAIN = "this systems directory was signed in again; this server's bridge stops"
SIGNED_OUT = "this systems directory was signed out; this server's bridge stops"
ENGINE_REFUSED = (
    "the bridge refused this engine's engine token; the bridge's account page issues a new one"
)


class Session(Protocol):
    """What a tunnel asks for the token it opens with, and for a fresh one when the bridge refuses
    the held."""

    async def access_token(self, force: bool = False) -> str: ...


@dataclass(frozen=True)
class EngineTokenSession:
    """The engine token an unattended server reads from its environment, which carries nothing to
    renew it with: a tunnel that refuses it stops this server's bridge and names the page that
    issues another."""

    token: str

    async def access_token(self, force: bool = False) -> str:
        """The token, unless a renewal is forced: an engine token has nothing to renew it with, so
        the bridge's refusal of it ends the bridge."""
        if force:
            raise Unauthorised(ENGINE_REFUSED)
        return self.token


class TunnelSession:
    """The interactive credential's tunnel access token, renewed with its rotating refresh token,
    which is saved to the store before the token that came with it is answered."""

    def __init__(
        self,
        http: httpx2.AsyncClient,
        config: BridgeConfiguration,
        oidc: OpenIdProvider,
        store: CredentialStore,
        credential: Credential,
        clock: Callable[[], datetime],
    ) -> None:
        self._http = http
        self._config = config
        self._oidc = oidc
        self._store = store
        self._credential = credential
        self._clock = clock
        self._held: Tokens | None = None
        self._renewing = asyncio.Lock()

    async def access_token(self, force: bool = False) -> str:
        """A token that lives at least the next minute: renewed when none is held, when a renewal is
        forced, or when the held one is nearly out. The renewal runs shielded from the caller's
        cancellation, so a rotated refresh token reaches the store whatever the caller does, and
        callers that renew at once share one renewal, since two renewals of one rotating refresh
        token would revoke the grant."""
        held = self._live(force)
        if held is not None:
            return held
        return await asyncio.shield(self._renewal(force))

    async def _renewal(self, force: bool) -> str:
        """The one renewal this systems directory runs at a time, under the lock a cancelled caller
        keeps until the save is done."""
        async with self._renewing:
            held = self._live(force)
            if held is not None:
                return held
            return await self._renewed()

    def _live(self, force: bool) -> str | None:
        """The token held now, when it lives beyond the margin and no renewal is forced."""
        held = self._held
        if held is None or force or held.expires_at - self._clock() <= RENEW_BEFORE:
            return None
        return held.access_token

    async def confirmed(self, handle: str, page_url: str) -> Credential:
        """The credential the bridge's registration answers the handle and page address of now,
        saved when either changed, so the address this server announces is the one that answers. It
        refuses as signed out when the store holds none, and as signed in again when the store holds
        another engine's credential. The reload, the check and the save run under the renewal's
        lock, so a renewal's rotated refresh token is never overwritten by the save."""
        async with self._renewing:
            held = self._stored()
            if held.handle == handle and held.page_url == page_url:
                return held
            self._credential = held.model_copy(update={"handle": handle, "page_url": page_url})
            self._store.save(self._credential)
            return self._credential

    def _stored(self) -> Credential:
        """The credential this systems directory keeps now, which is the one the store holds: a
        credential signed in or out since this session loaded it stops this server's bridge."""
        stored = self._store.load()
        if stored is None:
            raise SignedOut(SIGNED_OUT)
        if stored.engine != self._credential.engine:
            raise Unauthorised(SIGNED_IN_AGAIN)
        return stored

    async def _renewed(self) -> str:
        """A token from a renewal of the credential the store keeps now, saved before it is
        answered."""
        stored = self._stored()
        try:
            tokens = await refresh(self._http, self._oidc, self._config, stored)
        except SignedOut:
            self._store.delete()
            raise
        self._credential = stored.model_copy(update={"refresh_token": tokens.refresh_token})
        self._store.save(self._credential)
        self._held = tokens
        return tokens.access_token
