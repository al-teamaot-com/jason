from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "openbao_raft_restore_test.py"
SPEC = importlib.util.spec_from_file_location("openbao_raft_restore_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def args(tmp_path: Path, **overrides):
    values = {
        "address": "http://127.0.0.1:8200",
        "test_address": "http://127.0.0.1:8300",
        "image": "ghcr.io/openbao/openbao:2.6.1",
        "container": "openbao-restore-test",
        "network": "jason-restore-test",
        "backup_dir": tmp_path / "backups",
        "init_file": tmp_path / "init.json",
        "token_file": tmp_path / "openbao.token",
        "wrapper": tmp_path / "jason-secret",
        "evidence_output": tmp_path / "evidence.json",
        "check_only": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_check_only_is_no_contact_and_no_write(tmp_path: Path) -> None:
    result = MODULE.execute(args(tmp_path, check_only=True))
    assert result == {
        "status": "approved",
        "mode": "check-only",
        "docker_contacted": False,
        "openbao_contacted": False,
        "protected_material_read": False,
        "evidence_written": False,
    }
    assert not (tmp_path / "evidence.json").exists()


def test_live_and_test_addresses_must_differ(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must differ"):
        MODULE.validate_configuration(
            args(tmp_path, test_address="http://127.0.0.1:8200")
        )


def test_live_container_and_network_are_denied(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="live container"):
        MODULE.validate_configuration(args(tmp_path, container="openbao"))
    with pytest.raises(ValueError, match="live Docker network"):
        MODULE.validate_configuration(args(tmp_path, network="jason-core"))


def test_existing_evidence_is_denied(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        MODULE.validate_configuration(args(tmp_path, evidence_output=output))


def test_snapshot_checksum_is_verified(tmp_path: Path) -> None:
    backup = tmp_path / "backups"
    backup.mkdir()
    snapshot = backup / "openbao.snap"
    snapshot.write_bytes(b"snapshot")
    import hashlib

    digest = hashlib.sha256(b"snapshot").hexdigest()
    Path(str(snapshot) + ".sha256").write_text(
        f"{digest}  {snapshot.name}\n",
        encoding="utf-8",
    )
    assert MODULE.latest_snapshot(backup) == snapshot
    assert MODULE.verify_snapshot(snapshot) == (digest, 8)


def test_snapshot_checksum_mismatch_is_denied(tmp_path: Path) -> None:
    snapshot = tmp_path / "openbao.snap"
    snapshot.write_bytes(b"snapshot")
    Path(str(snapshot) + ".sha256").write_text(
        f"{'0' * 64}  {snapshot.name}\n",
        encoding="utf-8",
    )
    with pytest.raises(MODULE.RestoreTestError, match="checksum"):
        MODULE.verify_snapshot(snapshot)


def test_cleanup_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    root = tmp_path / "restore"
    root.mkdir()
    monkeypatch.setattr(MODULE, "run", fake_run)
    MODULE.cleanup("restore-container", "restore-network", root)
    assert calls == [
        ["docker", "rm", "-f", "restore-container"],
        ["docker", "network", "rm", "restore-network"],
    ]
    assert not root.exists()


def test_evidence_contract_excludes_protected_values(tmp_path: Path) -> None:
    evidence = {
        "snapshot_sha256": "a" * 64,
        "cluster_identity_match": True,
        "protected_values_exposed": False,
        "status": "approved",
    }
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(evidence), encoding="utf-8")
    output.chmod(0o600)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    serialized = output.read_text(encoding="utf-8")
    for protected in ("root_token", "unseal_keys", "secret-id", "password"):
        assert protected not in serialized
