"""Three REAL durable stage effects under one Owner consent — sandbox only.

All test mutations are private disposable /tmp files; production root disabled.
Failed/stale/foreign/replayed/crashed transactions never silently complete.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from implementation.mcp_service.src.jason_mcp.pmv4_bounded_owner_bridge import (
    authorize_one_bounded_objective_from_mcp,
)
from kernel.signed_owner_release import OWNER_PRINCIPAL
from orchestrator.pmv4_objective_scope import issue_proved_objective_step
from tools.pmv4_a0_atomic_plan_transaction import (
    A0AtomicSandboxTransaction, A0AtomicTransactionDenied,
)
from tools.pmv4_bounded_plan_journal import BoundedPlanJournal
from tools.pmv4_current_grant_attestation import issue_current_grant_attestation
from tools.pmv4_stage_a0_one_owner_review import build_reviewed_plan
from test_pmv4_owner_objective_end_to_end import AT, APPROVAL_ID, enrolled, observed


class ThreeRealDisposableFileEffects:
    def __init__(self, root: Path, *, fault: int | None = None) -> None:
        self.root = root
        self.fault = fault
        self.calls: list[tuple[str, int]] = []
        self.sources = [b"root bootstrap test blob", b"immutable source test blob",
                        b"native A0 test blob"]

    def _path(self, index: int) -> Path:
        return self.root / ("exact-stage-" + str(index))

    def apply(self, index, evidence):
        self.calls.append(("apply", index))
        if index != sum(1 for x in self.root.glob("exact-stage-*")):
            raise AssertionError("not sequential")
        p = self._path(index)
        with p.open("xb") as f:
            f.write(self.sources[index])
            f.flush()
            import os
            os.fsync(f.fileno())
        if self.fault == index:
            raise InterruptedError("simulated interrupted native write")
        return {"exact_sha256":sha256(self.sources[index]).hexdigest(),
                "step_index":index}

    def verify_installed(self, index):
        p = self._path(index)
        return p.is_file() and not p.is_symlink() and p.read_bytes() == self.sources[index]

    def rollback_exact(self, index):
        self.calls.append(("rollback", index))
        if not self.verify_installed(index):
            raise PermissionError("foreign replacement: cannot delete")
        self._path(index).unlink()
        return {"step_index":index, "recovered_exactly":True}

    def verify_absent(self, index):
        p = self._path(index)
        return not p.exists() and not p.is_symlink()


@pytest.fixture
def atomic(enrolled, tmp_path):
    env = enrolled
    reviewed = build_reviewed_plan(expires_at=AT + timedelta(minutes=30))
    # Disposable fixture uses synthetic protected byte strings. Never present
    # synthetic freeze evidence as actual live proof or authorize production.
    env["objective"] = replace(
        reviewed,
        freeze_sha256=sha256(b"synthetic-freeze").hexdigest(),
        hold_sha256=sha256(b"synthetic-hold").hexdigest(),
    )
    objective = env["objective"]
    issuer = authorize_one_bounded_objective_from_mcp(
        bearer_token=env["token"], verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot", verify_entra_bearer=env["verifier"],
        exact_owner_consent=lambda shown: env["consents"].append(shown) or True,
        protected_main_check=lambda sha: sha == objective.candidate_sha,
        objective=objective, ledger=env["ledger"],
        signing_key=env["owner_key"], approval_id=APPROVAL_ID,
        affirmative_decision="approve_exact_one_pmv4_objective", at=AT,
    )
    signed_parent = issuer["signed_parent"]
    directory = tmp_path / "atomic-a0-journal"
    directory.mkdir(mode=0o700)
    plan_dir = tmp_path / "sealed-original-owner-plan"
    plan_dir.mkdir(mode=0o700)
    plan = BoundedPlanJournal(
        directory=plan_dir, objective=objective, signed_parent=signed_parent,
        pinned_public_key=env["owner_key"].public_key(),
        owner_ledger=env["ledger"], at=AT,
    )
    coordinator = A0AtomicSandboxTransaction(
        directory=directory, objective=objective,
        signed_parent=signed_parent,
        pinned_public_key=env["owner_key"].public_key(),
        bounded_journal=plan,
    )
    def evidence(index: int, verified_prior: frozenset[int]):
        signed = issue_proved_objective_step(
            objective=objective, ledger=env["ledger"],
            signed_parent=signed_parent, signing_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=index, observed=observed(objective,index),
            verified_prior_steps=verified_prior,
            at=AT,
        )
        grant = issue_current_grant_attestation(
            objective=objective, signed_parent=signed_parent,
            ledger=env["ledger"], signer_private_key=env["owner_key"],
            pinned_public_key=env["owner_key"].public_key(),
            action_index=index, at=AT,
        )
        return {"signed_step":signed, "current_signed_grant":grant}
    return env, coordinator, evidence, tmp_path


def test_one_verified_owner_decision_three_actual_exact_file_effects(atomic):
    env, tx, evidence, directory = atomic
    a = ThreeRealDisposableFileEffects(directory)
    done = tx.execute(adapters=a, stage_provider=evidence,
                      at=AT + timedelta(seconds=1))
    assert done["status"] == "three_exact_stage_actions_verified_together"
    assert done["owner_approval_id"] == APPROVAL_ID
    assert done["production_mutation"] is False
    assert done["additional_human_consents"] == 0
    assert len(env["consents"]) == 1
    assert all(a.verify_installed(i) for i in range(3))
    assert [r["action"] for r in tx._read_events()].count("installed") == 3
    assert tx._read_events()[-1]["action"] == "committed"
    with pytest.raises(A0AtomicTransactionDenied, match="ONE_RELEASE_ALREADY_CLAIMED"):
        tx.execute(adapters=a,stage_provider=evidence,
                   at=AT + timedelta(seconds=1))


@pytest.mark.parametrize("fault", [0, 1, 2])
def test_failure_at_any_stage_rolls_all_created_effects_to_absence(atomic, fault):
    env, tx, evidence, directory = atomic
    a = ThreeRealDisposableFileEffects(directory, fault=fault)
    with pytest.raises(InterruptedError):
        tx.execute(adapters=a, stage_provider=evidence,
                   at=AT + timedelta(seconds=1))
    assert tx._read_events()[-1]["action"] == "aborted"
    assert not any(a._path(i).exists() for i in range(3))
    assert len(env["consents"]) == 1
    with pytest.raises(A0AtomicTransactionDenied, match="ONE_RELEASE_ALREADY_CLAIMED"):
        tx.execute(adapters=a, stage_provider=evidence,
                   at=AT + timedelta(seconds=1))


def test_tampered_stage_receipt_denied_without_first_write(atomic):
    env, tx, source, directory = atomic
    a = ThreeRealDisposableFileEffects(directory)
    def forged(index, prior):
        e = source(index, prior)
        if index == 0:
            e["signed_step"] = {
                **e["signed_step"], "signature_base64url":"A"*86,
            }
        return e
    with pytest.raises(PermissionError):
        tx.execute(adapters=a,stage_provider=forged,
                   at=AT+timedelta(seconds=1))
    assert a.calls == []
    assert tx._read_events()[-1]["action"] == "aborted"


def test_foreign_object_after_failure_never_deleted_during_rollback(atomic):
    env, tx, source, directory = atomic
    a = ThreeRealDisposableFileEffects(directory)
    original_apply = a.apply
    def tampered_apply(index, evidence):
        result = original_apply(index, evidence)
        if index == 1:
            a._path(0).write_bytes(b"foreign replacement not ours")
            raise InterruptedError("foreign replacement after root write")
        return result
    a.apply = tampered_apply
    with pytest.raises(A0AtomicTransactionDenied, match="FOREIGN_OR_UNVERIFIED"):
        tx.execute(adapters=a,stage_provider=source,
                   at=AT+timedelta(seconds=1))
    assert a._path(0).read_bytes() == b"foreign replacement not ours"
    assert tx._read_events()[-1]["action"] == "requires_review"
    assert len(env["consents"]) == 1


def test_torn_journal_fails_closed_without_reissue(atomic):
    env, tx, evidence, directory = atomic
    a = ThreeRealDisposableFileEffects(directory)
    tx.execute(adapters=a,stage_provider=evidence,at=AT+timedelta(seconds=1))
    raw = tx.path.read_bytes()
    tx.path.write_bytes(raw[:-1])
    with pytest.raises(A0AtomicTransactionDenied, match="JOURNAL_TORN"):
        tx._read_events()
    with pytest.raises(A0AtomicTransactionDenied, match="ONE_RELEASE_ALREADY_CLAIMED"):
        tx.execute(adapters=a, stage_provider=evidence, at=AT+timedelta(seconds=1))


def test_one_stage_pending_abandoned_after_crash_reconciles_by_rollback(atomic):
    env, tx, evidence, directory = atomic
    a = ThreeRealDisposableFileEffects(directory)
    tx._append("begin", -1, {"stages":3})
    tx._append("intent", 0, {"scope_sha256":env["objective"].actions[0].scope_sha256})
    a.apply(0, {})
    out = tx.reconcile_interrupted(adapters=a)
    assert out["status"] == "exact_three_stage_rollback_verified"
    assert all(a.verify_absent(i) for i in range(3))
    assert tx._read_events()[-1]["action"] == "aborted"
    with pytest.raises(A0AtomicTransactionDenied, match="ALREADY_TERMINAL"):
        tx.reconcile_interrupted(adapters=a)


def test_preapproval_and_production_paths_remain_unavailable(atomic):
    env, tx, evidence, directory = atomic
    with pytest.raises(A0AtomicTransactionDenied, match="ROOT_CONSUMER_NOT_DEPLOYED"):
        A0AtomicSandboxTransaction(
            directory=tx.directory, objective=env["objective"],
            signed_parent=tx.signed_parent,
            pinned_public_key=env["owner_key"].public_key(),
            bounded_journal=tx.bounded, production=True,
        )
    assert tx.path.exists() is False
    assert len(env["consents"]) == 1
