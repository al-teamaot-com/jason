"""Signed typed native ledger + real disposable 12-unit systemd acceptance.

This is the full isolated cross-component path: one authentic Ed25519 Owner
release, original shared native STARTED receipt, native Stage E eight callbacks,
actual 12 reviewed unit file writes in disposable directories, full rollback
through the same signed receipt, no provider or host-root changes.
"""
from contextlib import contextmanager
from hashlib import sha256
import json

import pytest

from tools import pmv4_e_native_systemd_adapter as adapter
from tools import pmv4_e_systemd_root_ops as ops
from tools import pmv4_e_root_trust_stage as trust
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_replacement_unit_bundle as bundle
from tools import pmv4_e_native_backend_bridge as bridge
from tools import pmv4_e_native_release_contract as contract
from tools.tests.test_pmv4_e_signed_native_ledger import (
    Host, fixture, approval, ctl, CANDIDATE, ROLLBACK, records,
)
from tools.tests.test_pmv4_e_native_backend_bridge import Native
from tools.tests.test_pmv4_e_systemd_root_ops import FakeSystemctl


class CoupledHost(Host):
    def __init__(self, tmp_path, monkeypatch, ledger_root, *, fail_at=None):
        super().__init__()
        # Copy the ACTUAL signed source manifest into an isolated sealed
        # root. The real unit generator reads reviewed bytes from this root.
        # There is deliberately no monkeypatch of bundle.generate; the
        # signed ledger performs its real exact-byte source verification.
        work = tmp_path / "systemd"
        work.mkdir()
        sealed = work / "sealed"
        staged_hashes = {
            relative: sha256((packet.ROOT / relative).read_bytes()).hexdigest()
            for relative in packet.REVIEWED_PATHS
        }
        stager = trust.RootTrustStager(
            source=packet.ROOT, target=sealed,
            native_signed_started=lambda: True,
            native_host_locked=lambda: True,
            native_freeze_locked=lambda: True,
            native_marker_absent=lambda: True,
            native_replacements_inert=lambda: True,
            production=False,
        )
        stage_result = stager.stage(source_sha=CANDIDATE,
                                    exact_hashes=staged_hashes)
        assert stage_result["installed_file_count"] == len(packet.REVIEWED_PATHS)
        self.user_dir = work / "user"
        self.system_dir = work / "system"
        self.user_dir.mkdir()
        self.system_dir.mkdir()
        self.systemd = FakeSystemctl()
        self.unit_surface = ops.ExactSystemdSurface(
            production=False, runner=self.systemd,
            user_dir=self.user_dir, system_dir=self.system_dir,
            trusted_dir=sealed / "infrastructure/pmv4-e-scheduler/systemd",
        )
        unit_hashes = {
            relative: sha256(content).hexdigest()
            for relative, content in bundle.generate(base=sealed).items()
        }
        assert len(unit_hashes) == 12
        self.native = Native(self.systemd,unit_hashes,fail_at=fail_at)
        wrapped = bridge.StageERootBridge(
            native_root=self.native,systemd=self.unit_surface)
        self.callback = adapter.StageEUnitAdapter(
            wrapped,native_invocation=lambda: True)
        self.ledger_root = ledger_root
        self.host_lock_held = False
        # The systemd fixture intentionally substitutes disposable unit
        # bytes after the signed source manifest was prepared. Reusing the
        # immutable on-disk manifest avoids re-drafting against fake bytes.
        self.scope = json.loads(
            (ledger_root/"releases"/CANDIDATE/"manifest.json").read_text()
        )["source_scope_sha256"]
        self.callback.native_invocation = (
            lambda: self.host_lock_held and self.freeze_active)
        self.native.exclusive_host_lock_held = lambda: self.host_lock_held
        self.native.freeze_lock_held = lambda: self.freeze_active
        self.native.trusted_exact_plan = (
            lambda candidate, rollback, scope, before: (
                (candidate, rollback, scope) ==
                (CANDIDATE, ROLLBACK, self.scope)))
        self.native.verify_live_controlplane_alignment = (
            lambda candidate, rollback, scope: (
                self.native.controlplane_aligned
                and (candidate,rollback,scope) ==
                (CANDIDATE,ROLLBACK,self.scope)))
        self.native.native_started_receipt_verified = self.signed_started
        self.native.original_signed_started_receipt_verified = (
            lambda rollback, scope: self.signed_started(
                CANDIDATE, rollback, scope))
        self.root_callback_count = 0

    def signed_started(self, candidate, rollback, scope):
        rows = records(self.ledger_root)
        if len(rows) != 1:
            return False
        record = rows[0]
        proof = record.get("signed_owner_proof") or {}
        payload = proof.get("payload") or {}
        return (
            record.get("state") == "started"
            and record.get("candidate_sha") == candidate
            and record.get("rollback_sha") == rollback
            and record.get("scope_sha256") == scope
            and record.get("approval_id") == payload.get("approval_id")
            and payload.get("authorization") ==
                "authenticated_entra_owner_exact_release"
            and payload.get("one_release_only") is True
        )

    @contextmanager
    def lock(self):
        self.host_lock_held = True
        try:
            with super().lock():
                yield
        finally:
            self.host_lock_held = False

    def activate(self, bundle, manifest):
        assert self.host_lock_held and self.freeze_active
        self.root_callback_count += 1
        self.callback.activate(
            candidate_sha=manifest["candidate_sha"],
            rollback_sha=manifest["rollback_sha"],
            scope_sha256=manifest["source_scope_sha256"],
            action=manifest["action"],
        )
        self.installed = CANDIDATE

    def restore(self, previous, manifest):
        assert self.host_lock_held and self.freeze_active
        assert previous.name == ROLLBACK
        if self.fail_restore:
            raise RuntimeError("SIMULATED_RECOVERY_INTERRUPTED")
        self.callback.restore(
            rollback_sha=manifest["rollback_sha"],
            scope_sha256=manifest["source_scope_sha256"],
        )
        self.installed = ROLLBACK

    def verify(self, bundle, manifest):
        if bundle.name == CANDIDATE:
            return (not self.fail_acceptance
                    and self.unit_surface.verify_final(replacement=True))
        return self.unit_surface.verify_final(replacement=False)


def check_old_restored(host):
    assert host.systemd.active == set(adapter.OLD_USER + adapter.OLD_ROOT)
    assert host.systemd.enabled == set(adapter.OLD_USER + adapter.OLD_ROOT)
    assert host.native.marker is False
    assert host.native.policy == "legacy"
    assert list(host.user_dir.iterdir()) == []
    assert list(host.system_dir.iterdir()) == []


def test_one_signed_owner_full_twelve_file_systemd_lifecycle(tmp_path, monkeypatch):
    root, manifest = fixture(tmp_path)
    host = CoupledHost(tmp_path, monkeypatch, root)
    receipt = ctl(root, host).promote(manifest, approval(manifest))
    assert receipt["status"] == "native_stage_e_six_unit_accepted"
    assert receipt["protected_services_changed"] is False
    assert host.root_callback_count == 1
    assert host.systemd.active == set(adapter.NEW_USER + adapter.NEW_ROOT)
    assert host.systemd.enabled == set(adapter.NEW_USER + adapter.NEW_ROOT)
    assert host.native.marker is True
    assert host.native.policy == "replacement"
    assert len(list(host.user_dir.iterdir()) +
               list(host.system_dir.iterdir())) == 12
    assert records(root)[0]["state"] == "accepted"
    assert not host.host_lock_held and not host.freeze_active


@pytest.mark.parametrize("fault", adapter.STEPS)
def test_each_real_unit_phase_rolls_back_under_same_signed_native_receipt(
        tmp_path, monkeypatch, fault):
    root, manifest = fixture(tmp_path)
    host = CoupledHost(tmp_path, monkeypatch, root, fail_at=fault)
    with pytest.raises(RuntimeError, match="INJECTED_" + fault):
        ctl(root, host).promote(manifest, approval(manifest))
    check_old_restored(host)
    assert host.installed == ROLLBACK
    assert records(root)[0]["state"] == "rolled_back"
    assert list((root/"active").iterdir()) == []
    assert host.root_callback_count == 1


def test_lost_native_recovery_keeps_started_until_original_proof_recovers(
        tmp_path, monkeypatch):
    root, manifest = fixture(tmp_path)
    host = CoupledHost(tmp_path, monkeypatch, root, fail_at=adapter.STEPS[-1])
    host.fail_restore = True
    with pytest.raises(RuntimeError, match="INJECTED_"):
        ctl(root, host).promote(manifest, approval(manifest))
    assert records(root)[0]["state"] == "started"
    assert host.native.before_image is not None
    host.fail_restore = False
    recovered = ctl(root, host).recover_interrupted_rollback()
    assert recovered["status"] == "native_stage_e_six_unit_rollback_verified"
    check_old_restored(host)
    assert records(root)[0]["state"] == "rolled_back"
    assert ctl(root, host).recover_interrupted_rollback()["status"] == (
        "nothing_pending")


def test_no_lock_cannot_touch_twelve_unit_surface(tmp_path, monkeypatch):
    root, manifest=fixture(tmp_path)
    host=CoupledHost(tmp_path, monkeypatch, root)
    with pytest.raises(adapter.StageEAdapterDenied,
                       match="NATIVE_SIGNED_TRANSACTION_BOUNDARY_REQUIRED"):
        host.callback.activate(
            candidate_sha=CANDIDATE,rollback_sha=ROLLBACK,
            scope_sha256=manifest["source_scope_sha256"],
            action=adapter.PINNED_ACTION,
        )
    check_old_restored(host)
    assert host.systemd.calls == []
    assert list((root/"receipts").iterdir()) == []
