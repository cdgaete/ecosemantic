"""How a request reached the engine, read from its ASGI scope."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ecosemantic.mcp.accounts import Reach

BRIDGE_EXTENSION = "ecosemantic.bridge"
LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1"})
FORWARDING_PREFIXES = (b"x-forwarded-", b"cf-", b"tailscale-")
FORWARDING_HEADERS = frozenset(
    {
        b"forwarded",
        b"via",
        b"x-original-forwarded-for",
        b"x-real-ip",
        b"x-client-ip",
        b"true-client-ip",
    }
)


def reach(scope: Mapping[str, object]) -> Reach:
    """How a request reached the engine: through the bridge when its scope carries the bridge's
    extension, on this computer from a loopback peer that forwards for nobody, and across the
    network otherwise. A proxy or a tunnel on this computer is a loopback peer, so the headers
    one adds say the request came from elsewhere."""
    extensions = scope.get("extensions")
    if isinstance(extensions, Mapping) and BRIDGE_EXTENSION in extensions:
        return "bridge"
    client = scope.get("client")
    peer = client[0] if isinstance(client, tuple | list) and client else ""
    if peer not in LOOPBACK_PEERS or _forwarded(scope.get("headers")):
        return "network"
    return "here"


def _forwarded(headers: object) -> bool:
    """Whether a request's headers hold one a proxy adds for the caller it forwards."""
    if not isinstance(headers, Iterable):
        return False
    names = (held[0] for held in headers if isinstance(held, tuple | list))
    return any(name in FORWARDING_HEADERS or name.startswith(FORWARDING_PREFIXES) for name in names)
