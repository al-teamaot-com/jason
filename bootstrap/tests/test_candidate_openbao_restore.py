from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from bootstrap.candidate_host import CandidateHostIdentity
from bootstrap.candidate_openbao_restore import (
    build_candidate_openbao_restore_plan,
    restore_candidate_openbao,
)


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def sources(tmp_path: Path):
    source = tmp_path / "seed"
    snapshot = source / "latest.snap"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"synthetic-raft-snapshot" * 50)
    snapshot.chmod(0o600)
    checksum = source / "latest.snap.sha256"
    checksum.write_text(
        hashlib.sha256(snapshot.read_bytes()).hexdigest()
        + "  latest.snap\n"
    )
    checksum.chmod(0o600)

    init = source / "init.json"
    init.write_text(
        json.dumps(
            {
                "unseal_keys_b64": ["share-a", "share-b"],
                "unseal_shares": 2,
                "unseal_threshold": 2,
                "root_token": "unused-source-authority",
            }
        )
    )
    init.chmod(0o600)

    approles = source / "bootstrap"
    for role in ("autotask-read-approle", "datto-rmm-read-approle"):
        path = approles / role
        path.mkdir(parents=True)
        (path / "role-id").write_text(role + "-role\n")
        (path / "secret-id").write_text(role + "-credential\n")
        (path / "role-id").chmod(0o640)
        (path / "secret-id").chmod(0o640)
    return snapshot, checksum, init, approles


def test_restore_uses_http_snapshot_force_and_restored_approles(tmp_path):
    snapshot, checksum, init, approles = sources(tmp_path)
    target = tmp_path / "candidate"
    plan = build_candidate_openbao_restore_plan(
        target_root=target,
        candidate_identity=identity(),
        snapshot_path=snapshot,
        snapshot_checksum_path=checksum,
        init_path=init,
        approle_root=approles,
        provider_ids=("autotask", "datto_rmm"),
    )
    commands = []
    calls = []

    def runner(command):
        commands.append(tuple(command))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "unseal_keys_b64": ["temporary-share"],
                    "root_token": "temporary-authority",
                }
            ),
            stderr="",
        )

    def api(method, path, authority, payload):
        calls.append((method, path, authority, payload))
        if path == "sys/health":
            return 200, {"initialized": False, "sealed": True}
        if path == "sys/unseal":
            return 200, {"sealed": False}
        if path == "sys/storage/raft/snapshot-force":
            assert authority == "temporary-authority"
            assert payload == snapshot.read_bytes()
            return 204, {}
        if path == "auth/approle/login":
            assert authority is None
            return 200, {"auth": {"client_token": "client-value"}}
        raise AssertionError((method, path))

    result = restore_candidate_openbao(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
        api=api,
    )
    assert result["status"] == "candidate_openbao_restored"
    assert result["providers_validated"] == ["autotask", "datto_rmm"]
    assert result["temporary_authority_exposed_in_command"] is False
    assert result["new_provider_credentials_issued"] is False
    flattened = " ".join(" ".join(command) for command in commands)
    assert "temporary-authority" not in flattened
    assert "unused-source-authority" not in flattened
    assert "credential" not in flattened
    assert any(
        path == "sys/storage/raft/snapshot-force"
        for _, path, _, _ in calls
    )
    restored = (
        target
        / "opt/jason/bootstrap/secrets/openbao"
        / "autotask-read-approle/secret-id"
    )
    assert restored.is_file()
    assert (restored.stat().st_mode & 0o777) == 0o640


def test_checksum_mismatch_blocks_before_candidate_write(tmp_path):
    snapshot, checksum, init, approles = sources(tmp_path)
    snapshot.write_bytes(b"tampered")
    target = tmp_path / "candidate"
    try:
        build_candidate_openbao_restore_plan(
            target_root=target,
            candidate_identity=identity(),
            snapshot_path=snapshot,
            snapshot_checksum_path=checksum,
            init_path=init,
            approle_root=approles,
            provider_ids=("autotask",),
        )
    except Exception as exc:
        assert "checksum verification failed" in str(exc)
    else:
        raise AssertionError("tampered snapshot must fail")
    assert not target.exists()


def test_unsupported_provider_is_blocked(tmp_path):
    snapshot, checksum, init, approles = sources(tmp_path)
    try:
        build_candidate_openbao_restore_plan(
            target_root=tmp_path / "candidate",
            candidate_identity=identity(),
            snapshot_path=snapshot,
            snapshot_checksum_path=checksum,
            init_path=init,
            approle_root=approles,
            provider_ids=("unsupported",),
        )
    except Exception as exc:
        assert "no AppRole mapping" in str(exc)
    else:
        raise AssertionError("unsupported provider must fail")
