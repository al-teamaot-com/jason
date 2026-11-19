#!/usr/bin/env python3
"""Bridge the existing native root release host to Stage E exact systemd ops.

Library only. The accepted ComponentReleaseController owns the signed Owner
proof and immutable native 'started' receipt. The existing root host provides
the original before-image, policy/freeze/breaker verification, artifact digest
pins, durable claims, signed receipt and rollback. This is a *typed bridge*,
not another release manager, installer or authority issuer.
"""
from __future__ import annotations
from typing import Any
from tools.pmv4_e_native_systemd_adapter import Before, StageEAdapterDenied, require
from tools.pmv4_e_systemd_root_ops import ExactSystemdSurface


class StageERootBridge:
    def __init__(self,*,native_root:Any,systemd:ExactSystemdSurface):
        self.native=native_root
        self.systemd=systemd

    def root_install_verified(self)->bool:
        return self.native.root_install_verified()

    def exclusive_host_lock_held(self)->bool:
        return self.native.exclusive_host_lock_held()

    def freeze_lock_held(self)->bool:
        return self.native.freeze_lock_held()

    def read_protected_before(self)->Before:
        return self.native.read_protected_before()

    def trusted_exact_plan(self,*args)->bool:
        return self.native.trusted_exact_plan(*args)

    def native_started_receipt_verified(self,*args)->bool:
        return self.native.native_started_receipt_verified(*args)

    def original_signed_started_receipt_verified(self,*args)->bool:
        return self.native.original_signed_started_receipt_verified(*args)

    def verify_baseline(self,before:Before)->None:
        self.native.verify_baseline(before)
        for user,names in ((True,self.native.old_user_units()),
                           (False,self.native.old_root_units())):
            for name in names:
                require(self.systemd.status(name,user=user)==("active","enabled"),
                        "LEGACY_LIVE_STATUS_DRIFT")

    def active_triggers(self):
        active=set()
        for user,names in ((True,self.native.all_user_triggers()),
                           (False,self.native.all_root_triggers())):
            for name in names:
                if self.systemd.status(name,user=user)[0]=="active":
                    active.add(name)
        return frozenset(active)

    def persist_root_before_image(self,b:Before):
        self.native.persist_root_before_image(b)

    def quiesce_and_verify_claims(self):
        self.native.quiesce_and_verify_claims()

    def stage_exact_new_units(self,u,r):
        hashes=self.native.reviewed_twelve_unit_hashes()
        need_user=set(u)==set(self.native.new_user_units())
        need_root=set(r)==set(self.native.new_root_units())
        require(need_user and need_root,"SIX_REPLACEMENT_SCOPE_CHANGED")
        self.systemd.stage(hashes)

    def stop_disable_exact(self,u,r):
        u_set=set(u)
        r_set=set(r)
        if (u_set==set(self.native.old_user_units())
            and r_set==set(self.native.old_root_units())):
            self.systemd.disable_legacy()
        elif (u_set==set(self.native.new_user_units())
              and r_set==set(self.native.new_root_units())):
            self.systemd.stop_disable_replacement_if_present()
        else:
            raise StageEAdapterDenied("PMV4_E_NATIVE_ADAPTER_STOP_SET_NOT_EXACT")

    def commit_reviewed_policy_and_code(self,*args):
        self.native.commit_reviewed_policy_and_code(*args)

    def verify_live_controlplane_alignment(self,*args)->bool:
        return self.native.verify_live_controlplane_alignment(*args)

    def commit_reviewed_root_marker(self,*args):
        self.native.commit_reviewed_root_marker(*args)

    def enable_start_exact(self,u,r):
        require(set(u)==set(self.native.new_user_units())
                and set(r)==set(self.native.new_root_units()),
                "ACTIVATION_SCOPE_CHANGED")
        self.systemd.activate_replacement()

    def verify_six_callbacks_and_protected(self,before:Before):
        require(self.systemd.verify_final(replacement=True),
                "SIX_LIVE_TRIGGER_PARITY_FAILED")
        self.native.verify_six_callbacks_and_protected(before)

    def freeze_and_protected_unchanged(self,before:Before):
        return self.native.freeze_and_protected_unchanged(before)

    def append_native_step_receipt(self,*args):
        self.native.append_native_step_receipt(*args)

    def read_immutable_root_before_image(self):
        return self.native.read_immutable_root_before_image()

    def block_new_dispatch(self):
        self.native.block_new_dispatch()

    def revoke_exact_marker_before_legacy(self):
        self.native.revoke_exact_marker_before_legacy()

    def restore_reviewed_policy_code_and_watchdog(self,before:Before):
        self.native.restore_reviewed_policy_code_and_watchdog(before)

    def restore_six_original_units_and_states(self,before:Before):
        self.systemd.restore_legacy()
        self.systemd.unstage_exact(self.native.reviewed_twelve_unit_hashes())
        self.native.restore_six_original_units_and_states(before)

    def verify_rollback(self,before:Before):
        require(self.systemd.verify_final(replacement=False),
                "SYSTEMD_ROLLBACK_NOT_EXACT")
        self.native.verify_rollback(before)

    def append_native_recovery_receipt(self,before:Before):
        self.native.append_native_recovery_receipt(before)
