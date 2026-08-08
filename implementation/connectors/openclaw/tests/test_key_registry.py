from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry


def write_keypair(tmp_path: Path):
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_path = tmp_path / "public.pem"
    public_path.write_bytes(public.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
    der = public.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    fingerprint = hashlib.sha256(der).hexdigest()
    return private, public_path, fingerprint


def test_registry_loads_active_public_key_and_authenticator(tmp_path: Path):
    _, public_path, fingerprint = write_keypair(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"version":1,"keys":[{
        "key_id":"openclaw-gateway-1",
        "machine_identity":"svc-openclaw-gateway",
        "public_key_path":str(public_path),
        "sha256_fingerprint":fingerprint,
        "status":"active"
    }]}), encoding="utf-8")

    authenticator = FileBackedTrustedKeyRegistry(registry).build_authenticator()
    assert authenticator.machine_identities["openclaw-gateway-1"] == "svc-openclaw-gateway"


def test_registry_fails_closed_on_fingerprint_mismatch(tmp_path: Path):
    _, public_path, _ = write_keypair(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"version":1,"keys":[{
        "key_id":"openclaw-gateway-1",
        "machine_identity":"svc-openclaw-gateway",
        "public_key_path":str(public_path),
        "sha256_fingerprint":"0"*64,
        "status":"active"
    }]}), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        FileBackedTrustedKeyRegistry(registry).build_authenticator()
