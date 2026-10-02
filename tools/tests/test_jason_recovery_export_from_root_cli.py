from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from tools import jason_recovery
from tools.full_recovery_package import decrypt_recovery_package
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


NOW = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)


def make_sqlite(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("create table evidence(value text)")
        db.execute("insert into evidence values ('synthetic')")
        db.commit()


def prepare_root(tmp_path: Path):
    root = tmp_path / "candidate"
    for relative, content in {
        "etc/jason/deployment.json": "{}",
        "etc/jason/msp-configuration.json": "{}",
        "etc/jason/msp-policy.json": "{}",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    manifest = build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-export-cli",
            instance_id="jason-b",
            environment="candidate",
            release_version="0.1.0",
            source_sha="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            deployment_revision="c" * 64,
            msp_configuration_revision="d" * 64,
            msp_policy_revision="e" * 64,
            playbook_revision="f" * 64,
            components=(
                ComponentIdentity(
                    name="core",
                    kind="runtime",
                    required=True,
                    release_version="0.1.0",
                    source_sha="a" * 40,
                    artifact_digest="sha256:" + "b" * 64,
                ),
            ),
            schemas=(SchemaIdentity("authority", "1"),),
            providers=(ProviderIdentity("autotask", False, "bundle"),),
            runtime=RuntimeIdentity(
                os="ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29",
                compose="5",
            ),
        ),
        generated_at=NOW,
    )
    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest))

    make_sqlite(root / "var/lib/jason/authority/authority.sqlite3")
    make_sqlite(root / "var/lib/jason/authority/client-boundaries.sqlite3")
    make_sqlite(root / "var/lib/jason/openclaw/orchestration-events.sqlite3")
    make_sqlite(root / "var/lib/jason/openclaw/approval-continuations.sqlite3")

    backup = root / "opt/jason/backups/openbao"
    backup.mkdir(parents=True)
    snapshot = backup / "openbao-raft-test.snap"
    snapshot.write_bytes(b"synthetic-openbao-secret-store" * 80)
    snapshot.chmod(0o600)
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    sidecar = Path(str(snapshot) + ".sha256")
    sidecar.write_text(f"{digest}  {snapshot.name}\n")
    sidecar.chmod(0o600)

    init = root / "opt/jason/bootstrap/secrets/openbao/init.json"
    init.parent.mkdir(parents=True)
    init.write_text(
        json.dumps(
            {
                "unseal_keys_b64": ["share-a", "share-b", "share-c"],
                "unseal_shares": 3,
                "unseal_threshold": 2,
                "root_token": "synthetic-root-token",
            }
        )
    )
    init.chmod(0o600)

    trusted = root / "var/lib/jason/openclaw/trusted-keys"
    trusted.mkdir(parents=True)
    registry = trusted / "registry.json"
    registry.write_text('{"keys":[]}')
    registry.chmod(0o600)
    return root, manifest


def write_keys(tmp_path: Path):
    recovery = X25519PrivateKey.generate()
    signer = Ed25519PrivateKey.generate()
    recovery_public = tmp_path / "recovery-public.pem"
    recovery_public.write_bytes(
        recovery.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
    )
    signer_private = tmp_path / "signer-private.pem"
    signer_private.write_bytes(
        signer.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
    )
    signer_private.chmod(0o600)
    return recovery, signer, recovery_public, signer_private


def test_export_from_root_cli_creates_encrypted_full_package(tmp_path, capsys):
    root, manifest = prepare_root(tmp_path)
    recovery, signer, recovery_public, signer_private = write_keys(tmp_path)
    output = tmp_path / "jason-full-recovery.jrp.json"

    args = jason_recovery.build_parser().parse_args(
        [
            "export-from-root",
            "--target-root",
            str(root),
            "--recovery-recipient-public-key",
            str(recovery_public),
            "--recipient-key-id",
            "owner-recovery-1",
            "--signer-private-key",
            str(signer_private),
            "--signer-key-id",
            "recovery-signer-1",
            "--output",
            str(output),
        ]
    )
    assert jason_recovery.command_export_from_root(args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "exported"
    assert summary["source_deployment_identity_sha256"] == manifest["identity_sha256"]
    assert summary["plaintext_secret_values_emitted"] is False
    assert (output.stat().st_mode & 0o777) == 0o600

    encoded = output.read_text()
    assert "synthetic-root-token" not in encoded
    assert "synthetic-openbao-secret-store" not in encoded

    members = decrypt_recovery_package(
        json.loads(encoded),
        recipient_private_key=recovery,
        signer_public_key=signer.public_key(),
    )
    assert "secrets/openbao/raft/latest.snap" in members
    assert "secrets/openbao/init.json" in members
    assert b"synthetic-root-token" in members["secrets/openbao/init.json"]


def test_export_from_root_refuses_live_root(tmp_path):
    _, _, recovery_public, signer_private = write_keys(tmp_path)
    args = jason_recovery.build_parser().parse_args(
        [
            "export-from-root",
            "--target-root",
            "/",
            "--recovery-recipient-public-key",
            str(recovery_public),
            "--recipient-key-id",
            "owner-recovery-1",
            "--signer-private-key",
            str(signer_private),
            "--signer-key-id",
            "recovery-signer-1",
            "--output",
            str(tmp_path / "should-not-exist.json"),
        ]
    )
    try:
        jason_recovery.command_export_from_root(args)
    except PermissionError as exc:
        assert "live filesystem root" in str(exc)
    else:
        raise AssertionError("live-root export must remain disabled")
