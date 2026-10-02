from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from jsonschema import Draft202012Validator

from tools.recovery_package import (
    RecoveryPackageError,
    create_recovery_package,
    decrypt_recovery_package,
    inspect_recovery_package,
)


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)
SOURCE_ID = "a" * 64


def keys():
    recovery = X25519PrivateKey.generate()
    signer = Ed25519PrivateKey.generate()
    return recovery, signer


def package():
    recovery, signer = keys()
    created = create_recovery_package(
        members={
            "manifest/deployment.json": b'{"identity":"candidate-a"}',
            "state/authority.sqlite3": b"synthetic-authority-state",
            "secrets/provider-token": b"synthetic-secret-do-not-leak",
        },
        source_deployment_identity_sha256=SOURCE_ID,
        recipient_public_key=recovery.public_key(),
        recipient_key_id="owner-recovery-key-1",
        signer_private_key=signer,
        signer_key_id="jason-recovery-signer-1",
        created_at=NOW,
    )
    return created, recovery, signer


def test_recovery_package_round_trip_and_schema_validation():
    created, recovery, signer = package()
    schema = json.load(open("config/schemas/jason-recovery-package.schema.json", encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(created)

    restored = decrypt_recovery_package(
        created,
        recipient_private_key=recovery,
        signer_public_key=signer.public_key(),
    )
    assert restored["state/authority.sqlite3"] == b"synthetic-authority-state"
    assert restored["secrets/provider-token"] == b"synthetic-secret-do-not-leak"


def test_inspection_exposes_metadata_without_plaintext_payload():
    created, _, _ = package()
    summary = inspect_recovery_package(created)
    assert summary.source_deployment_identity_sha256 == SOURCE_ID
    encoded = json.dumps(created)
    assert "synthetic-secret-do-not-leak" not in encoded
    assert "synthetic-authority-state" not in encoded


def test_wrong_recovery_key_fails_closed():
    created, _, signer = package()
    wrong = X25519PrivateKey.generate()
    with pytest.raises(RecoveryPackageError, match="decryption failed"):
        decrypt_recovery_package(
            created,
            recipient_private_key=wrong,
            signer_public_key=signer.public_key(),
        )


def test_package_tampering_fails_signature_verification():
    created, recovery, signer = package()
    tampered = deepcopy(created)
    tampered["recipient_key_id"] = "attacker-key"
    with pytest.raises(RecoveryPackageError, match="signature verification failed"):
        decrypt_recovery_package(
            tampered,
            recipient_private_key=recovery,
            signer_public_key=signer.public_key(),
        )


def test_ciphertext_tampering_fails_closed():
    created, recovery, signer = package()
    tampered = deepcopy(created)
    ciphertext = tampered["payload_ciphertext"]
    tampered["payload_ciphertext"] = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    with pytest.raises(RecoveryPackageError):
        decrypt_recovery_package(
            tampered,
            recipient_private_key=recovery,
            signer_public_key=signer.public_key(),
        )


def test_unsafe_member_paths_are_rejected():
    recovery, signer = keys()
    with pytest.raises(RecoveryPackageError, match="unsafe"):
        create_recovery_package(
            members={"../escape": b"bad"},
            source_deployment_identity_sha256=SOURCE_ID,
            recipient_public_key=recovery.public_key(),
            recipient_key_id="owner",
            signer_private_key=signer,
            signer_key_id="signer",
            created_at=NOW,
        )
