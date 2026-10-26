"""A bounded retry for a file Windows refuses to replace or read while another handle holds it.

Replacing a file another handle has open, and opening a file another process is replacing, are
both refused on Windows where Linux allows them. Each operation is retried `REPLACE_ATTEMPTS`
times, `REPLACE_WAIT_SECONDS` apart, and once the bound is spent the caller is answered with an
`Unavailable` naming the file and that another process holds it.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from ecosemantic.errors import Unavailable

REPLACE_ATTEMPTS = 40
REPLACE_WAIT_SECONDS = 0.01

T = TypeVar("T")


def _retry(operation: Callable[[], T], *, unavailable: str) -> T:
    """Run `operation`, retrying a `PermissionError` up to `REPLACE_ATTEMPTS` times and answering
    `Unavailable` once the bound is spent, chained from the last attempt's `PermissionError`."""
    for _ in range(REPLACE_ATTEMPTS - 1):
        try:
            return operation()
        except PermissionError:
            time.sleep(REPLACE_WAIT_SECONDS)
    try:
        return operation()
    except PermissionError as error:
        raise Unavailable(unavailable, hint="another process holds the file") from error


def replace(source: Path, destination: Path) -> None:
    """Replace `destination` with `source` whole, retrying while Windows refuses the replace
    because a reader holds the file; `Unavailable` after the bound."""
    _retry(
        lambda: os.replace(source, destination),
        unavailable=f"{destination} cannot be replaced; another process holds it",
    )


def read_bytes(path: Path) -> bytes:
    """Read a file whole, retrying while Windows refuses the open because a writer replaces it;
    `Unavailable` after the bound."""
    return _retry(
        path.read_bytes,
        unavailable=f"{path} cannot be read; another process holds it",
    )
