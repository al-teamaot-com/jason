"""Isolated V4 -> V5 staging, recovery and rollback contract.

No live root-policy writes. Native Release Manager authority remains separate.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import release_manager_host_runner as runner

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / "config/mobile-release-approval-policy.json"
V5 = ROOT / "config/mobile-release-approval-policy-v5-candidate.json"


def environment(tmp_path, monkeypatch):
    tree = tmp_path / "candidate"
    (tree / "config").mkdir(parents=True)
    (tree / "config/mobile-release-approval-policy.json").write_bytes(V5.read_bytes())
    live = tmp_path / "live-policy.json"
    original = V4.read_bytes()
    live.write_bytes(original)
    live.chmod(0o600)
    monkeypatch.setattr(runner, "MOBILE_APPROVAL_POLICY", live)
    state = tmp_path / "state"
    rec = {"release_id": "release-" + "a"*16, "updated_at": "", "history": []}
    return tree, live, state, rec, original


def test_v4_to_v5_native_stage_idempotent_and_byte_exact_rollback(tmp_path, monkeypatch):
    tree, live, state, rec, original = environment(tmp_path, monkeypatch)
    assert runner._validated_mobile_release_policy(live)["schema_version"] == "4.0"
    first = runner.stage_mobile_release_approval_policy(tree, state, rec)
    assert first["prior_schema_version"] == "4.0"
    assert first["candidate_schema_version"] == "5.0"
    assert first["candidate_mode"] == "service_requester_regular_owner_teams"
    assert runner._validated_mobile_release_policy(live)["schema_version"] == "5.0"
    assert live.stat().st_mode & 0o777 == 0o600
    second = runner.stage_mobile_release_approval_policy(tree, state, rec)
    assert second["status"] == "staged_recovered"
    restored = runner.restore_mobile_release_approval_policy(state, rec)
    assert restored["mode"] == "admin_approver_separated"
    assert live.read_bytes() == original
    backup = state / "mobile-release-policy-transitions" / (rec["release_id"] + ".prior-policy.json")
    assert backup.read_bytes() == original
    assert backup.stat().st_mode & 0o777 == 0o600


def test_v4_to_v5_staging_failure_restores_existing_policy(tmp_path, monkeypatch):
    tree, live, state, rec, original = environment(tmp_path, monkeypatch)
    actual_write = runner._atomic_private_bytes
    counter = 0

    def simulated_failure(path, raw):
        nonlocal counter
        counter += 1
        actual_write(path, raw)
        if counter == 1:
            raise OSError("controlled failure after staged bytes")

    monkeypatch.setattr(runner, "_atomic_private_bytes", simulated_failure)
    with pytest.raises(OSError, match="controlled failure"):
        runner.stage_mobile_release_approval_policy(tree, state, rec)
    assert counter == 2
    assert live.read_bytes() == original
    assert rec["mobile_release_policy_transition"]["status"] == "stage_failed_restored"


def test_v4_to_v5_drifted_backup_fails_without_changing_live_policy(tmp_path, monkeypatch):
    tree, live, state, rec, original = environment(tmp_path, monkeypatch)
    first = runner.stage_mobile_release_approval_policy(tree, state, rec)
    backup = Path(first["backup_path"])
    backup.write_bytes(V5.read_bytes())
    backup.chmod(0o600)
    before = live.read_bytes()
    with pytest.raises(runner.ReleaseManagerError, match="existing release approval policy backup conflicts"):
        runner.stage_mobile_release_approval_policy(tree, state, rec)
    assert live.read_bytes() == before
    with pytest.raises(runner.ReleaseManagerError, match="rollback backup identity changed"):
        runner.restore_mobile_release_approval_policy(state, rec)


def test_v5_native_activation_needs_installed_policy_digest_and_mode(tmp_path, monkeypatch):
    tree, live, state, rec, original = environment(tmp_path, monkeypatch)
    runner.stage_mobile_release_approval_policy(tree, state, rec)
    runtime = {"inspect": {"Config": {"Env": [
        "JASON_RELEASE_MOBILE_APPROVAL_MODE=service_requester_regular_owner_teams",
    ]}}}
    result = runner.verify_live_mobile_release_approval_activation(tree, runtime)
    assert result["runtime_mode"] == "service_requester_regular_owner_teams"
    runtime["inspect"]["Config"]["Env"] = [
        "JASON_RELEASE_MOBILE_APPROVAL_MODE=admin_approver_separated",
    ]
    with pytest.raises(runner.ReleaseManagerError, match="runtime mode"):
        runner.verify_live_mobile_release_approval_activation(tree, runtime)
    runner.restore_mobile_release_approval_policy(state, rec)
    assert live.read_bytes() == original
    with pytest.raises(runner.ReleaseManagerError):
        runner.verify_live_mobile_release_approval_activation(tree, runtime)
