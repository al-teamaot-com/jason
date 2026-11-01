from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/release_manager_host_runner.py"
spec = importlib.util.spec_from_file_location("open_breaker_recovery_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)

SHA_A = "a" * 40
SHA_B = "b" * 40



def reviewed_recovery_policy():
    return json.loads((ROOT / "config/open-breaker-recovery-policy.json").read_text())

def recovery_record(*, owner_source="authenticated_mobile_teams_owner:relapproval-" + "c" * 32):
    return {
        "release_id": runner.record_id(SHA_A),
        "state": "production_eligible",
        "change_class": "release_blocker",
        "risk_profile": "production_control_core",
        "rollback_sha": SHA_B,
        "changed_files": [
            "infrastructure/openclaw-operations/systemd/jason-openclaw-authority-full-integrity.service",
            "tools/openclaw_authority_health_snapshot.py",
            "tools/openclaw_authority_operational_health.py",
            "tools/release_manager_host_runner.py",
            "tools/tests/test_open_breaker_recovery_release.py",
        ],
        "release_candidate": {"candidate_sha": SHA_A},
        "release_manifest": {"candidate_sha": SHA_A, "rollback_sha": SHA_B},
        "development": {"required_checks_passed": True},
        "preproduction": {
            "acceptance_passed": True,
            "rollback_readiness_passed": True,
            "provider_mutations_disabled": True,
        },
        "owner_approval": {
            "approved": True,
            "candidate_sha": SHA_A,
            "source": owner_source,
        },
    }


def open_control():
    return {
        "schema_version": "1.0",
        "circuit_breaker": {
            "state": "open",
            "source": "production_drift_watchdog",
            "reason": "continuous_production_drift_detected",
        },
        "last_known_good": {"manifest": {"complete": True, "revision": SHA_B}},
    }


def authority_drift(*, extra=False):
    problems = [
        {"kind": "failed_system_unit", "state": "failed",
         "unit": "jason-openclaw-authority-full-integrity.service"},
        {"kind": "failed_system_unit", "state": "failed",
         "unit": "jason-openclaw-authority-health.service"},
    ]
    if extra:
        problems.append({"kind": "failed_user_unit", "state": "failed",
                         "unit": "jason-dnsfilter-boundary-reconcile.service"})
    return {
        "schema_version": "1.0",
        "status": "drift_detected",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "problems": problems,
    }



def test_recovery_policy_is_protected_core():
    assert runner.classify_change_risk(
        "feature", ["config/open-breaker-recovery-policy.json"]
    ) == "production_control_core"

def test_exact_profile_allows_only_signed_teams_owner_recovery():
    record = recovery_record()
    with (
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "recovery_live_production_alignment", return_value={"runtime_health_mode":"healthy"}),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "_open_breaker_recovery_policy", return_value=reviewed_recovery_policy()),
    ):
        context = runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=True,
            control=open_control(), drift=authority_drift(),
        )
    assert context is not None
    assert context["profile_id"] == "authority_integrity_timeout"
    assert context["candidate_sha"] == SHA_A
    assert context["rollback_sha"] == SHA_B

    record = recovery_record(owner_source="explicit_owner_instruction")
    with (
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "recovery_live_production_alignment", return_value={"runtime_health_mode":"healthy"}),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "_open_breaker_recovery_policy", return_value=reviewed_recovery_policy()),
    ):
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=True,
            control=open_control(), drift=authority_drift(),
        ) is None


def test_unrelated_drift_or_missing_repair_file_blocks_recovery():
    record = recovery_record()
    with (
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "recovery_live_production_alignment", return_value={"runtime_health_mode":"healthy"}),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "_open_breaker_recovery_policy", return_value=reviewed_recovery_policy()),
    ):
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=False,
            control=open_control(), drift=authority_drift(extra=True),
        ) is None
        record["changed_files"].remove("tools/openclaw_authority_operational_health.py")
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=False,
            control=open_control(), drift=authority_drift(),
        ) is None



def test_reviewed_authority_recovery_bundle_allows_18_files_but_not_19():
    record = recovery_record()
    required = list(record["changed_files"])
    while len(required) < 18:
        required.append(f"docs/recovery-evidence-{len(required):02d}.md")
    record["changed_files"] = required
    with (
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "recovery_live_production_alignment", return_value={"runtime_health_mode":"healthy"}),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "_open_breaker_recovery_policy", return_value=reviewed_recovery_policy()),
    ):
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=False,
            control=open_control(), drift=authority_drift(),
        ) is not None
        record["changed_files"].append("docs/recovery-evidence-over-bound.md")
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=False,
            control=open_control(), drift=authority_drift(),
        ) is None

def test_recovery_offer_is_nonexecuting_and_profile_bound(tmp_path):
    import release_mobile_approval_consumer as mobile_consumer
    mobile_consumer._install_repo_modules(ROOT)
    import jason_runtime.mobile_release_approval as mobile_policy
    import jason_runtime.owner_release_approval_containment as containment

    (tmp_path / "auto-promotion-incident-hold").touch()
    (tmp_path / "records").mkdir()
    policy = tmp_path / "mobile-policy.json"
    policy.write_text("{}")
    record = recovery_record()
    record["owner_approval"] = {"approved": False, "candidate_sha": None, "source": None}
    runner.atomic_json(tmp_path / "records" / (record["release_id"] + ".json"), record)
    reviewed = SimpleNamespace(
        schema_version="2.0", allowed_risk_profiles=frozenset({"normal", "production_control_core"})
    )
    live = {"revision": SHA_B,
            "inspect": {"Config": {"Env": ["JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_reviewed"]}}}
    context = {
        "schema_version": "1.0", "profile_id": "authority_integrity_timeout",
        "candidate_sha": SHA_A, "rollback_sha": SHA_B,
        "drift_observed_at": authority_drift()["observed_at"],
        "drift_problems": [], "policy_sha256": "sha256:" + "d" * 64,
        "owner_approval_required": False,
    }
    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "MOBILE_APPROVAL_POLICY", policy),
        patch.object(runner, "_read_protected_snapshot",
                     side_effect=lambda root, name: open_control() if name.endswith("control-state.json") else authority_drift()),
        patch.object(runner, "live_runtime_unchecked_health", return_value=live),
        patch.object(runner, "live_runtime", return_value=live),
        patch.object(runner, "recovery_live_production_alignment", return_value={"runtime_health_mode":"healthy"}),
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "governed_open_breaker_recovery_context", return_value=context),
        patch.object(mobile_consumer, "_install_repo_modules"),
        patch.object(mobile_consumer, "consume_mobile_release_decisions") as consume,
        patch.object(mobile_policy, "read_mobile_release_policy", return_value=reviewed),
        patch.object(containment, "read_release_approval_containment",
                     return_value=SimpleNamespace(active=False)),
        patch.object(runner, "signed_owner_offer_purpose", return_value="release_and_ccc"),
        patch.object(runner, "deploy_production") as deploy,
    ):
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path)
    offer = json.loads((tmp_path / "mobile-release-offers" / (record["release_id"] + ".json")).read_text())
    assert offer["recovery_profile_id"] == "authority_integrity_timeout"
    assert offer["candidate_sha"] == SHA_A
    consume.assert_called_once()
    deploy.assert_not_called()


def test_deploy_wrapper_crosses_open_breaker_only_with_proven_recovery(tmp_path):
    record = recovery_record()
    context = {"profile_id": "authority_integrity_timeout", "candidate_sha": SHA_A}
    with (
        patch.object(runner, "require_owner_production_deployment_unfrozen"),
        patch.object(runner, "acquire_production_transaction_lock", return_value=object()),
        patch.object(runner, "release_production_transaction_lock"),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "require_current_protected_release_source"),
        patch.object(runner, "require_host_reconciler_ready"),
        patch.object(runner, "reconcile_stopped_rollback_retention"),
        patch.object(runner, "_read_protected_snapshot",
                     side_effect=lambda root, name: open_control() if name.endswith("control-state.json") else authority_drift()),
        patch.object(runner, "governed_open_breaker_recovery_context", return_value=context),
        patch.object(runner, "revalidate_circuit_breaker",
                     side_effect=runner.ReleaseManagerError("production drift is not clean")) as revalidate,
        patch.object(runner, "_deploy_production_locked", return_value=record) as deploy_locked,
    ):
        assert runner.deploy_production(ROOT, tmp_path, record) is record
    revalidate.assert_called_once()
    assert deploy_locked.call_args.kwargs["recovery_context"] == context


def provider_identity_drift(*, extra=False):
    problems = authority_drift()["problems"] + [
        {"kind": "failed_user_unit", "state": "failed",
         "unit": "jason-dnsfilter-boundary-reconcile.service"},
    ]
    if extra:
        problems.append({"kind": "failed_system_unit", "state": "failed",
                         "unit": "jason-unrelated.service"})
    return {
        "schema_version": "1.0",
        "status": "drift_detected",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "problems": problems,
    }


def provider_identity_record():
    record = recovery_record()
    record["changed_files"] = [
        "infrastructure/openclaw-operations/systemd/jason-openclaw-authority-full-integrity.service",
        "tools/openclaw_authority_health_snapshot.py",
        "tools/openclaw_authority_operational_health.py",
        "tools/openbao_identity_lifecycle.py",
        "tools/openbao_identity_lifecycle_worker.py",
        "tools/install_openbao_identity_lifecycle.py",
        "tools/reconcile_production_host_services.sh",
        "tools/release_manager_host_runner.py",
    ]
    return record


def test_provider_identity_recovery_requires_exact_drift_and_degraded_runtime_profile():
    record = provider_identity_record()
    with (
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
        patch.object(runner, "require_current_manual_scope_review"),
        patch.object(runner, "_open_breaker_recovery_policy", return_value=reviewed_recovery_policy()),
        patch.object(runner, "recovery_live_production_alignment",
                     return_value={"runtime_health_mode": "ticket_worker_provider_auth_degraded"}),
    ):
        context = runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=True,
            control=open_control(), drift=provider_identity_drift(),
        )
        assert context is not None
        assert context["profile_id"] == "provider_identity_and_authority_recovery"
        assert context["runtime_health_mode"] == "ticket_worker_provider_auth_degraded"
        assert context["runtime_health"]["ticket_worker"] == "process_not_alive"
        assert runner.governed_open_breaker_recovery_context(
            ROOT, ROOT, record, require_owner_approval=True,
            control=open_control(), drift=provider_identity_drift(extra=True),
        ) is None


def test_provider_identity_degraded_runtime_contract_is_exact():
    profile = next(
        item for item in reviewed_recovery_policy()["profiles"]
        if item["id"] == "provider_identity_and_authority_recovery"
    )
    runtime = {"inspect": {"State": {"Health": {"Status": "unhealthy"}}}}
    body = {
        "authority": "central-orchestrator",
        "component": "jason-runtime",
        "status": "degraded",
        "ticket_worker": {
            "last_restart_reason": "restart_budget_exhausted:missing_process",
            "status": "degraded",
            "ticket_worker": "process_not_alive",
        },
    }
    with patch.object(runner, "_runtime_health_body", return_value=(503, body)):
        assert runner._verify_recovery_runtime_health(runtime, profile) == "ticket_worker_provider_auth_degraded"
    bad = json.loads(json.dumps(body))
    bad["ticket_worker"]["last_restart_reason"] = "different_failure"
    with patch.object(runner, "_runtime_health_body", return_value=(503, bad)):
        try:
            runner._verify_recovery_runtime_health(runtime, profile)
        except runner.ReleaseManagerError:
            pass
        else:
            raise AssertionError("unexpected runtime degradation must fail closed")
