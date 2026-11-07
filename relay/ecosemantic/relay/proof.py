"""The Ed25519 proof a bridged request carries, and the JWKs the bridge's welcome publishes to check
it."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from jwt.types import Options

from ecosemantic.relay.errors import ProofRefused
from ecosemantic.relay.messages import Door

PROOF_SECONDS = 60
_ALGORITHM = "EdDSA"
_CLAIMS: Options = {
    "verify_exp": False,
    "verify_aud": False,
    "verify_iss": False,
    "verify_jti": False,
}


@dataclass(frozen=True)
class Proof:
    """What a verified proof admits: the account, the engine, the door and its expiry."""

    account: str
    engine: UUID
    door: Door
    expires: datetime


def public_jwk(key: Ed25519PublicKey, kid: str) -> dict[str, str]:
    """The JWK a welcome carries for this key: its raw public bytes under the key's id."""
    raw = key.public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
        "kid": kid,
        "alg": _ALGORITHM,
        "use": "sig",
    }


def mint_proof(
    key: Ed25519PrivateKey,
    kid: str,
    issuer: str,
    account: str,
    engine: UUID,
    door: Door,
    now: datetime,
) -> str:
    """The token that admits one bridged request: the account, the engine and the door it names,
    its own id, expiring 60 seconds after `now`."""
    issued = int(now.timestamp())
    return jwt.encode(
        {
            "iss": issuer,
            "sub": account,
            "aud": str(engine),
            "door": door,
            "iat": issued,
            "exp": issued + PROOF_SECONDS,
            "jti": uuid4().hex,
        },
        key,
        algorithm=_ALGORITHM,
        headers={"kid": kid},
    )


def verify_proof(
    token: str,
    keys: Sequence[Mapping[str, str]],
    issuer: str,
    account: str,
    engine: UUID,
    door: Door,
    now: datetime,
) -> Proof:
    """What the proof admits. Refused when no key of the welcome carries the id it names, when its
    signature is not that key's, when it names another issuer, account, engine or door, when it
    carries no id of its own, or once `now` reaches its expiry."""
    kid = _header(token).get("kid")
    key = next((candidate for candidate in keys if candidate.get("kid") == kid), None)
    if key is None:
        raise ProofRefused(f"no key of the welcome carries the id {kid!r}")
    claims = _claims(token, _public(key))
    if claims.get("iss") != issuer:
        raise ProofRefused(f"the proof is issued by {claims.get('iss')!r}, not {issuer!r}")
    if claims.get("sub") != account:
        raise ProofRefused(f"the proof names the account {claims.get('sub')!r}, not {account!r}")
    if claims.get("aud") != str(engine):
        raise ProofRefused(f"the proof names the engine {claims.get('aud')!r}, not {engine}")
    if claims.get("door") != door:
        raise ProofRefused(f"the proof names the door {claims.get('door')!r}, not {door!r}")
    jti = claims.get("jti")
    if not isinstance(jti, str) or not jti:
        raise ProofRefused(f"the proof carries no jti, only {jti!r}")
    expires = _moment(claims, "exp")
    if expires <= now:
        raise ProofRefused(
            f"the proof expires at {expires.isoformat()}, not after {now.isoformat()}"
        )
    return Proof(account=account, engine=engine, door=door, expires=expires)


def _header(token: str) -> Mapping[str, object]:
    """The unverified header of a token, refused when the text is no token."""
    try:
        return jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as error:
        raise ProofRefused(f"the proof is no token: {error}") from error


def _public(key: Mapping[str, str]) -> Ed25519PublicKey:
    """The Ed25519 key a JWK of the welcome carries, refused when it carries none."""
    try:
        return Ed25519PublicKey.from_public_bytes(_raw(key["x"]))
    except (KeyError, ValueError) as error:
        raise ProofRefused(f"the key {key.get('kid')!r} is no Ed25519 public key") from error


def _raw(encoded: str) -> bytes:
    """The bytes a base64url value of a JWK stands for."""
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def _claims(token: str, key: Ed25519PublicKey) -> Mapping[str, object]:
    """What a token claims once its signature is the key's; the clock and the claims it names are
    checked by the caller."""
    try:
        return jwt.decode(token, key, algorithms=[_ALGORITHM], options=_CLAIMS)
    except jwt.InvalidSignatureError as error:
        raise ProofRefused("the signature is not the key's") from error
    except jwt.InvalidTokenError as error:
        raise ProofRefused(f"the proof cannot be read: {error}") from error


def _moment(claims: Mapping[str, object], name: str) -> datetime:
    """The moment a claim carries, in seconds, refused when the claim carries none."""
    value = claims.get(name)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProofRefused(f"the proof carries no numeric {name}")
    return datetime.fromtimestamp(value, UTC)
