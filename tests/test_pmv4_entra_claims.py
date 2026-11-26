"""Real offline RS256 verification for the existing MCP Owner issuer path."""
from __future__ import annotations

import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from jason_mcp.pmv4_entra_claims import verify_signed_entra_claims
from kernel.signed_owner_release import OWNER_OID, TID

ISSUER = "https://login.microsoftonline.com/" + TID + "/v2.0"
AUDIENCE = "trusted-jason-mcp-audience"


@pytest.fixture
def jwt_fixture():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "iss": ISSUER, "aud": AUDIENCE, "tid": TID, "oid": OWNER_OID,
        "iat": now - 10, "nbf": now - 10, "exp": now + 300,
        "scp": "jason.read",
    }
    def sign(values=None):
        return jwt.encode(values or claims, key, algorithm="RS256", headers={"kid": "offline-only"})
    resolver = lambda token: SimpleNamespace(key=key.public_key())
    def verify(token):
        return verify_signed_entra_claims(token, signing_key_lookup=resolver,
                                           audience=AUDIENCE, issuer=ISSUER)
    return claims, sign, verify


def test_valid_rsa_signed_owner_claims_recovered_without_model_assertion(jwt_fixture):
    claims, sign, verify = jwt_fixture
    assert verify(sign()) == claims


@pytest.mark.parametrize("field,value", [
    ("iss", "https://evil.invalid/"),
    ("aud", "unrelated-service"),
    ("exp", 1),
    ("nbf", 9999999999),
    ("iat", "bad"),
    ("oid", None),
    ("tid", None),
])
def test_mismatched_or_expired_issuer_audience_time_fails(jwt_fixture, field, value):
    claims, sign, verify = jwt_fixture
    altered = dict(claims)
    altered[field] = value
    # Cryptography verifies format/signature. The PMv4 issuer performs the
    # additional exact AOT tenant/OID checks after this reusable decoder.
    if field in ("tid", "oid"):
        altered.pop(field)
    assert verify(sign(altered)) is None


def test_bad_signature_and_lookup_fail_closed(jwt_fixture):
    claims, sign, verify = jwt_fixture
    another = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, another, algorithm="RS256", headers={"kid": "offline-only"})
    assert verify(forged) is None
    assert verify_signed_entra_claims(
        sign(), signing_key_lookup=lambda _: (_ for _ in ()).throw(RuntimeError("JWKS down")),
        audience=AUDIENCE, issuer=ISSUER,
    ) is None


def test_non_rsa_token_cannot_replace_signed_owner(jwt_fixture):
    claims, _, verify = jwt_fixture
    token = jwt.encode(claims, "attacker-owned-secret", algorithm="HS256")
    assert verify(token) is None
