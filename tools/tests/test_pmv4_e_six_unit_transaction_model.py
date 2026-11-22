"""Negative and recovery tests for source-only PMv4 E six-unit transaction model."""
from __future__ import annotations

from dataclasses import replace
import pytest

from tools import pmv4_e_six_unit_transaction_model as model


def test_exact_six_trigger_delta_without_provider_or_core_changes():
    result=model.summary()
    assert result["old_triggers"]==6
    assert result["new_triggers"]==6
    assert result["injected_failures_restored"]==7
    assert result["exact_rollback"] is True
    assert result["protected_core_mcp_unchanged"] is True
    assert result["freeze_unchanged"] is True
    assert result["ticket_owner_unchanged"] is True
    assert result["production_mutations"] is False
    assert result["root_transaction_implemented"] is False
    assert result["live_parity_accepted"] is False


@pytest.mark.parametrize("step",(
    "stage_new_inert","capture_checkpoint","disable_legacy",
    "commit_exact_policy","publish_root_acceptance",
    "activate_replacement","postflight",
))
def test_every_failed_step_restores_byte_equivalent_baseline(step):
    baseline=model.baseline()
    with pytest.raises(model.TransactionDenied) as err:
        model.cutover(baseline,fail_after=step)
    assert err.value.recovery_snapshot==baseline
    assert err.value.completed_steps[-1]==step


def test_no_new_dispatch_before_root_acceptance():
    old=model.baseline()
    with pytest.raises(model.TransactionDenied,match="NEW_DISPATCH_BEFORE_ACCEPTANCE"):
        replace(old,active_user=old.active_user|model.NEW_USER).verify()


def test_no_old_dispatch_after_root_acceptance():
    accepted,_=model.cutover(model.baseline())
    with pytest.raises(model.TransactionDenied,match="DUPLICATE_OLD_AFTER_ACCEPTANCE"):
        replace(accepted,active_root=accepted.active_root|model.OLD_ROOT).verify()


def test_new_controls_must_be_active_after_accepted_cutover():
    accepted,_=model.cutover(model.baseline())
    with pytest.raises(model.TransactionDenied,match="REPLACEMENT_NOT_ACTIVE"):
        replace(accepted,active_user=accepted.active_user-model.NEW_USER).verify()


def test_no_unapproved_or_repeated_cutover():
    prior=model.baseline()
    with pytest.raises(model.TransactionDenied,match="NEW_EXACT_OWNER_GRANT_REQUIRED"):
        model.cutover(replace(prior,owner_grant=False))
    accepted,_=model.cutover(prior)
    with pytest.raises(model.TransactionDenied,match="NEW_EXACT_OWNER_GRANT_REQUIRED"):
        model.cutover(accepted)


def test_changed_old_baseline_denies():
    b=model.baseline()
    with pytest.raises(model.TransactionDenied,match="BASELINE_CHANGED"):
        model.cutover(replace(b,enabled_user=frozenset()))


def test_rollback_refuses_changed_protected_components():
    b=model.baseline()
    accepted,_=model.cutover(b)
    with pytest.raises(model.TransactionDenied,match="PROTECTED_STATE_CHANGED"):
        model.rollback(replace(accepted,core_sha="e"*40),b)


def test_recovery_preserves_existing_audit_chain_and_exact_prestate():
    b=replace(model.baseline(),audit_chain="1"*64)
    accepted,_=model.cutover(b)
    assert accepted.audit_chain != b.audit_chain
    assert model.rollback(accepted,b)==b


def test_model_uses_no_provider_host_or_root_mutation():
    from pathlib import Path
    c=(Path(__file__).resolve().parents[2]/"tools/pmv4_e_six_unit_transaction_model.py").read_text()
    for denied in ("subprocess.run(","os.system(","systemctl start",
                   "systemctl disable","docker restart","sudo ",
                   "requests.post(","os.replace("):
        assert denied not in c
