"""One Entra-format Owner decision -> one native Stage A0 create/rollback.

This is an exact ephemeral /tmp native acceptance, not an active root path.
The real production installer must reject schema-v2 even if given a perfectly
verified parent receipt/step until separately reviewed root policy is deployed.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from implementation.kernel.signed_owner_release import canonical
from orchestrator.pmv4_objective_scope import issue_proved_objective_step
from tools import pmv4_stage_a_native_install as native
from tools import pmv4_stage_a_packet as packet
from test_pmv4_owner_objective_end_to_end import (
    AT, APPROVAL_ID, enrolled, enroll, observed,
)
from test_pmv4_stage_a_native_install import rig as native_rig


@pytest.fixture
def plan_install(enrolled, native_rig, tmp_path):
    env = enrolled
    sandbox, scope, freeze, health, kwargs, native_installer = native_rig
    hold = tmp_path / "protected-promotion-hold"
    hold.write_bytes(b"independent protected hold")

    candidate = kwargs["candidate_sha"]
    scoped = replace(
        env["objective"].actions[3],
        scope_sha256=scope["scope_sha256"],
        artifact_sha256=sha256(canonical(kwargs["manifest"])).hexdigest(),
    )
    objective = replace(
        env["objective"],
        candidate_sha=candidate,
        rollback_sha=packet.EMPTY_BASELINE,
        freeze_sha256=sha256(freeze.read_bytes()).hexdigest(),
        hold_sha256=sha256(hold.read_bytes()).hexdigest(),
        actions=env["objective"].actions[:3] + (scoped,),
    )
    env["objective"] = objective
    parent = enroll(env)
    step = issue_proved_objective_step(
        objective=objective,
        ledger=env["ledger"],
        signed_parent=parent,
        signing_key=env["owner_key"],
        pinned_public_key=env["owner_key"].public_key(),
        action_index=3,
        observed=observed(objective, 3),
        verified_prior_steps=frozenset({0, 1, 2}),
        at=AT,
    )
    health.update({
        "runtime_healthy": True, "mcp_running": True,
        "worker_scan_fresh": True,
        "promotion_hold_sha256": sha256(hold.read_bytes()).hexdigest(),
    })

    def installer():
        return native.NativeStageAInstaller(
            production=False, sandbox=sandbox,
            old_lock=native_installer().old_lock,
            owner_metadata=False,
            root_health=lambda: health.copy(),
            at=AT + timedelta(seconds=30),
        )
    plan = {
        "objective": objective,
        "action_index": 3,
        "signed_parent": parent,
        "ledger": env["ledger"],
        "pinned_public_key": env["owner_key"].public_key(),
        "verified_prior_steps": frozenset({0, 1, 2}),
        "consumed_step_claims": frozenset(),
        "hold_path": hold,
    }
    arguments = {
        **kwargs, "signed_proof": step,
        "approval_public_key": None,
        "bounded_plan_evidence": plan,
    }
    return env, installer, sandbox, scope, arguments, health, plan, step, hold


def test_one_human_decision_native_install_journal_and_empty_recovery(plan_install):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    assert len(env["consents"]) == 1
    result = factory().install(**args)
    assert result["status"] == "installed"
    assert result["owner_approval_id"] == APPROVAL_ID
    assert result["production_mutation"] is False
    j = factory()._journal(args["candidate_sha"])
    events = factory()._events(j)
    assert events[0]["owner_approval_id"] == APPROVAL_ID
    assert events[-1]["event"] == "verified_installed"
    assert events[-1]["signed_proof_sha256"] == sha256(canonical(step)).hexdigest()
    assert len(env["consents"]) == 1
    with pytest.raises(native.StageANativeDenied, match="EXISTING_JOURNAL"):
        factory().install(**args)
    outcome = factory().recover_empty(
        scope=scope,
        confirmed_approval_id=APPROVAL_ID,
        confirmed_proof_sha256=sha256(canonical(step)).hexdigest(),
    )
    assert outcome["status"] == "empty_baseline_restored"
    assert not any(factory()._map(name).exists()
                   for name in (packet.HOST_CODE, packet.ROOT, packet.ETC))
    assert len(env["consents"]) == 1


@pytest.mark.parametrize("tamper", [
    "prior", "replay", "hold", "runtime", "mcp", "ci",
    "changed_step", "changed_parent", "revoked", "extra_field",
    "legacy_test_pub",
])
def test_no_native_mutation_on_invalid_plan_evidence(plan_install, tamper):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    args = args.copy()
    plan = plan.copy()
    args["bounded_plan_evidence"] = plan
    if tamper == "prior":
        plan["verified_prior_steps"] = frozenset({0, 2})
    elif tamper == "replay":
        plan["consumed_step_claims"] = frozenset({step["payload"]["step_claim_id"]})
    elif tamper == "hold":
        hold.write_bytes(b"tampered protected hold")
    elif tamper == "runtime":
        health["runtime_healthy"] = False
    elif tamper == "mcp":
        health["mcp_running"] = False
    elif tamper == "ci":
        args["ci_check"] = lambda _: False
    elif tamper == "changed_step":
        args["signed_proof"] = {**step, "signature_base64url": "A"*86}
    elif tamper == "changed_parent":
        plan["signed_parent"] = {
            **plan["signed_parent"], "signature_base64url": "A"*86
        }
    elif tamper == "revoked":
        env["ledger"].revoke(
            env["objective"].plan_id, at=AT + timedelta(seconds=1),
            reason="test revoked",
        )
    elif tamper == "extra_field":
        plan["shell_command"] = "sh -c arbitrary"
    elif tamper == "legacy_test_pub":
        args["approval_public_key"] = env["owner_key"].public_key()

    with pytest.raises((PermissionError, ValueError, TypeError)):
        factory().install(**args)
    assert list(sandbox.glob("*.jsonl")) == []
    assert not any((sandbox / name.lstrip("/")).exists()
                   for name in (packet.ROOT, packet.HOST_CODE, packet.ETC))


def test_production_plan_path_denied_prior_to_root_mutation(plan_install):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    native_installer = factory()
    # Production root path is deliberately not installable from this source
    # checkout. Force the production gate to confirm it rejects before the
    # test-only path can open a lock, journal or arbitrary root destination.
    native_installer.production = True
    with pytest.raises(native.StageANativeDenied,
                       match="STAGE_A_PLAN_ROOT_POLICY_NOT_DEPLOYED"):
        native_installer.install(**args)
    assert list(sandbox.glob("*.jsonl")) == []
