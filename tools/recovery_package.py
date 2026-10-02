from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import tarfile
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


FORMAT = "jason-recovery-package"
FORMAT_VERSION = "1.0"


class RecoveryPackageError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise RecoveryPackageError("invalid base64 in recovery package") from exc


def _derive_wrap_key(
    *,
    private_key: X25519PrivateKey,
    public_key: X25519PublicKey,
    context: bytes,
) -> bytes:
    shared = private_key.exchange(public_key)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"jason-recovery-key-wrap-v1|" + context,
    ).derive(shared)


def _build_payload(members: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in sorted(members):
            clean = name.strip().lstrip("/")
            if not clean or ".." in clean.split("/"):
                raise RecoveryPackageError(f"unsafe recovery member path: {name!r}")
            data = bytes(members[name])
            info = tarfile.TarInfo(name=clean)
            info.size = len(data)
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _extract_payload(payload: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                raise RecoveryPackageError("recovery package payload contains non-file member")
            if member.name.startswith("/") or ".." in member.name.split("/"):
                raise RecoveryPackageError("unsafe recovery member path")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RecoveryPackageError("unable to read recovery member")
            result[member.name] = extracted.read()
    return result


def _signature_material(package: Mapping[str, Any]) -> bytes:
    unsigned = {
        key: value
        for key, value in package.items()
        if key != "signature"
    }
    return canonical_json_bytes(unsigned)


@dataclass(frozen=True, slots=True)
class RecoveryPackageSummary:
    format: str
    format_version: str
    created_at: str
    source_deployment_identity_sha256: str
    recipient_key_id: str
    signer_key_id: str
    payload_ciphertext_sha256: str


def create_recovery_package(
    *,
    members: Mapping[str, bytes],
    source_deployment_identity_sha256: str,
    recipient_public_key: X25519PublicKey,
    recipient_key_id: str,
    signer_private_key: Ed25519PrivateKey,
    signer_key_id: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    source_id = source_deployment_identity_sha256.strip().lower()
    if len(source_id) != 64 or any(c not in "0123456789abcdef" for c in source_id):
        raise RecoveryPackageError("source deployment identity must be SHA-256 hex")
    if not recipient_key_id.strip() or not signer_key_id.strip():
        raise RecoveryPackageError("key identifiers must be non-empty")
    if not members:
        raise RecoveryPackageError("recovery package must contain at least one member")

    timestamp = created_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise RecoveryPackageError("created_at must be timezone-aware")
    created = timestamp.astimezone(timezone.utc).isoformat()

    payload_plaintext = _build_payload(members)
    data_key = AESGCM.generate_key(bit_length=256)
    payload_nonce = os.urandom(12)
    payload_aad = canonical_json_bytes(
        {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "created_at": created,
            "source_deployment_identity_sha256": source_id,
            "recipient_key_id": recipient_key_id.strip(),
            "signer_key_id": signer_key_id.strip(),
        }
    )
    payload_ciphertext = AESGCM(data_key).encrypt(
        payload_nonce,
        payload_plaintext,
        payload_aad,
    )

    ephemeral_private = X25519PrivateKey.generate()
    ephemeral_public = ephemeral_private.public_key()
    ephemeral_public_bytes = ephemeral_public.public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    wrap_context = source_id.encode("ascii")
    wrap_key = _derive_wrap_key(
        private_key=ephemeral_private,
        public_key=recipient_public_key,
        context=wrap_context,
    )
    wrapped_key_nonce = os.urandom(12)
    wrapped_key = AESGCM(wrap_key).encrypt(
        wrapped_key_nonce,
        data_key,
        payload_aad,
    )

    package: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "created_at": created,
        "source_deployment_identity_sha256": source_id,
        "recipient_key_id": recipient_key_id.strip(),
        "signer_key_id": signer_key_id.strip(),
        "ephemeral_public_key": _b64(ephemeral_public_bytes),
        "wrapped_key_nonce": _b64(wrapped_key_nonce),
        "wrapped_key": _b64(wrapped_key),
        "payload_nonce": _b64(payload_nonce),
        "payload_ciphertext": _b64(payload_ciphertext),
        "payload_ciphertext_sha256": hashlib.sha256(payload_ciphertext).hexdigest(),
    }
    package["signature"] = _b64(
        signer_private_key.sign(_signature_material(package))
    )
    return package


def inspect_recovery_package(package: Mapping[str, Any]) -> RecoveryPackageSummary:
    required = (
        "format",
        "format_version",
        "created_at",
        "source_deployment_identity_sha256",
        "recipient_key_id",
        "signer_key_id",
        "payload_ciphertext_sha256",
    )
    for key in required:
        if not str(package.get(key) or "").strip():
            raise RecoveryPackageError(f"recovery package field is missing: {key}")
    return RecoveryPackageSummary(
        format=str(package["format"]),
        format_version=str(package["format_version"]),
        created_at=str(package["created_at"]),
        source_deployment_identity_sha256=str(
            package["source_deployment_identity_sha256"]
        ),
        recipient_key_id=str(package["recipient_key_id"]),
        signer_key_id=str(package["signer_key_id"]),
        payload_ciphertext_sha256=str(package["payload_ciphertext_sha256"]),
    )


def verify_recovery_package_signature(
    package: Mapping[str, Any],
    *,
    signer_public_key: Ed25519PublicKey,
) -> None:
    signature = _unb64(str(package.get("signature") or ""))
    try:
        signer_public_key.verify(signature, _signature_material(package))
    except Exception as exc:
        raise RecoveryPackageError("recovery package signature verification failed") from exc

    ciphertext = _unb64(str(package.get("payload_ciphertext") or ""))
    observed = hashlib.sha256(ciphertext).hexdigest()
    if observed != str(package.get("payload_ciphertext_sha256") or ""):
        raise RecoveryPackageError("recovery package ciphertext digest mismatch")


def decrypt_recovery_package(
    package: Mapping[str, Any],
    *,
    recipient_private_key: X25519PrivateKey,
    signer_public_key: Ed25519PublicKey,
) -> dict[str, bytes]:
    verify_recovery_package_signature(
        package,
        signer_public_key=signer_public_key,
    )
    summary = inspect_recovery_package(package)
    if summary.format != FORMAT or summary.format_version != FORMAT_VERSION:
        raise RecoveryPackageError("unsupported recovery package format/version")

    ephemeral_public = X25519PublicKey.from_public_bytes(
        _unb64(str(package["ephemeral_public_key"]))
    )
    payload_aad = canonical_json_bytes(
        {
            "format": summary.format,
            "format_version": summary.format_version,
            "created_at": summary.created_at,
            "source_deployment_identity_sha256": summary.source_deployment_identity_sha256,
            "recipient_key_id": summary.recipient_key_id,
            "signer_key_id": summary.signer_key_id,
        }
    )
    wrap_key = _derive_wrap_key(
        private_key=recipient_private_key,
        public_key=ephemeral_public,
        context=summary.source_deployment_identity_sha256.encode("ascii"),
    )
    try:
        data_key = AESGCM(wrap_key).decrypt(
            _unb64(str(package["wrapped_key_nonce"])),
            _unb64(str(package["wrapped_key"])),
            payload_aad,
        )
        plaintext = AESGCM(data_key).decrypt(
            _unb64(str(package["payload_nonce"])),
            _unb64(str(package["payload_ciphertext"])),
            payload_aad,
        )
    except Exception as exc:
        raise RecoveryPackageError(
            "recovery package decryption failed; wrong key or tampered package"
        ) from exc
    return _extract_payload(plaintext)
