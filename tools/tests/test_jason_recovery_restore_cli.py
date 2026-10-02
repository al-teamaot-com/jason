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
from tools.full_recovery_restore import assemble_recovery_members
from tools import jason_recovery


NOW = datetime(2026, 10, 2, 19, 30, tzinfo=timezone.utc)
SOURCE_ID = "a" * 64


def write_fixture(tmp_path: Path, *, reenrollment: bool = False):
    recovery = X25519PrivateKey.generate()
    signer = Ed25519PrivateKey.generate()

    metadata_only = (
        (("host-bound-identity", {"identity": "synthetic-tpm"}),)
        if reenrollment
        else (("service-and-schedule-definitions", {"source": "release"}),)
    )
    members = assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=(
            (
                "deployment-configuration",
                "state/deployment/config.json",
                "etc/jason/deployment.json",
                b'{"environment":"candidate"}',
                {"source": "synthetic"},
            ),
            (
                "provider-secrets",
                "secrets/provider-token",
                "var/lib/jason/recovery-secrets/provider-token",
                b"synthetic-secret",
                {"provider": "synthetic"},
            ),
        ),
        metadata_only=metadata_only,
    )
    package = create_recovery_package(
        members=members,
        source_deployment_identity_sha256=SOURCE_ID,
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


def parse_args(tmp_path: Path, command: str, *, reenrollment: bool = False):
    package, signer, recovery = write_fixture(
        tmp_path,
        reenrollment=reenrollment,
    )
    target = tmp_path / "restore-root"
    args = jason_recovery.build_parser().parse_args(
        [
            command,
            str(package),
            "--signer-public-key",
            str(signer),
            "--recovery-private-key",
            str(recovery),
            "--target-root",
            str(target),
            "--expected-source-deployment-id",
            SOURCE_ID,
        ]
    )
    return args, target


def test_plan_restore_outputs_no_secret_contents(tmp_path, capsys):
    args, target = parse_args(tmp_path, "plan-restore")
    assert jason_recovery.command_plan_restore(args) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "ready_for_restore"
    assert "synthetic-secret" not in output
    assert not target.exists()


def test_restore_to_root_applies_validated_payload_without_starting_services(tmp_path, capsys):
    args, target = parse_args(tmp_path, "restore-to-root")
    assert jason_recovery.command_restore_to_root(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "restore_payload_applied"
    assert output["services_started"] is False
    assert output["migrations_run"] is False
    assert (
        target / "var/lib/jason/recovery-secrets/provider-token"
    ).read_bytes() == b"synthetic-secret"


def test_reenrollment_blocks_restore_to_root_before_writes(tmp_path, capsys):
    args, target = parse_args(
        tmp_path,
        "restore-to-root",
        reenrollment=True,
    )
    assert jason_recovery.command_restore_to_root(args) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked_for_reenrollment"
    assert not target.exists()


def test_restore_cli_can_acknowledge_required_machine_reenrollment(tmp_path, capsys):
    args, target = parse_args(
        tmp_path,
        "restore-to-root",
        reenrollment=True,
    )
    args.acknowledge_reenrollment = ["host-bound-identity"]
    assert jason_recovery.command_restore_to_root(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "restore_payload_applied"
    assert target.exists()
