from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .signed_transport import Ed25519TransportAuthenticator


@dataclass(frozen=True, slots=True)
class TrustedKeyRecord:
    key_id: str
    machine_identity: str
    public_key_path: str
    sha256_fingerprint: str
    status: str = "active"


class FileBackedTrustedKeyRegistry:
    """Load OpenClaw trusted public keys from a governed JSON registry.

    Registry records contain only public-key metadata and paths. Private key
    material is never accepted by this class.
    """

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)

    def records(self) -> tuple[TrustedKeyRecord, ...]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        entries = payload.get("keys")
        if not isinstance(entries, list):
            raise ValueError("trusted-key registry must contain a keys list")
        records: list[TrustedKeyRecord] = []
        for item in entries:
            record = TrustedKeyRecord(**item)
            if record.status != "active":
                continue
            records.append(record)
        return tuple(records)

    def build_authenticator(self) -> Ed25519TransportAuthenticator:
        public_keys: dict[str, bytes] = {}
        machine_identities: dict[str, str] = {}
        for record in self.records():
            key_path = Path(record.public_key_path)
            if not key_path.is_file():
                raise ValueError(f"registered public key missing: {record.key_id}")
            pem = key_path.read_bytes()
            fingerprint = hashlib.sha256(_public_der(pem)).hexdigest()
            if fingerprint != record.sha256_fingerprint:
                raise ValueError(f"public key fingerprint mismatch: {record.key_id}")
            public_keys[record.key_id] = pem
            machine_identities[record.key_id] = record.machine_identity
        if not public_keys:
            raise ValueError("trusted-key registry contains no active keys")
        return Ed25519TransportAuthenticator(
            public_keys=public_keys,
            machine_identities=machine_identities,
        )


def _public_der(pem: bytes) -> bytes:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key

    key = load_pem_public_key(pem)
    return key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
