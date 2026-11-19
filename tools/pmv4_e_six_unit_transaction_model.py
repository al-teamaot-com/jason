#!/usr/bin/env python3
"""PMv4 Stage E six-unit cutover/rollback model. SOURCE-ONLY, NO host writes.

This verifies phase ordering, duplicate-dispatch exclusion, full-state rollback,
and failure injection using disposable in-memory state. It is NOT the privileged
release executor and cannot prove root/systemd/provider acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Any

from tools import pmv4_e_scheduler_parity as parity

OLD_USER=frozenset(parity.USER_LEGACY)
OLD_ROOT=frozenset(parity.ROOT_LEGACY)
NEW_USER=frozenset(parity.USER_REPLACEMENT)
NEW_ROOT=frozenset(parity.ROOT_REPLACEMENT)

class TransactionDenied(RuntimeError):
    pass

@dataclass(frozen=True)
class Snapshot:
    active_user: frozenset[str]
    active_root: frozenset[str]
    enabled_user: frozenset[str]
    enabled_root: frozenset[str]
    policy: str
    accepted_marker: bool
    source_sha: str
    owner_grant: bool
    freeze: str
    core_sha: str
    mcp_sha: str
    ticket_owner: str
    audit_chain: str

    def verify(self) -> None:
        if not (OLD_USER <= self.enabled_user or NEW_USER <= self.enabled_user):
            raise TransactionDenied("SCHEDULE_UNAVAILABLE")
        if (self.accepted_marker and ((self.active_user & OLD_USER) or
                                      (self.active_root & OLD_ROOT))):
            raise TransactionDenied("DUPLICATE_OLD_AFTER_ACCEPTANCE")
        if self.accepted_marker and not (NEW_USER <= self.active_user and
                                         NEW_ROOT <= self.active_root):
            raise TransactionDenied("REPLACEMENT_NOT_ACTIVE")
        if not self.accepted_marker and ((self.active_user & NEW_USER) or
                                         (self.active_root & NEW_ROOT)):
            raise TransactionDenied("NEW_DISPATCH_BEFORE_ACCEPTANCE")


def baseline() -> Snapshot:
    return Snapshot(
        active_user=OLD_USER,active_root=OLD_ROOT,
        enabled_user=OLD_USER,enabled_root=OLD_ROOT,
        policy="legacy",accepted_marker=False,
        source_sha="a"*40,owner_grant=True,
        freeze="f"*64,core_sha="c"*40,mcp_sha="d"*40,
        ticket_owner="external-ticket-core",audit_chain="0"*64)


def audit_step(prev:str,step:str)->str:
    raw=json.dumps({"prior":prev,"step":step},sort_keys=True,
                   separators=(",",":")).encode("utf-8")
    return sha256(raw).hexdigest()


def cutover(start:Snapshot, *,fail_after:str|None=None)->tuple[Snapshot,tuple[str,...]]:
    """Model a serialized exact-approval host transaction and rollback.

    No filesystem, systemd, Docker, provider, network or root access.
    All operations return immutable snapshots. Failure returns an exception
    whose recovery_snapshot equals the complete prior state.
    """
    if start.accepted_marker or not start.owner_grant:
        raise TransactionDenied("NEW_EXACT_OWNER_GRANT_REQUIRED")
    if (start.active_user!=OLD_USER or start.active_root!=OLD_ROOT
        or start.enabled_user!=OLD_USER or start.enabled_root!=OLD_ROOT
        or start.policy!="legacy"):
        raise TransactionDenied("BASELINE_CHANGED")
    original=start
    state=start
    trail=[]
    steps=(
        "stage_new_inert", "capture_checkpoint", "disable_legacy",
        "commit_exact_policy", "publish_root_acceptance", "activate_replacement",
        "postflight",
    )
    try:
        for step in steps:
            if step=="stage_new_inert":
                state=replace(state,enabled_user=state.enabled_user|NEW_USER,
                              enabled_root=state.enabled_root|NEW_ROOT)
            elif step=="capture_checkpoint":
                # The live root executor must independently acquire the
                # production release lock and persist durable work claims.
                pass
            elif step=="disable_legacy":
                state=replace(state,active_user=state.active_user-OLD_USER,
                              active_root=state.active_root-OLD_ROOT,
                              enabled_user=state.enabled_user-OLD_USER,
                              enabled_root=state.enabled_root-OLD_ROOT)
            elif step=="commit_exact_policy":
                state=replace(state,policy="reviewed-pmv4-e")
            elif step=="publish_root_acceptance":
                # New timers are staged but not dispatched until accepted.
                state=replace(state,accepted_marker=True)
            elif step=="activate_replacement":
                state=replace(state,active_user=state.active_user|NEW_USER,
                              active_root=state.active_root|NEW_ROOT)
            elif step=="postflight":
                state.verify()
            state=replace(state,audit_chain=audit_step(state.audit_chain,step))
            trail.append(step)
            if fail_after==step:
                raise TransactionDenied("INJECTED_FAILURE_"+step.upper())
        return state,tuple(trail)
    except Exception as exc:
        # The model restores the exact immutable pre-transaction snapshot.
        # Live rollback must separately demonstrate this with root receipts.
        error=TransactionDenied(str(exc))
        error.recovery_snapshot=original
        error.completed_steps=tuple(trail)
        raise error from exc


def rollback(after:Snapshot, original:Snapshot)->Snapshot:
    if not after.accepted_marker or after.policy!="reviewed-pmv4-e":
        raise TransactionDenied("ACCEPTED_STATE_REQUIRED")
    if (after.freeze!=original.freeze or after.core_sha!=original.core_sha
        or after.mcp_sha!=original.mcp_sha
        or after.ticket_owner!=original.ticket_owner):
        raise TransactionDenied("PROTECTED_STATE_CHANGED")
    # Remove acceptance before restoring PMv3. Real root path must prevent
    # in-flight PMv4 callbacks and use the existing serialized lock.
    return original


def summary()->dict[str,Any]:
    b=baseline()
    final,trail=cutover(b)
    failures=0
    for step in trail:
        try:
            cutover(b,fail_after=step)
        except TransactionDenied as exc:
            if getattr(exc,"recovery_snapshot",None)!=b:
                raise
            failures+=1
    return {
        "status":"source_only_simulation_not_root_acceptance",
        "old_triggers":len(OLD_USER)+len(OLD_ROOT),
        "new_triggers":len(NEW_USER)+len(NEW_ROOT),
        "transaction_phases":list(trail),
        "injected_failures_restored":failures,
        "exact_rollback":rollback(final,b)==b,
        "protected_core_mcp_unchanged":final.core_sha==b.core_sha and final.mcp_sha==b.mcp_sha,
        "freeze_unchanged":final.freeze==b.freeze,
        "ticket_owner_unchanged":final.ticket_owner==b.ticket_owner,
        "production_mutations":False,
        "root_transaction_implemented":False,
        "owner_authority_issued":False,
        "live_parity_accepted":False,
    }

if __name__=="__main__":
    print(json.dumps(summary(),sort_keys=True))
