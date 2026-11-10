import json
from pathlib import Path

import pytest

import release_manager_host_runner as runner
import release_control_transition_worker as root_worker


ROOT = Path(__file__).resolve().parents[2]
# Historical V2/V3 tests must remain independent of the current source
# release-policy version (now V4.1). This makes the original rollback
# and policy-staging regressions meaningful instead of source-version-coupled.
def v2_policy() -> dict:
    return {
        "schema_version": "2.0",
        "organization_id": "aot",
        "policy_mode": "owner_reviewed",
        "owner_identity_ids": ["person-al"],
        "allowed_risk_profiles": ["normal", "production_control_core"],
        "ttl_seconds": 900,
        "capability": "release.production.approve",
        "high_impact_review": {
            "owner_exact_sha_required": True,
            "signed_teams_identity_required": True,
            "independent_ccc_required": True,
            "protected_release_gates_unchanged": True,
        },
    }


def v2_policy_bytes() -> bytes:
    return (json.dumps(v2_policy(), indent=2) + "\n").encode("utf-8")


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
    (tree / "config/mobile-release-approval-policy.json").write_bytes(v2_policy_bytes())
    return tree


def test_source_policy_is_exact_owner_reviewed_protected_core_contract(tmp_path):
    policy = runner.declared_mobile_release_approval_policy(candidate_tree(tmp_path))
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
    with pytest.raises(runner.ReleaseManagerError, match="reviewed"):
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
    live.write_bytes(v2_policy_bytes())
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


def test_teams_delivery_repair_defers_shadow_but_keeps_reviewed_pm_v2_plan():
    policy = json.loads((ROOT / "config/production-desired-state.json").read_text())
    assert "jason-pm-v2-shadow.service" not in policy["allowed_user_units"]
    assert "jason-pm-v2-shadow.service" not in policy["required_user_units"]
    migration = (ROOT / "tools/protected_root_policy_migration.py").read_text()
    assert "APPROVED_PM_V2_SHADOW_DELTA" in migration
    assert 'frozenset({"jason-pm-v2-shadow.service"})' in migration


def test_v3_source_policy_requires_exact_opt_in_and_keeps_v2_default(tmp_path):
    # Historical V2 never permits V3 risk before an exact versioned opt-in.
    tree = candidate_tree(tmp_path)
    assert runner.declared_mobile_release_approval_policy(tree)["schema_version"] == "2.0"
    policy_file = tree / "config/mobile-release-approval-policy.json"
    doc = json.loads(policy_file.read_text())
    doc["schema_version"] = "3.0"
    doc["allowed_risk_profiles"] = [
        "normal", "production_control_core", "production_repair",
    ]
    policy_file.write_text(json.dumps(doc))
    reviewed = runner.declared_mobile_release_approval_policy(tree)
    assert reviewed["schema_version"] == "3.0"
    assert reviewed["mode"] == "owner_reviewed"
    assert reviewed["risks"] == sorted(doc["allowed_risk_profiles"])
    doc["allowed_risk_profiles"].append("schema_or_contract")
    policy_file.write_text(json.dumps(doc))
    with pytest.raises(runner.ReleaseManagerError, match="reviewed"):
        runner.declared_mobile_release_approval_policy(tree)


def test_v3_signed_owner_offer_requires_exact_opt_in_and_reviewed_mode(tmp_path):
    from types import SimpleNamespace
    repair = {
        "risk_profile": "production_repair",
        "owner_approval": {"approved": False},
    }
    v2 = SimpleNamespace(schema_version="2.0", allowed_risk_profiles=frozenset({
        "normal", "production_control_core",
    }))
    v3 = SimpleNamespace(schema_version="3.0", allowed_risk_profiles=frozenset({
        "normal", "production_control_core", "production_repair",
    }))
    assert runner.signed_owner_offer_purpose(
        repair, "a" * 40, v2, "owner_reviewed", ccc_root=tmp_path,
    ) is None
    assert runner.signed_owner_offer_purpose(
        repair, "a" * 40, v3, "off", ccc_root=tmp_path,
    ) is None
    assert runner.signed_owner_offer_purpose(
        repair, "a" * 40, v3, "owner_reviewed", ccc_root=tmp_path,
    ) == "release_and_ccc"
    exact_approved = {
        **repair, "owner_approval": {"approved": True, "candidate_sha": "a" * 40},
    }
    assert runner.signed_owner_offer_purpose(
        exact_approved, "a" * 40, v3, "owner_reviewed", ccc_root=tmp_path,
    ) == "ccc_material_review_only"


def test_v3_policy_stages_atomically_and_rolls_back_to_original_v2(monkeypatch, tmp_path):
    tree = candidate_tree(tmp_path)
    source = tree / "config/mobile-release-approval-policy.json"
    doc = json.loads(source.read_text())
    doc["schema_version"] = "3.0"
    doc["allowed_risk_profiles"] = [
        "normal", "production_control_core", "production_repair",
    ]
    source.write_text(json.dumps(doc))
    live = tmp_path / "mobile-release-approval-policy.json"
    live.write_bytes(v2_policy_bytes())
    live.chmod(0o600)
    monkeypatch.setattr(runner, "MOBILE_APPROVAL_POLICY", live)
    record = {"release_id": "release-" + "a" * 16, "updated_at": "", "history": []}
    state = tmp_path / "state"
    original = live.read_bytes()
    staged = runner.stage_mobile_release_approval_policy(tree, state, record)
    assert staged["status"] == "staged"
    assert staged["candidate_mode"] == "owner_reviewed"
    assert runner._validated_mobile_release_policy(live)["schema_version"] == "3.0"
    assert "production_repair" in runner._validated_mobile_release_policy(live)["risks"]
    recovered = runner.stage_mobile_release_approval_policy(tree, state, record)
    assert recovered["status"] == "staged_recovered"
    restored = runner.restore_mobile_release_approval_policy(state, record)
    assert restored["status"] == "restored"
    assert live.read_bytes() == original
    assert runner._validated_mobile_release_policy(live)["risks"] == [
        "normal", "production_control_core",
    ]


def test_v3_owner_reviewed_deploy_mode_requires_reviewed_source(tmp_path):
    tree = candidate_tree(tmp_path)
    path = tree / "config/mobile-release-approval-policy.json"
    doc = json.loads(path.read_text())
    doc["schema_version"] = "3.0"
    doc["allowed_risk_profiles"].append("production_repair")
    path.write_text(json.dumps(doc))
    from unittest.mock import patch
    with patch.object(runner, "declared_autotask_read_profiles", return_value=None), \
         patch.object(runner, "declared_quickbooks_read_profile", return_value=None), \
         patch.dict(__import__('os').environ, {}, clear=False):
        env = runner.native_deploy_environment(
            tree, "jason-runtime:test", "jason-mcp:test", "b" * 40
        )
    assert env["JASON_RELEASE_MOBILE_APPROVAL_MODE"] == "owner_reviewed"
