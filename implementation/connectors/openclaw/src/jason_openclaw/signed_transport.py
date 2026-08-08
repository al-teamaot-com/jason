from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class TransportAuthenticationError(ValueError):
    pass


def canonical_signed_payload(envelope: Mapping[str, Any]) -> bytes:
    excluded = {"signature"}
    body = {str(key): value for key, value in envelope.items() if str(key) not in excluded}
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class Ed25519TransportAuthenticator:
    """Verify OpenClaw application-layer signatures using registered public keys.

    Public keys are not secrets. The corresponding private key remains with the
    OpenClaw machine identity and is never accepted in request payloads.
    """

    public_keys: Mapping[str, bytes | str]
    machine_identities: Mapping[str, str]

    def authenticate(self, envelope: Mapping[str, Any]) -> str:
        key_id = str(envelope.get("key_id", "")).strip()
        signature_text = str(envelope.get("signature", "")).strip()
        if not key_id or not signature_text:
            raise TransportAuthenticationError("signed transport metadata missing")

        public_key_pem = self.public_keys.get(key_id)
        machine_identity = self.machine_identities.get(key_id)
        if public_key_pem is None or machine_identity is None:
            raise TransportAuthenticationError("unregistered OpenClaw signing key")

        try:
            signature = base64.b64decode(signature_text, validate=True)
        except Exception as exc:
            raise TransportAuthenticationError("signature encoding invalid") from exc

        if isinstance(public_key_pem, str):
            public_key_pem = public_key_pem.encode("utf-8")
        public_key = load_pem_public_key(public_key_pem)
        try:
            public_key.verify(signature, canonical_signed_payload(envelope))
        except InvalidSignature as exc:
            raise TransportAuthenticationError("signature verification failed") from exc
        except Exception as exc:
            raise TransportAuthenticationError("registered public key is invalid") from exc

        return machine_identity
