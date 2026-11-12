"""The secret a caller sends compared with the one held: whether the two are the same string,
compared as UTF-8 bytes in constant time, and false for anything that is no string at all.
"""

from __future__ import annotations

import hmac


def secret_matches(sent: object, held: str) -> bool:
    """Whether the value sent is the secret held, compared as UTF-8 bytes in constant time."""
    if not isinstance(sent, str):
        return False
    return hmac.compare_digest(sent.encode("utf-8"), held.encode("utf-8"))
