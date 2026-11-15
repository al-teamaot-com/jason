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
from tools.pmv4_bounded_plan_journal import (
    BoundedPlanJournal, BoundedPlanJournalDenied,
)
from tools.pmv4_current_grant_attestation import (
    issue_current_grant_attestation,
)
from test_pmv4_owner_objective_end_to_end import (
    AT, APPROVAL_ID, enrolled, enroll, observed,
)
from test_pmv4_stage_a_native_install import rig as native_rig
from implementation.mcp_service.src.jason_mcp.pmv4_bounded_owner_bridge import (
    authorize_one_bounded_objective_from_mcp,
)
from kernel.signed_owner_release import OWNER_PRINCIPAL


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
    # The ONE human action crosses the actual MCP identity binding before
    # native plan claims are derived. No synthetic per-step Owner approvals.
    issued = authorize_one_bounded_objective_from_mcp(
        bearer_token=env["token"],
        verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot",
        verify_entra_bearer=env["verifier"],
        exact_owner_consent=lambda displayed: env["consents"].append(displayed) or True,
        protected_main_check=lambda sha: sha == objective.candidate_sha,
        objective=objective, ledger=env["ledger"],
        signing_key=env["owner_key"], approval_id=APPROVAL_ID,
        affirmative_decision="approve_exact_one_pmv4_objective",
        at=AT,
    )
    assert issued["production_authorized"] is False
    parent = issued["signed_parent"]
    plan_dir = tmp_path / "sealed-plan-sandbox"
    plan_dir.mkdir(mode=0o700)
    plan_journal = BoundedPlanJournal(
        directory=plan_dir, objective=objective, signed_parent=parent,
        pinned_public_key=env["owner_key"].public_key(),
        owner_ledger=env["ledger"], at=AT,
    )
    # In source-only acceptance the preceding three components provide
    # synthetic results, deliberately NOT claimed as native production work.
    # The final Stage A0 step below executes the actual native install.
    for index in range(3):
        verified_prior = plan_journal.observe_prior(action_index=index, at=AT)
        previous_step = issue_proved_objective_step(
            objective=objective, ledger=env["ledger"], signed_parent=parent,
            signing_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=index, observed=observed(objective, index),
            verified_prior_steps=verified_prior, at=AT,
        )
        claimed = plan_journal.claim(
            action_index=index, signed_step=previous_step,
            observed=observed(objective, index), at=AT,
        )
        plan_journal.complete(
            action_index=index, claim_id=claimed["step_claim_id"],
            native_result={
                "status": "installed", "owner_approval_id": APPROVAL_ID,
                "production_mutation": False,
                "scope_sha256": objective.actions[index].scope_sha256,
            },
            at=AT,
        )
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
        "plan_journal": plan_journal,
        "hold_path": hold,
        "current_grant_attestation": issue_current_grant_attestation(
            objective=objective, signed_parent=parent, ledger=env["ledger"],
            signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=3, at=AT + timedelta(seconds=20),
        ),
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
    # The separate durable one-plan journal also proves the exact completed
    # chain without consulting any caller-provided prior-step list.
    rows = [__import__("json").loads(x) for x in plan["plan_journal"].path.read_text().splitlines()]
    assert len([x for x in rows if x["event"] == "completed"]) == 4
    assert rows[-1]["event"] == "completed" and rows[-1]["step"] == 3
    with pytest.raises(BoundedPlanJournalDenied, match="ROOT_READER_NOT_READY"):
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
    "legacy_test_pub", "attestation_forged", "attestation_stale",
])
def test_no_native_mutation_on_invalid_plan_evidence(plan_install, tamper):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    args = args.copy()
    plan = plan.copy()
    args["bounded_plan_evidence"] = plan
    if tamper == "prior":
        # Fresh durable root-sandbox ledger has NONE of the three successful
        # preceding steps. Supplying a forged prior list is not supported.
        other = plan["plan_journal"].directory.parent / "missing-prior-proof"
        other.mkdir(mode=0o700)
        plan["plan_journal"] = BoundedPlanJournal(
            directory=other, objective=env["objective"],
            signed_parent=plan["signed_parent"],
            pinned_public_key=env["owner_key"].public_key(),
            owner_ledger=env["ledger"], at=AT,
        )
    elif tamper == "replay":
        # Outstanding one-use claim makes a repeated native call fail closed.
        plan["plan_journal"].claim(
            action_index=3, signed_step=step,
            observed=observed(env["objective"], 3), at=AT,
        )
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
    elif tamper == "attestation_forged":
        plan["current_grant_attestation"] = {
            **plan["current_grant_attestation"],
            "signature_base64url": "A" * 86,
        }
    elif tamper == "attestation_stale":
        plan["current_grant_attestation"] = issue_current_grant_attestation(
            objective=env["objective"], signed_parent=plan["signed_parent"],
            ledger=env["ledger"], signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=3, at=AT,
        )

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
