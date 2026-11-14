"""Synthetic integration of signed ONE-owner plan with current Stage A0 read gates.

This is NOT an active root worker and cannot perform a privileged release.
"""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import copy

import pytest

from implementation.kernel.signed_owner_release import canonical
from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a_admission as admission
from tools.pmv4_stage_a_bounded_plan_preflight import (
    StageABoundedPlanDenied, verify_bounded_plan_stage_a0_readonly,
)
from test_pmv4_owner_objective_end_to_end import (
    enrolled, enroll, observed, AT,
)
from orchestrator.pmv4_objective_scope import issue_proved_objective_step


@pytest.fixture
def rig(enrolled, tmp_path, monkeypatch):
    env=enrolled
    freeze=tmp_path/"freeze"
    hold=tmp_path/"hold"
    freeze.write_bytes(b"synthetic frozen root safety")
    hold.write_bytes(b"synthetic promotion hold")
    sh=sha256(freeze.read_bytes()).hexdigest()
    hh=sha256(hold.read_bytes()).hexdigest()
    source_sha=env["objective"].candidate_sha
    scope={
        "schema_version":"1.0",
        "phase":"stage-a0-independent-trusted-host-bootstrap",
        "candidate_sha":source_sha,
        "rollback_sha":packet.EMPTY_BASELINE,
        "host_code_bundle_sha256":"f"*64,
        "install_approval_required":True,
        "production_freeze_change":False,
        "production_services_restart":False,
        "breaker_mutation":False,
        "owner_issuer_enabled":False,
        "provider_writes":False,
        "installer_authority":"native-root-signed-exact-owner-transaction-only",
    }
    scope["scope_sha256"]=packet._digest(packet._canonical(scope))
    manifest=admission.exact_stage_a_manifest(scope,sh)
    action=replace(env["objective"].actions[3],
                   scope_sha256=scope["scope_sha256"],
                   artifact_sha256=sha256(canonical(manifest)).hexdigest())
    env["objective"]=replace(env["objective"],
        rollback_sha=packet.EMPTY_BASELINE,
        freeze_sha256=sh,hold_sha256=hh,
        actions=env["objective"].actions[:3]+(action,))
    monkeypatch.setattr(packet,"verify_exact_repository_head",
                        lambda repo,sha: None if sha==source_sha else
                        (_ for _ in ()).throw(PermissionError("protected main changed")))
    monkeypatch.setattr(packet,"build_scope",
                        lambda repo,sha: copy.deepcopy(scope))
    parent=enroll(env)
    step=issue_proved_objective_step(
        objective=env["objective"],ledger=env["ledger"],
        signed_parent=parent,signing_key=env["owner_key"],
        pinned_public_key=env["owner_key"].public_key(),
        action_index=3,observed=observed(env["objective"],3),
        verified_prior_steps=frozenset({0,1,2}),at=AT,
    )
    health={
        "preflight_evidence_satisfied":True,
        "stage_a_empty_baseline_verified":True,
        "root_only_target_parent_verification_needed":False,
        "breaker_state":"closed",
        "installation_ready":False,
        "production_install_authorized":False,
        "runtime_healthy":True,
        "mcp_running":True,
        "worker_scan_fresh":True,
        "freeze_sha256":sh,"promotion_hold_sha256":hh,
    }
    args={
        "repo":tmp_path,"candidate_sha":source_sha,"scope":scope,
        "exact_manifest":manifest,"objective":env["objective"],
        "action_index":3,"signed_parent":parent,"signed_step":step,
        "owner_plan_ledger":env["ledger"],
        "pinned_public_key":env["owner_key"].public_key(),
        "freeze_path":freeze,"hold_path":hold,"native_root_health":health,
        "verified_prior_steps":frozenset({0,1,2}),
        "consumed_step_claims":frozenset(),
        "protected_main_ci_check":lambda sha:sha==source_sha,
        "at":AT,"production":False,
    }
    return args


def test_existing_stage_a0_manifest_health_and_signed_plan_all_pass_readonly(rig):
    result=verify_bounded_plan_stage_a0_readonly(**rig)
    assert result["status"]=="source_only_bounded_plan_preflight_verified"
    assert result["action"]=="pmv4-stage-a0-step-3"
    assert result["no_production_authority"] is True
    assert result["root_mutation"] is False


def test_production_cannot_use_source_only_approval_adapter(rig):
    with pytest.raises(StageABoundedPlanDenied,match="ROOT_POLICY_NOT_DEPLOYED"):
        verify_bounded_plan_stage_a0_readonly(**{**rig,"production":True})


@pytest.mark.parametrize("fault",[
    "ci","freeze","hold","scope","manifest","breaker","ticket",
    "mcp","scan","root","rollback","prior","replay","expired",
])
def test_stage_a0_preflight_negative_boundary_denies(rig,fault):
    args=copy.copy(rig)
    if fault=="ci":
        args["protected_main_ci_check"]=lambda _:False
    elif fault=="freeze":
        args["freeze_path"].write_bytes(b"torn root freeze")
    elif fault=="hold":
        args["hold_path"].write_bytes(b"unexpected hold change")
    elif fault=="scope":
        args["scope"]={**rig["scope"],"scope_sha256":"0"*64}
    elif fault=="manifest":
        args["exact_manifest"]={**rig["exact_manifest"],"protected_services_restart":True}
    elif fault=="breaker":
        args["native_root_health"]={**rig["native_root_health"],"breaker_state":"open"}
    elif fault=="ticket":
        args["native_root_health"]={**rig["native_root_health"],"runtime_healthy":False}
    elif fault=="mcp":
        args["native_root_health"]={**rig["native_root_health"],"mcp_running":False}
    elif fault=="scan":
        args["native_root_health"]={**rig["native_root_health"],"worker_scan_fresh":False}
    elif fault=="root":
        args["native_root_health"]={**rig["native_root_health"],"stage_a_empty_baseline_verified":False}
    elif fault=="rollback":
        args["candidate_sha"]="d"*40
    elif fault=="prior":
        args["verified_prior_steps"]=frozenset({0,2})
    elif fault=="replay":
        args["consumed_step_claims"]=frozenset({rig["signed_step"]["payload"]["step_claim_id"]})
    elif fault=="expired":
        args["at"]=AT+timedelta(hours=1)
    with pytest.raises((StageABoundedPlanDenied,PermissionError,ValueError)):
        verify_bounded_plan_stage_a0_readonly(**args)
