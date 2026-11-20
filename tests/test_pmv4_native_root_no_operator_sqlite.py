"""Source-only exact native root verifier never trusts raw operator grant DB.

The trusted signer issued a fresh Ed25519 current grant after checking SQLite
and revocation. Only the SIGNED, source-bound attestation and the read-only
append-only plan journal are needed at root admission. Live production root
policy remains disabled.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tools.pmv4_one_owner_native_root_admission import (
    OneOwnerNativeRootAdmissionDenied,
    verify_sandbox_native_root_action,
)
from test_pmv4_one_consent_native_sandbox_transaction import (
    plan_install, enrolled, native_rig,
)
from test_pmv4_owner_objective_end_to_end import AT


def _root_call(rig, **overrides):
    env, factory, sandbox, scope, args, health, plan, step, hold = rig
    values = {
        "repo": args["repo"], "candidate_sha": args["candidate_sha"],
        "reviewed_scope": scope, "exact_manifest": args["manifest"],
        "freeze_path": args["freeze_path"], "hold_path": hold,
        "native_root_health": health,
        "objective": env["objective"],
        "signed_parent": plan["signed_parent"],
        "signed_step": step,
        "current_signed_grant": plan["current_grant_attestation"],
        "root_readonly_journal": plan["plan_journal"],
        "pinned_public_key": env["owner_key"].public_key(),
        "action_index": 3,
        "protected_main_ci_check": args["ci_check"],
        "at": AT + timedelta(seconds=30),
        "production": False,
    }
    values.update(overrides)
    return verify_sandbox_native_root_action(**values)


def test_native_root_admission_requires_zero_raw_operator_sqlite_queries(
    plan_install, monkeypatch,
):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    # Only the issuer had access to operator-owned SQLite when it signed the
    # parent and CURRENT grant. The root verifier must have no SQL dependency.
    def forbidden(*args, **kwargs):
        raise AssertionError("ROOT must not read operator-owned SQLite")
    monkeypatch.setattr(env["ledger"], "require_grant", forbidden)
    monkeypatch.setattr(env["ledger"],
                        "authenticated_owner_objective_receipt", forbidden)
    monkeypatch.setattr(env["ledger"], "decision_receipt", forbidden)
    result = _root_call(plan_install)
    assert result["status"] == "read_only_native_exact_one_owner_plan_verified"
    assert result["parent_approval_id"] == plan["signed_parent"]["payload"]["parent_approval_id"]
    assert result["root_mutation"] is False
    assert result["production_root_authority"] is False
    assert result["root_journal_head_sha256"]


@pytest.mark.parametrize("fault", [
    "wrong_scope", "wrong_manifest", "forged_parent", "forged_child",
    "forged_current_grant", "foreign_candidate", "runtime_unhealthy",
    "mcp_unhealthy", "drift_broken", "changed_hold", "wrong_step",
    "missing_predecessors", "ci_unverified",
])
def test_root_no_sql_verifier_denies_all_unreviewed_native_mutations(plan_install,
                                                                    fault, tmp_path):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    args_root = {}
    if fault == "wrong_scope":
        args_root["reviewed_scope"] = {**scope, "scope_sha256": "0" * 64}
    elif fault == "wrong_manifest":
        args_root["exact_manifest"] = {**args["manifest"], "standing_authority": True}
    elif fault == "forged_parent":
        args_root["signed_parent"] = {**plan["signed_parent"],
                                       "signature_base64url": "A"*86}
    elif fault == "forged_child":
        args_root["signed_step"] = {**step, "signature_base64url": "A"*86}
    elif fault == "forged_current_grant":
        args_root["current_signed_grant"] = {
            **plan["current_grant_attestation"], "signature_base64url": "A"*86,
        }
    elif fault == "foreign_candidate":
        args_root["candidate_sha"] = "f"*40
    elif fault == "runtime_unhealthy":
        args_root["native_root_health"] = {**health, "runtime_healthy": False}
    elif fault == "mcp_unhealthy":
        args_root["native_root_health"] = {**health, "mcp_running": False}
    elif fault == "drift_broken":
        args_root["native_root_health"] = {**health, "breaker_state": "open"}
    elif fault == "changed_hold":
        hold.write_bytes(b"owner protected hold drift")
    elif fault == "wrong_step":
        args_root["action_index"] = 1
    elif fault == "missing_predecessors":
        args_root["root_readonly_journal"] = type(plan["plan_journal"])(
            directory=tmp_path, objective=env["objective"],
            signed_parent=plan["signed_parent"],
            pinned_public_key=env["owner_key"].public_key(),
            owner_ledger=env["ledger"], at=AT,
        )
    elif fault == "ci_unverified":
        args_root["protected_main_ci_check"] = lambda sha: False
    with pytest.raises((PermissionError, ValueError, OSError)):
        _root_call(plan_install, **args_root)
    assert list(sandbox.glob("*.jsonl")) == []


def test_production_root_policy_absence_denies_even_correct_enrolled_plan(plan_install):
    with pytest.raises(OneOwnerNativeRootAdmissionDenied,
                       match="ROOT_POLICY_NOT_DEPLOYED"):
        _root_call(plan_install, production=True)
