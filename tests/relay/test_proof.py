from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ecosemantic.relay.errors import ProofRefused
from ecosemantic.relay.proof import PROOF_SECONDS, Proof, mint_proof, public_jwk, verify_proof

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ENGINE = UUID("6f3d1e2a-0000-4000-8000-000000000001")
OTHER_ENGINE = UUID("6f3d1e2a-0000-4000-8000-000000000002")
ISSUER = "https://logto.test/oidc"
ACCOUNT = "acct_1"
KID = "bridge-1"
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
OTHER_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
KEYS = [public_jwk(KEY.public_key(), KID), public_jwk(OTHER_KEY.public_key(), "bridge-2")]
ISSUED = int(NOW.timestamp())
CLAIMS = {
    "iss": ISSUER,
    "sub": ACCOUNT,
    "aud": str(ENGINE),
    "door": "mcp",
    "iat": ISSUED,
    "exp": ISSUED + PROOF_SECONDS,
}


def minted(**changed: object) -> str:
    claim = {
        "key": KEY,
        "kid": KID,
        "issuer": ISSUER,
        "account": ACCOUNT,
        "engine": ENGINE,
        "door": "mcp",
        "now": NOW,
    }
    return mint_proof(**{**claim, **changed})


def checked(token: str, **changed: object) -> Proof:
    claim = {
        "token": token,
        "keys": KEYS,
        "issuer": ISSUER,
        "account": ACCOUNT,
        "engine": ENGINE,
        "door": "mcp",
        "now": NOW,
    }
    return verify_proof(**{**claim, **changed})


def signed(claims: dict[str, object]) -> str:
    return jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})


def claims_of(token: str) -> dict[str, object]:
    return jwt.decode(token, options={"verify_signature": False})


def test_a_minted_proof_is_verified_into_its_claims() -> None:
    proof = checked(minted())
    assert proof == Proof(
        account=ACCOUNT,
        engine=ENGINE,
        door="mcp",
        expires=NOW + timedelta(seconds=PROOF_SECONDS),
    )
    assert PROOF_SECONDS == 60


def test_a_minted_proof_carries_an_id_of_its_own() -> None:
    first = minted()
    found = claims_of(first)["jti"]
    assert isinstance(found, str) and len(found) == 32
    assert int(found, 16) >= 0
    assert claims_of(minted())["jti"] != found
    assert checked(first).account == ACCOUNT


@pytest.mark.parametrize(
    "claims",
    [CLAIMS, {**CLAIMS, "jti": ""}, {**CLAIMS, "jti": 7}],
    ids=["absent", "empty", "not-text"],
)
def test_a_proof_without_its_id_is_refused(claims: dict[str, object]) -> None:
    with pytest.raises(ProofRefused, match="jti"):
        checked(signed(claims))


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        (minted(account="acct_2"), "account"),
        (minted(engine=OTHER_ENGINE), "engine"),
        (minted(door="page"), "door"),
        (minted(issuer="https://other.test/oidc"), "issued"),
        (minted(key=OTHER_KEY), "signature"),
        (minted(kid="bridge-3"), "key"),
        ("not a token", "token"),
    ],
)
def test_a_proof_is_refused_for_another_account_engine_door_issuer_or_key(
    token: str, reason: str
) -> None:
    with pytest.raises(ProofRefused, match=reason):
        checked(token)


def test_a_proof_is_refused_once_now_reaches_its_expiry() -> None:
    token = minted()
    assert checked(token, now=NOW + timedelta(seconds=PROOF_SECONDS - 1)).account == ACCOUNT
    with pytest.raises(ProofRefused, match="expires"):
        checked(token, now=NOW + timedelta(seconds=PROOF_SECONDS))
