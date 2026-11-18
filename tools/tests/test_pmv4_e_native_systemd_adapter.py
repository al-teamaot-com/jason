"""Stage E native host callback: isolated six-unit transition and inverse tests.

No production systemd or provider access. The previously accepted signed
generic controller remains responsible for authenticated Owner preflight,
'started' receipt, host/freeze locks, re-entry and interrupted recovery.
"""
from __future__ import annotations
from dataclasses import replace
import pytest

from tools import pmv4_e_native_systemd_adapter as adapter

CANDIDATE="b"*40
ROLLBACK="a"*40
SCOPE="c"*64


class FakeRootBackend:
    def __init__(self,fail_at=None):
        self.before=adapter.Before(
            active=frozenset(adapter.OLD),
            enabled=frozenset(adapter.OLD),
            policy_sha256="d"*64,source_sha=ROLLBACK,
            freeze_sha256="e"*64,protected_fingerprint="f"*64,
            claims_fingerprint="1"*64,marker_present=False,
        )
        self.before_image=None
        self.active=set(adapter.OLD)
        self.enabled=set(adapter.OLD)
        self.marker=False
        self.steps=[]
        self.fail_at=fail_at
        self.issued_signer=False
        self.changed_protected=False
        self.changed_freeze=False
        self.policy="legacy"
        self.staged=False
        self.claims_quiesced=False
        self.recovered=False

    def root_install_verified(self):return True
    def exclusive_host_lock_held(self):return True
    def freeze_lock_held(self):return True
    def read_protected_before(self):return self.before
    def trusted_exact_plan(self,*args):return args[:3]==(CANDIDATE,ROLLBACK,SCOPE)
    def native_started_receipt_verified(self,*args):return args==(CANDIDATE,ROLLBACK,SCOPE)
    def original_signed_started_receipt_verified(self,*args):return args==(ROLLBACK,SCOPE)
    def verify_baseline(self,b):
        assert b==self.before
        assert self.active==set(adapter.OLD)
    def active_triggers(self):return frozenset(self.active)
    def persist_root_before_image(self,b):self.before_image=b
    def quiesce_and_verify_claims(self):self.claims_quiesced=True
    def stage_exact_new_units(self,u,r):self.staged=True
    def stop_disable_exact(self,u,r):
        self.active.difference_update(u+r)
        self.enabled.difference_update(u+r)
    def commit_reviewed_policy_and_code(self,*args):self.policy="replacement"
    def commit_reviewed_root_marker(self,*args):self.marker=True
    def enable_start_exact(self,u,r):
        assert self.staged
        self.active.update(u+r)
        self.enabled.update(u+r)
    def verify_six_callbacks_and_protected(self,b):
        assert self.active==set(adapter.NEW)
    def freeze_and_protected_unchanged(self,b):
        return not self.changed_protected and not self.changed_freeze
    def append_native_step_receipt(self,s,b):
        self.steps.append(s)
        if self.fail_at==s:
            raise RuntimeError("INJECTED_"+s)
    def read_immutable_root_before_image(self):return self.before_image
    def block_new_dispatch(self):self.steps.append("block_new_dispatch")
    def revoke_exact_marker_before_legacy(self):
        assert not (self.active&adapter.NEW)
        self.marker=False
    def restore_reviewed_policy_code_and_watchdog(self,b):self.policy="legacy"
    def restore_six_original_units_and_states(self,b):
        assert not self.marker
        self.active=set(b.active)
        self.enabled=set(b.enabled)
    def verify_rollback(self,b):
        assert self.policy=="legacy"
        assert self.active==set(adapter.OLD)
        assert not self.marker
    def append_native_recovery_receipt(self,b):self.recovered=True


def callback(backend,*,grant=True):
    return adapter.StageEUnitAdapter(backend,native_invocation=lambda:grant)


def promote(root):
    return callback(root).activate(
        candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
        scope_sha256=SCOPE,action=adapter.PINNED_ACTION)


def recover(root):
    return callback(root).restore(rollback_sha=ROLLBACK,scope_sha256=SCOPE)


def test_existing_native_boundary_six_replacements_exact():
    backend=FakeRootBackend()
    result=promote(backend)
    assert result["status"]=="native_stage_e_six_unit_candidate_verified"
    assert result["completed_steps"]==adapter.STEPS
    assert backend.steps==list(adapter.STEPS)
    assert backend.active==set(adapter.NEW)
    assert backend.marker is True
    assert backend.policy=="replacement"
    assert backend.before_image==backend.before
    assert backend.issued_signer is False


@pytest.mark.parametrize("fault",adapter.STEPS)
def test_all_eight_phase_failures_have_exact_native_inverse(fault):
    backend=FakeRootBackend(fail_at=fault)
    with pytest.raises(RuntimeError,match="INJECTED_"+fault):
        promote(backend)
    assert backend.before_image==backend.before
    recovery=recover(backend)
    assert recovery["status"]=="native_stage_e_six_unit_rollback_verified"
    assert backend.active==set(adapter.OLD)
    assert backend.enabled==set(adapter.OLD)
    assert backend.policy=="legacy"
    assert backend.marker is False
    assert backend.recovered
    assert backend.issued_signer is False


def test_no_exact_signed_native_boundary_denies_before_mutation():
    root=FakeRootBackend()
    with pytest.raises(adapter.StageEAdapterDenied,match="NATIVE_SIGNED_TRANSACTION_BOUNDARY_REQUIRED"):
        callback(root,grant=False).activate(
            candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
            scope_sha256=SCOPE,action=adapter.PINNED_ACTION)
    assert not root.steps and root.before_image is None


@pytest.mark.parametrize("change",["candidate","rollback","scope","action"])
def test_wrong_exact_release_scope_denied(change):
    root=FakeRootBackend()
    args=dict(candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
              scope_sha256=SCOPE,action=adapter.PINNED_ACTION)
    args[dict(candidate="candidate_sha",rollback="rollback_sha",
              scope="scope_sha256",action="action")[change]]="wrong"
    with pytest.raises(adapter.StageEAdapterDenied):
        callback(root).activate(**args)
    assert root.before_image is None and not root.steps


def test_missing_native_receipt_denies_before_mutation():
    root=FakeRootBackend()
    root.native_started_receipt_verified=lambda *args:False
    with pytest.raises(adapter.StageEAdapterDenied,match="SIGNED_NATIVE_RECEIPT_MISSING"):
        promote(root)
    assert root.before_image is None


def test_missing_shared_host_lock_denies():
    root=FakeRootBackend()
    root.exclusive_host_lock_held=lambda:False
    with pytest.raises(adapter.StageEAdapterDenied,match="SHARED_HOST_LOCK_REQUIRED"):
        promote(root)


def test_preexisting_replacement_dispatch_denied():
    root=FakeRootBackend()
    root.before=replace(root.before,active=root.before.active|adapter.NEW)
    with pytest.raises(adapter.StageEAdapterDenied,match="REPLACEMENTS_ALREADY_DISPATCHING"):
        promote(root)


def test_missing_durable_snapshot_prevents_unsafe_recovery():
    root=FakeRootBackend()
    with pytest.raises(adapter.StageEAdapterDenied,match="DURABLE_BEFORE_IMAGE_MISSING"):
        recover(root)


def test_recovery_fails_if_protected_changed():
    root=FakeRootBackend()
    promote(root)
    root.changed_protected=True
    with pytest.raises(adapter.StageEAdapterDenied,match="ROLLBACK_NOT_EXACT"):
        recover(root)


def test_exact_legacy_restoration_precedes_unblocking():
    root=FakeRootBackend()
    promote(root)
    root.steps=[]
    recover(root)
    assert root.steps==["block_new_dispatch"]
    assert root.active==set(adapter.OLD)
    assert root.marker is False
