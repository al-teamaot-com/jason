from __future__ import annotations

import base64
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from jason_openclaw.signed_transport import (
    Ed25519TransportAuthenticator,
    TransportAuthenticationError,
    canonical_signed_payload,
)


def signed_envelope():
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    envelope = {
        "request_id": "req-signed-1",
        "correlation_id": "corr-signed-1",
        "issued_at": "2026-08-08T21:00:00Z",
        "expires_at": "2026-08-08T21:05:00Z",
        "nonce": "nonce-1",
        "key_id": "openclaw-prod-1",
        "capability": "autotask.ticket.get",
        "arguments": {"ticket_id": "12445279"},
        "principal": {
            "principal_id": "person-al",
            "channel": "teams",
            "external_user_id": "openclaw-user-1",
            "organization_id": "aot",
        },
    }
    signature = private_key.sign(canonical_signed_payload(envelope))
    envelope["signature"] = base64.b64encode(signature).decode("ascii")
    return envelope, public_pem


def test_valid_signature_resolves_registered_machine_identity():
    envelope, public_pem = signed_envelope()
    authenticator = Ed25519TransportAuthenticator(
        public_keys={"openclaw-prod-1": public_pem},
        machine_identities={"openclaw-prod-1": "machine:openclaw-prod"},
    )

    assert authenticator.authenticate(envelope) == "machine:openclaw-prod"


def test_payload_tampering_fails_signature_verification():
    envelope, public_pem = signed_envelope()
    tampered = deepcopy(envelope)
    tampered["arguments"]["ticket_id"] = "DIFFERENT"
    authenticator = Ed25519TransportAuthenticator(
        public_keys={"openclaw-prod-1": public_pem},
        machine_identities={"openclaw-prod-1": "machine:openclaw-prod"},
    )

    with pytest.raises(TransportAuthenticationError, match="verification failed"):
        authenticator.authenticate(tampered)


def test_unknown_key_id_fails_closed():
    envelope, _ = signed_envelope()
    authenticator = Ed25519TransportAuthenticator(public_keys={}, machine_identities={})

    with pytest.raises(TransportAuthenticationError, match="unregistered"):
        authenticator.authenticate(envelope)
