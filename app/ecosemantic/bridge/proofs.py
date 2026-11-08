"""The proof a bridged request carries, checked on the bridge's clock: the keys the tunnel's
welcome published and the offset between the two clocks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from ecosemantic.relay.errors import ProofRefused
from ecosemantic.relay.messages import Welcome, door_of
from ecosemantic.relay.proof import verify_proof


class ProofCheck:
    """Whether a bridged request's proof admits it. The check holds the bridge's keys and the
    offset between the bridge's clock and this machine's, both taken from the tunnel's welcome, and
    admits nothing before a welcome arrives: a proof is signed by a key only the welcome
    publishes."""

    def __init__(
        self,
        issuer: str,
        account: str,
        engine: UUID,
        clock: Callable[[], datetime],
    ) -> None:
        self._issuer = issuer
        self._account = account
        self._engine = engine
        self._clock = clock
        self._keys: list[dict[str, str]] | None = None
        self._offset = timedelta(0)

    def welcome(self, message: Welcome) -> None:
        """Take the keys the welcome publishes and the offset between the bridge's clock and this
        machine's, so every proof is judged at the moment the bridge minted it."""
        self._keys = list(message.keys)
        self._offset = message.now - self._clock()

    def __call__(self, proof: str, path: str) -> bool:
        """Whether the proof admits a request to the path: signed by one of the bridge's keys, for
        this account, this engine and the door the path belongs to, and unexpired on the bridge's
        clock."""
        keys = self._keys
        if keys is None:
            return False
        try:
            verify_proof(
                proof,
                keys,
                issuer=self._issuer,
                account=self._account,
                engine=self._engine,
                door=door_of(path),
                now=self._clock() + self._offset,
            )
        except ProofRefused:
            return False
        return True
