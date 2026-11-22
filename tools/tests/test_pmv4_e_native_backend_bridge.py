"""Stage E end-to-end bridge into native lifecycle using disposable unit files."""
from __future__ import annotations
from pathlib import Path

import pytest

from tools import pmv4_e_native_systemd_adapter as adapter
from tools import pmv4_e_native_backend_bridge as bridge
from tools.tests.test_pmv4_e_native_systemd_adapter import (
    FakeRootBackend,CANDIDATE,ROLLBACK,SCOPE,
)
from tools.tests.test_pmv4_e_systemd_root_ops import make


class Native(FakeRootBackend):
    def __init__(self,sys,hashes,*,fail_at=None):
        super().__init__(fail_at=fail_at)
        self.sys=sys
        self.hashes=hashes

    def old_user_units(self):return adapter.OLD_USER
    def old_root_units(self):return adapter.OLD_ROOT
    def new_user_units(self):return adapter.NEW_USER
    def new_root_units(self):return adapter.NEW_ROOT
    def all_user_triggers(self):return adapter.OLD_USER+adapter.NEW_USER
    def all_root_triggers(self):return adapter.OLD_ROOT+adapter.NEW_ROOT
    def reviewed_twelve_unit_hashes(self):return self.hashes

    def commit_reviewed_root_marker(self,*args):
        assert self.sys.active==set(adapter.NEW_USER+adapter.NEW_ROOT)
        assert self.sys.enabled==set(adapter.NEW_USER+adapter.NEW_ROOT)
        self.marker=True

    def verify_six_callbacks_and_protected(self,b):
        assert self.sys.active==set(adapter.NEW_USER+adapter.NEW_ROOT)
        assert self.marker is False

    def verify_rollback(self,b):
        assert self.sys.active==set(adapter.OLD_USER+adapter.OLD_ROOT)
        assert self.policy=="legacy"
        assert not self.marker


def make_bridge(tmp_path,monkeypatch,*,fail_at=None):
    unit_ops,sys,hashes,generated,u,s=make(tmp_path,monkeypatch)
    native=Native(sys,hashes,fail_at=fail_at)
    wrapped=bridge.StageERootBridge(native_root=native,systemd=unit_ops)
    callback=adapter.StageEUnitAdapter(wrapped,native_invocation=lambda:True)
    return callback,native,sys,u,s


def promote(callback):
    return callback.activate(candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
        scope_sha256=SCOPE,action=adapter.PINNED_ACTION)


def recover(callback):
    return callback.restore(rollback_sha=ROLLBACK,scope_sha256=SCOPE)


def test_full_six_old_to_six_new_exact_systemd_bridge(tmp_path,monkeypatch):
    callback,native,sys,u,s=make_bridge(tmp_path,monkeypatch)
    result=promote(callback)
    assert result["completed_steps"]==adapter.STEPS
    assert sys.active==set(adapter.NEW_USER+adapter.NEW_ROOT)
    assert native.marker is True
    assert native.policy=="replacement"
    assert native.before_image==native.before
    assert sum(1 for p in list(u.iterdir())+list(s.iterdir()) if p.is_file())==12
    assert not native.issued_signer


@pytest.mark.parametrize("fault",adapter.STEPS)
def test_all_eight_real_unit_operation_phases_restore_exact_old_state(
    tmp_path,monkeypatch,fault
):
    callback,native,sys,u,s=make_bridge(tmp_path,monkeypatch,fail_at=fault)
    with pytest.raises(RuntimeError,match="INJECTED_"+fault):
        promote(callback)
    assert native.before_image==native.before
    result=recover(callback)
    assert result["status"]=="native_stage_e_six_unit_rollback_verified"
    assert sys.active==set(adapter.OLD_USER+adapter.OLD_ROOT)
    assert sys.enabled==set(adapter.OLD_USER+adapter.OLD_ROOT)
    assert native.policy=="legacy"
    assert native.marker is False
    assert list(u.iterdir())==[]
    assert list(s.iterdir())==[]


def test_replay_or_wrong_scope_cannot_touch_systemd(tmp_path,monkeypatch):
    callback,native,sys,u,s=make_bridge(tmp_path,monkeypatch)
    native.native_started_receipt_verified=lambda *args:False
    with pytest.raises(adapter.StageEAdapterDenied,match="SIGNED_NATIVE_RECEIPT_MISSING"):
        promote(callback)
    assert sys.active==set(adapter.OLD_USER+adapter.OLD_ROOT)
    assert not list(u.iterdir())


def test_backend_bridge_rechecks_live_code_before_marker(tmp_path,monkeypatch):
    callback,native,sys,u,s=make_bridge(tmp_path,monkeypatch)
    native.verify_live_controlplane_alignment=lambda *args:False
    with pytest.raises(adapter.StageEAdapterDenied,
                       match="INSTALLED_CONTROLPLANE_NOT_EXACT"):
        promote(callback)
    assert native.marker is False
    assert native.policy=="replacement"
    result=recover(callback)
    assert result["status"]=="native_stage_e_six_unit_rollback_verified"
    assert sys.active==set(adapter.OLD_USER+adapter.OLD_ROOT)
    assert native.policy=="legacy"
