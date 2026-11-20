"""Durable root-journal source acceptance, crash recovery and adversarial cases.

One synthetic Owner Entra decision is reused without renewed consent.
All tests use /tmp and operator-owned disposable evidence, never production.
"""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import pytest

from tools.pmv4_bounded_plan_journal import (
    BoundedPlanJournal, BoundedPlanJournalDenied,
)
from tools import pmv4_stage_a_native_install as native
from test_pmv4_one_consent_native_sandbox_transaction import (
    plan_install,
)
from test_pmv4_owner_objective_end_to_end import (
    AT, APPROVAL_ID, observed, enrolled,
)
from test_pmv4_stage_a_native_install import rig as native_rig


def _interrupt_final_receipt(plan_install, monkeypatch):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    ledger = plan["plan_journal"]
    original = ledger.complete

    def interrupted(**_):
        raise InterruptedError("simulated power loss after native verified")

    monkeypatch.setattr(ledger, "complete", interrupted)
    try:
        with pytest.raises(InterruptedError, match="simulated power loss"):
            factory().install(**args)
    finally:
        monkeypatch.setattr(ledger, "complete", original)
    stage_events = factory()._events(factory()._journal(args["candidate_sha"]))
    assert stage_events[-1]["event"] == "verified_installed"
    assert len(env["consents"]) == 1
    return env, factory, sandbox, scope, args, plan, step


def test_exact_native_success_can_be_reconciled_after_receipt_interruption(
    plan_install, monkeypatch,
):
    env, factory, sandbox, scope, args, plan, step = _interrupt_final_receipt(
        plan_install, monkeypatch,
    )
    with pytest.raises(BoundedPlanJournalDenied, match="RECOVERY_REQUIRES_NATIVE_READBACK"):
        plan["plan_journal"].fail_closed_reopen(at=AT + timedelta(seconds=30))
    with pytest.raises(BoundedPlanJournalDenied, match="PRIOR_STEPS_NOT_COMPLETE"):
        plan["plan_journal"].verified_snapshot(
            action_index=3, at=AT + timedelta(seconds=30),
        )
    outcome = factory().reconcile_bounded_plan_completion(
        plan_journal=plan["plan_journal"], action_index=3,
        scope=scope, signed_step=step,
    )
    assert outcome["status"] == "installed"
    assert outcome["owner_approval_id"] == APPROVAL_ID
    assert len(env["consents"]) == 1
    rows = [json.loads(x) for x in plan["plan_journal"].path.read_text().splitlines()]
    assert rows[-1]["event"] == "completed" and rows[-1]["step"] == 3
    with pytest.raises(BoundedPlanJournalDenied, match="NO_CURRENT_CLAIM"):
        factory().reconcile_bounded_plan_completion(
            plan_journal=plan["plan_journal"], action_index=3,
            scope=scope, signed_step=step,
        )


def test_failed_native_postflight_is_not_reconciled_as_success(plan_install):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    plan["plan_journal"].claim(
        action_index=3, signed_step=step, observed=observed(env["objective"], 3),
        at=AT,
    )
    with pytest.raises(native.StageANativeDenied, match="NATIVE_RECEIPT_UNVERIFIED"):
        factory().reconcile_bounded_plan_completion(
            plan_journal=plan["plan_journal"], action_index=3,
            scope=scope, signed_step=step,
        )
    assert list(sandbox.glob("*.jsonl")) == []


@pytest.mark.parametrize("fault", ["native_file", "wrong_child", "revoked", "bad_scope"])
def test_recovery_requires_exact_native_files_signatures_and_current_grant(
    plan_install, monkeypatch, fault,
):
    env, factory, sandbox, scope, args, plan, step = _interrupt_final_receipt(
        plan_install, monkeypatch,
    )
    if fault == "native_file":
        file = factory()._map(scope["files"][0]["path"])
        file.chmod(0o600)
        file.write_bytes(b"operator tampering")
    elif fault == "wrong_child":
        step = {**step, "signature_base64url": "A" * 86}
    elif fault == "revoked":
        env["ledger"].revoke(
            env["objective"].plan_id, at=AT + timedelta(seconds=1),
            reason="Owner-revoked objective",
        )
    elif fault == "bad_scope":
        scope = {**scope, "scope_sha256": "0" * 64}
    with pytest.raises((native.StageANativeDenied, BoundedPlanJournalDenied, PermissionError)):
        factory().reconcile_bounded_plan_completion(
            plan_journal=plan["plan_journal"], action_index=3,
            scope=scope, signed_step=step,
        )


@pytest.mark.parametrize("tamper", ["truncated", "modified_content", "foreign_event"])
def test_tamper_to_append_only_owner_journal_fails_closed(plan_install, tamper):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    log = plan["plan_journal"].path
    raw = log.read_bytes()
    if tamper == "truncated":
        log.write_bytes(raw[:-1])
    elif tamper == "modified_content":
        log.write_bytes(raw.replace(b'"event":"claimed"', b'"event":"bypass_"', 1))
    else:
        recs = [json.loads(x) for x in raw.splitlines()]
        last = recs[-1]
        forged = {
            "version": 1, "seq": len(recs)+1,
            "event": "foreign", "parent_hash": last["parent_hash"],
            "plan_fingerprint": last["plan_fingerprint"],
            "step": 3, "claim_id": "foreign",
            "evidence_sha256": "e"*64, "prev_sha256": last["hash"],
        }
        from implementation.kernel.signed_owner_release import canonical
        from hashlib import sha256
        forged["hash"] = sha256(canonical(forged)).hexdigest()
        log.write_bytes(raw + canonical(forged) + b"\n")
    with pytest.raises(BoundedPlanJournalDenied):
        plan["plan_journal"].verified_snapshot(action_index=3, at=AT)
    assert list(sandbox.glob("*.jsonl")) == []


def test_root_plan_revocation_prevents_new_native_claim(plan_install):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    j = plan["plan_journal"]
    j.revoke(at=AT, root_attested_revocation_sha256="f"*64)
    with pytest.raises(BoundedPlanJournalDenied, match="PRIOR_STEPS_NOT_COMPLETE"):
        j.verified_snapshot(action_index=3, at=AT)
    with pytest.raises(BoundedPlanJournalDenied):
        factory().install(**args)
    assert len(env["consents"]) == 1


def test_untrusted_directory_or_symlink_never_becomes_trusted_journal(
    plan_install, tmp_path,
):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    unsafe = tmp_path / "loose"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o777)
    with pytest.raises(BoundedPlanJournalDenied, match="UNTRUSTED_SANDBOX"):
        BoundedPlanJournal(
            directory=unsafe, objective=env["objective"],
            signed_parent=plan["signed_parent"],
            pinned_public_key=env["owner_key"].public_key(),
            owner_ledger=env["ledger"], at=AT,
        )
    unsafe.chmod(0o700)
    link = tmp_path / "foreign-symlink"
    link.symlink_to(unsafe)
    with pytest.raises(BoundedPlanJournalDenied, match="SANDBOX_REQUIRED"):
        BoundedPlanJournal(
            directory=link, objective=env["objective"],
            signed_parent=plan["signed_parent"],
            pinned_public_key=env["owner_key"].public_key(),
            owner_ledger=env["ledger"], at=AT,
        )


def test_production_root_consumer_remains_unavailable(plan_install):
    env, factory, sandbox, scope, args, health, plan, step, hold = plan_install
    instance = factory()
    instance.production = True
    with pytest.raises(native.StageANativeDenied, match="PLAN_ROOT_POLICY_NOT_DEPLOYED"):
        instance.reconcile_bounded_plan_completion(
            plan_journal=plan["plan_journal"], action_index=3,
            scope=scope, signed_step=step,
        )
