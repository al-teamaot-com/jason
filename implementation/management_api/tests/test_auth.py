from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from management_api.auth import (
    JwtManagementContextResolver,
    ManagementAuthenticationFailed,
)


def keypair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "https://identity.jason.local",
        "aud": "jason-management-api",
        "sub": "person-al",
        "organization_id": "aot",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def resolver(public_key):
    return JwtManagementContextResolver(
        public_key=public_key,
        issuer="https://identity.jason.local",
        audience="jason-management-api",
    )


def test_valid_signed_token_resolves_management_context():
    private_key, public_key = keypair()
    context = resolver(public_key).resolve(
        {"HTTP_AUTHORIZATION": f"Bearer {token(private_key)}"}
    )

    assert context.principal_id == "person-al"
    assert context.organization_id == "aot"


def test_spoofed_identity_headers_are_ignored():
    private_key, public_key = keypair()
    context = resolver(public_key).resolve(
        {
            "HTTP_AUTHORIZATION": f"Bearer {token(private_key)}",
            "HTTP_X_JASON_PRINCIPAL_ID": "attacker",
            "HTTP_X_JASON_ORGANIZATION_ID": "other-org",
        }
    )

    assert context.principal_id == "person-al"
    assert context.organization_id == "aot"


def test_wrong_signature_fails_closed():
    _, public_key = keypair()
    attacker_private_key, _ = keypair()

    with pytest.raises(ManagementAuthenticationFailed):
        resolver(public_key).resolve(
            {
                "HTTP_AUTHORIZATION": (
                    f"Bearer {token(attacker_private_key)}"
                )
            }
        )


def test_missing_organization_claim_fails_closed():
    private_key, public_key = keypair()
    now = datetime.now(timezone.utc)
    unsigned_claims = {
        "iss": "https://identity.jason.local",
        "aud": "jason-management-api",
        "sub": "person-al",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    signed = jwt.encode(unsigned_claims, private_key, algorithm="RS256")

    with pytest.raises(ManagementAuthenticationFailed):
        resolver(public_key).resolve(
            {"HTTP_AUTHORIZATION": f"Bearer {signed}"}
        )


def test_shared_secret_algorithms_are_rejected():
    _, public_key = keypair()

    with pytest.raises(ValueError, match="shared-secret"):
        JwtManagementContextResolver(
            public_key=public_key,
            issuer="https://identity.jason.local",
            audience="jason-management-api",
            algorithms=("HS256",),
        )
