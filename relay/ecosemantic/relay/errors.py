"""The relay's typed errors: text, a frame or a proof it cannot accept."""

from __future__ import annotations


class RelayError(ValueError):
    """The tunnel carries something the protocol does not define, or not the thing it defines."""


class ProofRefused(RelayError):
    """A bridged request's proof does not admit the request; the message names the fault."""
