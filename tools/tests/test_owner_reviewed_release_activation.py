import json
from pathlib import Path

import pytest

import release_manager_host_runner as runner
import release_control_transition_worker as root_worker


ROOT = Path(__file__).resolve().parents[2]
SOURCE_POLICY = ROOT / "config/mobile-release-approval-policy.json"


def v1_policy() -> dict:
    return {
        "schema_version": "1.0",
        "organization_id": "aot",
        "policy_mode": "owner_only_pilot",
        "owner_identity_ids": ["person-al"],
        "allowed_risk_profiles": ["normal"],
        "ttl_seconds": 900,
        "capability": "release.production.approve",
    }


def candidate_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "candidate"
    (tree / "config").mkdir(parents=True)
    (tree / "config/mobile-release-approval-policy.json").write_bytes(SOURCE_POLICY.read_bytes())
    return tree


def test_source_policy_is_exact_owner_reviewed_protected_core_contract():
    policy = runner.declared_mobile_release_approval_policy(ROOT)
    assert policy["schema_version"] == "2.0"
    assert policy["mode"] == "owner_reviewed"
    assert policy["risks"] == ["normal", "production_control_core"]
    assert policy["ttl_seconds"] == 900
    assert runner.classify_change_risk(
        "feature", ["config/mobile-release-approval-policy.json"]
    ) == "production_control_core"


def test_policy_stage_is_atomic_idempotent_and_restores_v1(monkeypatch, tmp_path):
    tree = candidate_tree(tmp_path)
    live = tmp_path / "mobile-release-approval-policy.json"
    live.write_text(json.dumps(v1_policy()) + "\n")
    live.chmod(0o600)
    monkeypatch.setattr(runner, "MOBILE_APPROVAL_POLICY", live)
    state = tmp_path / "state"
    record = {"release_id": "release-" + "a" * 16, "updated_at": "", "history": []}

    first = runner.stage_mobile_release_approval_policy(tree, state, record)
    assert first["status"] == "staged"
    assert first["prior_mode"] == "owner_only_pilot"
    assert first["candidate_mode"] == "owner_reviewed"
    assert runner._validated_mobile_release_policy(live)["mode"] == "owner_reviewed"

    # A crash/retry after the atomic live write must recover the existing V1
    # backup rather than treating the already-staged candidate as a conflict.
    second = runner.stage_mobile_release_approval_policy(tree, state, record)
    assert second["status"] == "staged_recovered"
    restored = runner.restore_mobile_release_approval_policy(state, record)
    assert restored["status"] == "restored"
    assert restored["mode"] == "owner_only_pilot"
    assert json.loads(live.read_text()) == v1_policy()


def test_policy_stage_rejects_unreviewed_high_impact_class(monkeypatch, tmp_path):
    tree = candidate_tree(tmp_path)
    doc = json.loads((tree / "config/mobile-release-approval-policy.json").read_text())
    doc["allowed_risk_profiles"].append("schema_or_contract")
    (tree / "config/mobile-release-approval-policy.json").write_text(json.dumps(doc))
    with pytest.raises(runner.ReleaseManagerError, match="reviewed contract"):
        runner.declared_mobile_release_approval_policy(tree)


def test_native_deploy_contract_binds_owner_reviewed_mode(monkeypatch, tmp_path):
    tree = candidate_tree(tmp_path)
    monkeypatch.setattr(runner, "declared_autotask_read_profiles", lambda _tree: None)
    monkeypatch.setattr(runner, "declared_quickbooks_read_profile", lambda _tree: None)
    monkeypatch.delenv("JASON_RELEASE_MOBILE_APPROVAL_MODE", raising=False)
    env = runner.native_deploy_environment(
        tree, "jason-runtime:test", "jason-mcp:test", "b" * 40
    )
    assert env["JASON_RELEASE_MOBILE_APPROVAL_MODE"] == "owner_reviewed"
    assert "JASON_RELEASE_MOBILE_APPROVAL_MODE" in runner._NATIVE_DEPLOY_CONTRACT_KEYS


def test_live_activation_requires_policy_digest_and_runtime_mode(monkeypatch, tmp_path):
    tree = candidate_tree(tmp_path)
    live = tmp_path / "mobile-release-approval-policy.json"
    live.write_bytes(SOURCE_POLICY.read_bytes())
    live.chmod(0o600)
    monkeypatch.setattr(runner, "MOBILE_APPROVAL_POLICY", live)
    runtime = {"inspect": {"Config": {"Env": ["JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_reviewed"]}}}
    evidence = runner.verify_live_mobile_release_approval_activation(tree, runtime)
    assert evidence["runtime_mode"] == "owner_reviewed"
    assert evidence["allowed_risk_profiles"] == ["normal", "production_control_core"]
    runtime["inspect"]["Config"]["Env"] = ["JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_only_pilot"]
    with pytest.raises(runner.ReleaseManagerError, match="runtime mode"):
        runner.verify_live_mobile_release_approval_activation(tree, runtime)


def test_deployment_script_preprod_and_rollback_are_fail_closed():
    text = (ROOT / "infrastructure/jason-runtime/production-deploy.sh").read_text()
    assert 'RELEASE_APPROVAL_MODE="off"' in text
    assert 'JASON_RELEASE_MOBILE_APPROVAL_ROLLBACK_MODE' in text
    assert '--set-env "JASON_RELEASE_MOBILE_APPROVAL_MODE=$RELEASE_APPROVAL_MODE"' in text
    assert 'invoking release approval mode differs from reviewed source' in text


def test_root_lkg_fingerprint_protects_release_approval_authority():
    assert "mobile_release_approval_policy_digest" in root_worker.PROTECTED_LKG_FIELDS
    assert "mobile_release_approval_mode" in root_worker.PROTECTED_LKG_FIELDS


def test_rollback_restores_policy_before_baseline_runtime():
    text = (ROOT / "tools/release_manager_host_runner.py").read_text()
    failure_block = text.split("except Exception as error:", 1)[1]
    restore_at = failure_block.index("restore_mobile_release_approval_policy(state_root, record)")
    runtime_at = failure_block.index("if runtime_attempted:")
    assert restore_at < runtime_at
    assert "policy_restored_before_runtime" in failure_block


def test_bootstrap_release_has_no_pm_v2_unit_delta_but_keeps_reviewed_plan():
    policy = json.loads((ROOT / "config/production-desired-state.json").read_text())
    assert "jason-pm-v2-shadow.service" not in policy["allowed_user_units"]
    migration = (ROOT / "tools/protected_root_policy_migration.py").read_text()
    assert "APPROVED_PM_V2_SHADOW_DELTA" in migration
    assert 'jason-pm-v2-shadow.service' in migration
