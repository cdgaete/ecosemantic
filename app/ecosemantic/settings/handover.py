"""The health an engine answers, and what a server another process may hand over to needs: the
nonce a caller that can write a systems directory proves, the files it is written in, and the calls
that post one to a route.

Nothing here imports the server, the page or the tools, so a tray reads it without loading them.
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from ecosemantic.access import secret_matches
from ecosemantic.errors import Unavailable, field_error
from ecosemantic.files import replace

UNSPECIFIED = ("0.0.0.0", "::")
LOOPBACK_ADDRESS = "127.0.0.1"
YIELD_NONCE_FILE = "yield-nonce"
STOP_NONCE_FILE = "stop-nonce"
NONCE_BYTES = 24
CALL_SECONDS = 2.0
HEALTH_SECONDS = 2.0

ServiceName = Literal["ecosemantic-view"]
SERVICE: ServiceName = "ecosemantic-view"
BridgeState = Literal["off", "connecting", "connected", "offline", "signed-out", "stopped"]
SIGNED_OUT_STATES: tuple[BridgeState, ...] = ("signed-out", "stopped")


class BridgeHealth(BaseModel):
    """The tunnel's state, and the addresses its owner needs when it has them."""

    state: BridgeState
    handle: str | None = None
    page: str | None = None
    connector: str | None = None


class Health(BaseModel):
    """The document an engine answers at `/health`: which workspace it serves, whether it yields the
    port, how its tunnel stands, and the accounts screen's address where it serves one."""

    service: ServiceName
    workspace: str
    yields: bool
    bridge: BridgeHealth
    accounts: str | None = None


def reachable(host: str) -> str:
    """The address that reaches a listener on this machine: loopback when it binds every one."""
    return host if host not in UNSPECIFIED else LOOPBACK_ADDRESS


def read_health(
    host: str, port: int, timeout: float = HEALTH_SECONDS, hint: str | None = None
) -> Health | None:
    """The health the engine on this port of this machine answers, or None when nothing answers
    there. What answers must be a health: another service's answer, an HTTP error, a body that is
    not JSON or not a `Health`, and a listener that does not speak HTTP are each refused, with the
    remedy the reader names as the refusal's hint."""
    try:
        with urllib.request.urlopen(
            f"http://{reachable(host)}:{port}/health", timeout=timeout
        ) as answer:
            body = answer.read()
    except urllib.error.HTTPError as error:
        error.close()
        raise _not_a_health(port, f"HTTP {error.code}", hint) from error
    except OSError:
        return None
    except http.client.HTTPException as error:
        raise _not_a_health(port, str(error), hint) from error
    try:
        return Health.model_validate_json(body)
    except ValidationError as error:
        raise _not_a_health(port, field_error(error), hint) from error


def _not_a_health(port: int, detail: str, hint: str | None) -> Unavailable:
    """The refusal of what a listener on this port answered instead of an engine's health."""
    return Unavailable(
        f"port {port} is held by another application, which answers what is not an EcoSemantic "
        f"engine's health: {detail}",
        hint=hint,
    )


def nonce_path(systems_dir: Path, nonce_file: str) -> Path:
    """The file a handover route's nonce is written in, by the name the route reads."""
    return systems_dir / nonce_file


def read_nonce(systems_dir: Path, nonce_file: str) -> str:
    """The nonce written in this folder, empty when it holds none."""
    try:
        return nonce_path(systems_dir, nonce_file).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def proven(sent: object, systems_dir: Path, nonce_file: str) -> bool:
    """Whether a request's nonce is the one written in this folder, which proves the caller can
    write there."""
    held = read_nonce(systems_dir, nonce_file)
    return bool(held) and secret_matches(sent, held)


def asked_with_nonce(systems_dir: Path, nonce_file: str, url: str) -> dict[str, object] | None:
    """Post a fresh nonce to a route that checks it, the nonce written at 0600 while the call is
    made and removed once it answers: the body the server answered, or None when it refused, could
    not be reached, or answered what is no object. A listener that does not speak HTTP is no route,
    so the client's own refusal is read as none too."""
    nonce = secrets.token_urlsafe(NONCE_BYTES)
    stored = nonce_path(systems_dir, nonce_file)
    _staged(stored, nonce)
    asked = urllib.request.Request(
        url,
        data=json.dumps({"nonce": nonce}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(asked, timeout=CALL_SECONDS) as answer:
            answered = json.loads(answer.read())
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        stored.unlink(missing_ok=True)
    return answered if isinstance(answered, dict) else None


def _staged(stored: Path, nonce: str) -> None:
    """Write the nonce to a temporary sibling only its owner can read and move it onto the nonce's
    path, so two callers writing at once leave one whole nonce there and never none."""
    staged = stored.with_name(f".{stored.name}.{secrets.token_hex(8)}")
    handle = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as opened:
            opened.write(nonce)
        replace(staged, stored)
    except OSError:
        staged.unlink(missing_ok=True)
        raise


def ask_to_yield(host: str, port: int, systems_dir: Path) -> bool:
    """Ask the server that holds this workspace's port to hand it over: true when it answered that
    it yielded."""
    answered = asked_with_nonce(
        systems_dir, YIELD_NONCE_FILE, f"http://{reachable(host)}:{port}/yield"
    )
    return answered is not None and answered.get("yielded") is True


def ask_to_stop(host: str, port: int, systems_dir: Path) -> bool:
    """End a server of this workspace by the nonce its systems directory proves: true when it
    answered that it stopped, false when it refused or could not be reached."""
    answered = asked_with_nonce(
        systems_dir, STOP_NONCE_FILE, f"http://{reachable(host)}:{port}/stop"
    )
    return answered is not None and answered.get("stopped") is True
