from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from tools.full_recovery_builtin_adapters import (
    BuiltinRecoveryAdapterError,
    discover_builtin_adapter_names,
    governed_key_export_adapter,
    governed_secret_export_adapter,
)


def prepare_openbao(root: Path):
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
    return snapshot, init


def test_builtin_openbao_adapters_package_snapshot_and_protected_recovery_material(tmp_path):
    root = tmp_path / "candidate"
    snapshot, init = prepare_openbao(root)

    secret_payloads, _ = governed_secret_export_adapter(
        "provider-secrets",
        {},
        root,
    )
    key_payloads, _ = governed_key_export_adapter(
        "signing-key-material",
        {},
        root,
    )

    assert secret_payloads[0].data == snapshot.read_bytes()
    assert secret_payloads[0].restore_relative_path.endswith(
        "recovery/openbao/latest.snap"
    )
    init_payload = next(
        item for item in key_payloads if item.member_name == "secrets/openbao/init.json"
    )
    assert init_payload.data == init.read_bytes()
    assert init_payload.metadata["protected_values_exposed"] is False
    assert any(
        item.member_name == "secrets/trusted-keys/registry.json"
        for item in key_payloads
    )
    assert discover_builtin_adapter_names(root) == (
        "governed_key_export",
        "governed_secret_export",
    )


def test_snapshot_checksum_tampering_blocks_secret_export(tmp_path):
    root = tmp_path / "candidate"
    snapshot, _ = prepare_openbao(root)
    snapshot.write_bytes(b"tampered")
    with pytest.raises(
        BuiltinRecoveryAdapterError,
        match="checksum verification failed",
    ):
        governed_secret_export_adapter("provider-secrets", {}, root)


def test_init_permissions_must_be_private(tmp_path):
    root = tmp_path / "candidate"
    _, init = prepare_openbao(root)
    init.chmod(0o644)
    with pytest.raises(
        BuiltinRecoveryAdapterError,
        match="permissions are too broad",
    ):
        governed_key_export_adapter("signing-key-material", {}, root)
    assert "governed_key_export" not in discover_builtin_adapter_names(root)


def prepare_kfs_backup(root: Path):
    from tools.kfs_postgresql_backup import KfsPostgresqlBackupResult

    dump = root / "var/lib/jason/recovery/kfs/kfs-postgresql.dump"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"PGDMP-synthetic-kfs-backup")
    dump.chmod(0o600)
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    receipt = dump.with_suffix(".dump.receipt.json")
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "output_path": str(dump),
                "sha256": digest,
                "size_bytes": dump.stat().st_size,
                "database": "kfs_collector",
                "host": "127.0.0.1",
                "port": 5432,
                "user": "kfs_collector",
                "format": "postgresql-custom",
                "verified": True,
            }
        )
    )
    receipt.chmod(0o600)
    return dump, receipt


def test_kfs_backup_adapter_packages_only_verified_custom_dump(tmp_path):
    from tools.full_recovery_builtin_adapters import (
        kfs_postgresql_backup_adapter,
    )

    root = tmp_path / "candidate"
    dump, receipt = prepare_kfs_backup(root)
    payloads, metadata = kfs_postgresql_backup_adapter(
        "kfs-postgresql",
        {},
        root,
    )
    assert metadata == ()
    assert payloads[0].data == dump.read_bytes()
    assert payloads[0].metadata["verified"] is True
    assert payloads[0].metadata["format"] == "postgresql-custom"
    assert payloads[1].data == receipt.read_bytes()
    assert "kfs_postgresql_backup" in discover_builtin_adapter_names(root)


def test_kfs_backup_adapter_rejects_receipt_digest_mismatch(tmp_path):
    from tools.full_recovery_builtin_adapters import (
        kfs_postgresql_backup_adapter,
    )

    root = tmp_path / "candidate"
    dump, receipt = prepare_kfs_backup(root)
    payload = json.loads(receipt.read_text())
    payload["sha256"] = "0" * 64
    receipt.write_text(json.dumps(payload))
    receipt.chmod(0o600)
    with pytest.raises(
        BuiltinRecoveryAdapterError,
        match="digest does not match",
    ):
        kfs_postgresql_backup_adapter("kfs-postgresql", {}, root)


def test_missing_kfs_backup_is_optional_source_unavailable(tmp_path):
    from tools.full_recovery_builtin_adapters import (
        kfs_postgresql_backup_adapter,
    )
    from tools.full_recovery_export import OptionalRecoverySourceUnavailable

    with pytest.raises(OptionalRecoverySourceUnavailable):
        kfs_postgresql_backup_adapter(
            "kfs-postgresql",
            {},
            tmp_path / "candidate",
        )
