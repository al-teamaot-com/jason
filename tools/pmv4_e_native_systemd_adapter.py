#!/usr/bin/env python3
"""Stage E six-control systemd adapter for the *existing* native root controller.

Library only. No CLI, no new authority signer, no self-deploying root entrypoint.
Only the installed native ComponentReleaseController may invoke this host
callback after its signed exact-release preflight, immutable receipt, and
shared host/freeze locks. The final root installation must pin the immutable
source and bind its callback/rollback to the existing controller.

All six triggers are moved as one transaction. No provider commands, reboot,
network changes, service restarts, or protected core/MCP modifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from tools import pmv4_e_scheduler_parity as schedule

OLD_USER=tuple(sorted(schedule.USER_LEGACY))
OLD_ROOT=tuple(sorted(schedule.ROOT_LEGACY))
NEW_USER=tuple(sorted(schedule.USER_REPLACEMENT))
NEW_ROOT=tuple(sorted(schedule.ROOT_REPLACEMENT))
CONTINUITY_USER=tuple(sorted(schedule.CONTINUITY_USER))
CONTINUITY_ROOT=tuple(sorted(schedule.CONTINUITY_ROOT))
OLD=frozenset(OLD_USER+OLD_ROOT)
NEW=frozenset(NEW_USER+NEW_ROOT)
PINNED_ACTION="pmv4-e-oneowner-six-unit-replacement-and-retirement-v1"
STEPS=(
    "check_exact_baseline",
    "checkpoint_durable_claims",
    "stage_reviewed_units_inert",
    "stop_six_legacy",
    "commit_exact_policy_and_convergence",
    "commit_root_accepted_marker",
    "activate_six_replacements",
    "verify_complete_parity",
)


class StageEAdapterDenied(PermissionError):
    pass


def require(value:bool,code:str)->None:
    if not value:
        raise StageEAdapterDenied("PMV4_E_NATIVE_ADAPTER_"+code)


@dataclass(frozen=True)
class Before:
    """Verbatim native root snapshot; backend must persist before mutation."""
    active: frozenset[str]
    enabled: frozenset[str]
    policy_sha256: str
    source_sha: str
    freeze_sha256: str
    protected_fingerprint: str
    claims_fingerprint: str
    marker_present: bool


def assert_exact_before(before:Before)->None:
    require(before.marker_present is False,"EXISTING_MARKER")
    require(OLD.issubset(before.active) and OLD.issubset(before.enabled),
            "SIX_LEGACY_BASELINE_UNAVAILABLE")
    require(not before.active.intersection(NEW) and
            not before.enabled.intersection(NEW),
            "REPLACEMENTS_ALREADY_DISPATCHING")
    require(bool(before.policy_sha256) and bool(before.freeze_sha256)
            and bool(before.protected_fingerprint)
            and bool(before.claims_fingerprint),"PROTECTED_BASELINE_UNVERIFIED")


class StageEUnitAdapter:
    """Systemd host callback, only usable inside native signed release boundary.

    Backend is an installed root-only native adapter; never an arbitrary
    untrusted shell target. No release authorization is issued here.
    """

    def __init__(self,backend:Any,*,native_invocation:Callable[[],bool]):
        self.backend=backend
        self.native_invocation=native_invocation

    def _native(self)->None:
        require(self.native_invocation() is True,
                "NATIVE_SIGNED_TRANSACTION_BOUNDARY_REQUIRED")
        require(self.backend.root_install_verified() is True,
                "IMMUTABLE_ROOT_INSTALL_REQUIRED")
        require(self.backend.exclusive_host_lock_held() is True,
                "SHARED_HOST_LOCK_REQUIRED")
        require(self.backend.freeze_lock_held() is True,
                "FREEZE_LOCK_REQUIRED")

    def activate(self,*,candidate_sha:str,rollback_sha:str,
                 scope_sha256:str,action:str)->Mapping[str,Any]:
        self._native()
        require(action==PINNED_ACTION,"ACTION_UNREVIEWED")
        require(candidate_sha!=rollback_sha and
                len(candidate_sha)==len(rollback_sha)==40 and
                len(scope_sha256)==64 and
                all(x in "0123456789abcdef" for x in
                    candidate_sha+rollback_sha+scope_sha256),
                "CANDIDATE_ROLLBACK_SCOPE_UNTRUSTED")
        before=self.backend.read_protected_before()
        require(isinstance(before,Before),"PROTECTED_BEFORE_INVALID")
        assert_exact_before(before)
        require(before.source_sha==rollback_sha,"ROLLBACK_BASELINE_CHANGED")
        require(self.backend.trusted_exact_plan(candidate_sha,rollback_sha,
                                               scope_sha256,before) is True,
                "SIGNED_PLAN_NOT_INSTALLED")
        # The native controller writes its immutable 'started' receipt
        # *before* calling this adapter, and owns interrupted recovery.
        require(self.backend.native_started_receipt_verified(
            candidate_sha,rollback_sha,scope_sha256) is True,
            "SIGNED_NATIVE_RECEIPT_MISSING")
        completed=[]
        try:
            for step in STEPS:
                if step=="check_exact_baseline":
                    self.backend.verify_baseline(before)
                elif step=="stage_reviewed_units_inert":
                    self.backend.stage_exact_new_units(NEW_USER,NEW_ROOT)
                    require(not set(self.backend.active_triggers())&NEW,
                            "INERT_STAGE_DISPATCHED")
                elif step=="checkpoint_durable_claims":
                    self.backend.persist_root_before_image(before)
                    self.backend.quiesce_and_verify_claims()
                elif step=="stop_six_legacy":
                    self.backend.stop_disable_exact(OLD_USER,OLD_ROOT)
                    require(not set(self.backend.active_triggers())&OLD,
                            "LEGACY_DISPATCH_STILL_ACTIVE")
                elif step=="commit_exact_policy_and_convergence":
                    self.backend.commit_reviewed_policy_and_code(
                        candidate_sha,rollback_sha,scope_sha256)
                elif step=="commit_root_accepted_marker":
                    self.backend.commit_reviewed_root_marker(
                        candidate_sha,rollback_sha,scope_sha256)
                elif step=="activate_six_replacements":
                    self.backend.enable_start_exact(NEW_USER,NEW_ROOT)
                elif step=="verify_complete_parity":
                    self.backend.verify_six_callbacks_and_protected(before)
                    active=set(self.backend.active_triggers())
                    require(NEW.issubset(active) and not (active&OLD),
                            "POSTFLIGHT_NOT_SIX_REPLACEMENTS")
                    require(self.backend.freeze_and_protected_unchanged(before),
                            "PROTECTED_POSTFLIGHT_CHANGED")
                self.backend.append_native_step_receipt(step,before)
                completed.append(step)
            return {"status":"native_stage_e_six_unit_candidate_verified",
                    "candidate_sha":candidate_sha,
                    "rollback_sha":rollback_sha,
                    "scope_sha256":scope_sha256,
                    "completed_steps":tuple(completed),
                    "owner_authority_issued":False}
        except BaseException:
            # Fail closed; native controller will independently call restore
            # and mark 'rolled_back' only after strict postflight.
            raise

    def restore(self,*,rollback_sha:str,scope_sha256:str)->Mapping[str,Any]:
        self._native()
        require(self.backend.original_signed_started_receipt_verified(
            rollback_sha,scope_sha256) is True,
            "ORIGINAL_NATIVE_RECOVERY_RECEIPT_MISSING")
        before=self.backend.read_immutable_root_before_image()
        require(isinstance(before,Before),"DURABLE_BEFORE_IMAGE_MISSING")
        assert_exact_before(before)
        self.backend.block_new_dispatch()
        self.backend.stop_disable_exact(NEW_USER,NEW_ROOT)
        self.backend.revoke_exact_marker_before_legacy()
        self.backend.restore_reviewed_policy_code_and_watchdog(before)
        self.backend.restore_six_original_units_and_states(before)
        self.backend.verify_rollback(before)
        require(self.backend.freeze_and_protected_unchanged(before)
                and set(self.backend.active_triggers())&NEW==set()
                and OLD.issubset(set(self.backend.active_triggers())),
                "ROLLBACK_NOT_EXACT")
        self.backend.append_native_recovery_receipt(before)
        return {"status":"native_stage_e_six_unit_rollback_verified",
                "rollback_sha":rollback_sha,
                "owner_authority_issued":False}
