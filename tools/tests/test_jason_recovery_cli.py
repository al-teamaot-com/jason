from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from tools.full_recovery_package import create_recovery_package
from tools import jason_recovery


NOW = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)


def write_fixture(tmp_path: Path):
    recovery = X25519PrivateKey.generate()
    signer = Ed25519PrivateKey.generate()
    package = create_recovery_package(
        members={
            "manifest/deployment.json": b"{}",
            "secrets/example": b"synthetic-secret",
        },
        source_deployment_identity_sha256="a" * 64,
        recipient_public_key=recovery.public_key(),
        recipient_key_id="owner-recovery-1",
        signer_private_key=signer,
        signer_key_id="recovery-signer-1",
        created_at=NOW,
    )

    package_path = tmp_path / "recovery.jrp.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    signer_public = tmp_path / "signer-public.pem"
    signer_public.write_bytes(
        signer.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
    )

    recovery_private = tmp_path / "recovery-private.pem"
    recovery_private.write_bytes(
        recovery.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
    )
    return package_path, signer_public, recovery_private


def test_inspect_command_outputs_only_public_summary(tmp_path, capsys):
    package_path, _, _ = write_fixture(tmp_path)
    args = jason_recovery.build_parser().parse_args(["inspect", str(package_path)])
    assert jason_recovery.command_inspect(args) == 0
    output = capsys.readouterr().out
    assert "owner-recovery-1" in output
    assert "synthetic-secret" not in output


def test_validate_can_verify_signature_without_decryption(tmp_path, capsys):
    package_path, signer_public, _ = write_fixture(tmp_path)
    args = jason_recovery.build_parser().parse_args([
        "validate",
        str(package_path),
        "--signer-public-key",
        str(signer_public),
    ])
    assert jason_recovery.command_validate(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["signature"] == "valid"
    assert result["decryptability"] == "not_checked"


def test_validate_with_recovery_key_checks_decryptability(tmp_path, capsys):
    package_path, signer_public, recovery_private = write_fixture(tmp_path)
    args = jason_recovery.build_parser().parse_args([
        "validate",
        str(package_path),
        "--signer-public-key",
        str(signer_public),
        "--recovery-private-key",
        str(recovery_private),
    ])
    assert jason_recovery.command_validate(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decryptability"] == "valid"
    assert result["member_count"] == 2
