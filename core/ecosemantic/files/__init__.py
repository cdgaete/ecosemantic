"""The bounded retry for a file Windows refuses, and the whole write every writer lands a file
through.

Replacing a file another handle has open, and opening a file another process is replacing, are
both refused on Windows where Linux allows them. Each operation is retried `REPLACE_ATTEMPTS`
times, `REPLACE_WAIT_SECONDS` apart, and once the bound is spent the caller is answered with an
`Unavailable` naming the file and that another process holds it. `write_whole` stages the bytes
in a sibling beside the file and lands them through that retry, so a reader sees one whole
version or the other.
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from ecosemantic.errors import Unavailable

REPLACE_ATTEMPTS = 40
REPLACE_WAIT_SECONDS = 0.01

T = TypeVar("T")


def _retry(operation: Callable[[], T], *, unavailable: str, discard: Path | None) -> T:
    """Run `operation`, retrying a `PermissionError` up to `REPLACE_ATTEMPTS` times and answering
    `Unavailable` once the bound is spent, chained from the last attempt's `PermissionError` and
    removing `discard` first, since a file nothing can move is of no use."""
    for _ in range(REPLACE_ATTEMPTS - 1):
        try:
            return operation()
        except PermissionError:
            time.sleep(REPLACE_WAIT_SECONDS)
    try:
        return operation()
    except PermissionError as error:
        if discard is not None:
            with contextlib.suppress(OSError):
                discard.unlink(missing_ok=True)
        raise Unavailable(unavailable, hint="another process holds the file") from error


def replace(source: Path, destination: Path) -> None:
    """Replace `destination` with `source` whole, retrying while Windows refuses the replace
    because a reader holds the file; `Unavailable` after the bound, leaving no `source`."""
    _retry(
        lambda: os.replace(source, destination),
        unavailable=f"{destination} cannot be replaced; another process holds it",
        discard=source,
    )


def read_bytes(path: Path) -> bytes:
    """Read a file whole, retrying while Windows refuses the open because a writer replaces it;
    `Unavailable` after the bound."""
    return _retry(
        path.read_bytes,
        unavailable=f"{path} cannot be read; another process holds it",
        discard=None,
    )


def write_whole(path: Path, data: bytes) -> None:
    """Write `data` over `path` whole: the bytes staged in a sibling named for the file and a
    random token, then replaced over it, so a reader sees one of the two versions whole and
    never a part of either. The sibling is removed whatever fails."""
    sibling = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        sibling.write_bytes(data)
        replace(sibling, path)
    finally:
        with contextlib.suppress(OSError):
            sibling.unlink(missing_ok=True)
