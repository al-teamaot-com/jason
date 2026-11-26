#!/usr/bin/env python3
"""Source-only Stage E scheduler parity using EXISTING durable work engine.

No production entrypoint or provider dispatch. A versioned future installation
must connect proven native adapters, root locks and exact Owner release proof.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping

from tools import pmv3_work_engine as engine


class PMv4SchedulingDenied(PermissionError):
    pass


USER_LEGACY=frozenset({
    "jason-release-manager.timer",
    "jason-release-approval-only.timer",
    "jason-support-repair-worker.timer",
})
ROOT_LEGACY=frozenset({
    "jason-release-control-transition.timer",
    "jason-release-control-readback.timer",
    "jason-release-host-reconcile.path",
})
USER_REPLACEMENT=frozenset({
    "jason-pmv4-engineering.timer",
    "jason-pmv4-release-approval.timer",
    "jason-pmv4-component-release.timer",
})
ROOT_REPLACEMENT=frozenset({
    "jason-pmv4-component-transition.timer",
    "jason-pmv4-component-readback.timer",
    "jason-pmv4-component-reconcile.path",
})
CONTINUITY_USER=frozenset({
    "jason-self-heal-watchdog.timer",
    "jason-dnsfilter-boundary-reconcile.timer",
    "jason-kfs-collector.timer",
})
CONTINUITY_ROOT=frozenset({
    "jason-production-drift-watchdog.timer",
    "jason-openclaw-authority-health.timer",
    "jason-provider-health-canary.timer",
    "jason-core.service",
    "jason-boot-recovery.timer",
})
# An integration adapter must be explicitly reviewed for each of these.
# Unknown actions, provider writes and implicit release promotion are denied.
TEST_ACTIONS=frozenset({
    "read_engineering_inventory",
    "read_release_approval_offer",
    "read_component_signed_release_receipt",
    "read_root_drift_status",
    "read_component_recovery_status",
    "read_workboard_correlation",
})


def need(ok:bool,code:str)->None:
    if not ok:raise PMv4SchedulingDenied("PMV4_E_"+code)


def canon(item:Mapping[str,Any])->bytes:
    return json.dumps(item,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def read_source_policy(path:Path)->dict[str,Any]:
    need(path.is_file() and not path.is_symlink(),
         "SOURCE_POLICY_NOT_REGULAR")
    doc=json.loads(path.read_bytes())
    need(isinstance(doc,dict) and doc.get("schema_version")=="1.0",
         "SOURCE_POLICY_SCHEMA_UNTRUSTED")
    return doc


def plan_exact_unit_delta(policy:Mapping[str,Any])->dict[str,Any]:
    """Simulate the final old/new six-unit delta, never apply it."""
    need(isinstance(policy,Mapping)
         and policy.get("schema_version")=="1.0",
         "SOURCE_POLICY_SCHEMA_UNTRUSTED")
    users=set(policy.get("required_user_units") or [])
    roots=set(policy.get("required_system_units") or [])
    need(USER_LEGACY.issubset(users) and ROOT_LEGACY.issubset(roots),
         "LEGACY_SOURCE_UNIT_SET_NOT_FOUND")
    need(CONTINUITY_USER.issubset(users)
         and (CONTINUITY_ROOT - {"jason-boot-recovery.timer"}).issubset(roots),
         "CRITICAL_MONITORING_SAFETY_UNDECLARED")
    need(not any(s in users for s in USER_REPLACEMENT)
         and not any(s in roots for s in ROOT_REPLACEMENT),
         "REPLACEMENT_UNEXPECTEDLY_ALREADY_REQUIRED")
    output=dict(policy)
    output["required_user_units"]=sorted((users-USER_LEGACY)|USER_REPLACEMENT)
    output["required_system_units"]=sorted((roots-ROOT_LEGACY)|ROOT_REPLACEMENT)
    allowed_user=set(policy.get("allowed_user_units") or [])
    allowed_root=set(policy.get("allowed_system_units") or [])
    output["allowed_user_units"]=sorted(allowed_user | {
        n.replace(".timer",".service") for n in USER_REPLACEMENT
    })
    output["allowed_system_units"]=sorted(allowed_root | {
        n.replace(".timer",".service").replace(".path",".service")
        for n in ROOT_REPLACEMENT
    })
    # Removing old enabled units is a separate serialized root-owned
    # operation. Desired-state source change ALONE is never deployment.
    for field in ("required_containers","allowed_running_containers",
                  "max_stopped_rollback_containers",
                  "rollback_container_prefixes",
                  "forbidden_execution_prefixes"):
        need(output.get(field)==policy.get(field),
             "PROTECTED_CONTAINER_SCOPE_CHANGED")
    need(len(USER_REPLACEMENT)==len(USER_LEGACY)==3
         and len(ROOT_REPLACEMENT)==len(ROOT_LEGACY)==3,
         "RETIREMENT_UNIT_DELTA_NOT_EXACT")
    return {
        "schema_version":"1.0",
        "status":"source_only_exact_unit_delta_not_authorized",
        "retire_user_units":sorted(USER_LEGACY),
        "retire_system_units":sorted(ROOT_LEGACY),
        "add_user_units":sorted(USER_REPLACEMENT),
        "add_system_units":sorted(ROOT_REPLACEMENT),
        "prior_policy_sha256":sha256(canon(policy)).hexdigest(),
        "candidate_policy_sha256":sha256(canon(output)).hexdigest(),
        "candidate_policy":output,
        "core_mcp_restarts":0,
        "production_mutations":False,
        "owner_approval_issued":False,
        "retirement_authorized":False,
        "systemd_units_installed":False,
        "parity_accepted":False,
    }


@contextmanager
def readonly_isolated_lock(path:Path):
    """Lock the SAME state inode across replacement timer processes."""
    need(path.is_absolute() and str(path).startswith("/tmp/")
         and not path.is_symlink() and path.parent.is_dir()
         and not path.parent.is_symlink(),
         "TEST_ONLY_LOCK_PATH_REQUIRED")
    fd=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        meta=os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1
             and meta.st_uid==os.geteuid()
             and stat.S_IMODE(meta.st_mode)==0o600,
             "TEST_LOCK_INODE_UNTRUSTED")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PMv4SchedulingDenied("PMV4_E_CONCURRENT_SCHEDULER_CLAIM") from exc
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def isolated_preproduction_tick(
    state_path:Path,lock_path:Path,
    *,handlers:Mapping[str,Callable[[Mapping[str,Any],str],engine.Outcome]],
    facts:Mapping[str,bool]|None=None,
    capacity:int=2,
)->dict[str,Any]:
    """Existing engine claim/recovery logic, no new task engine or provider.

    Only explicit test callbacks and disposable /tmp state. It cannot
    schedule production or bypass a release/Owner permission gate.
    """
    need(state_path.is_absolute() and str(state_path).startswith("/tmp/")
         and not state_path.is_symlink() and state_path.parent.is_dir()
         and not state_path.parent.is_symlink()
         and type(capacity) is int and 1<=capacity<=2,
         "TEST_ONLY_DURABLE_STATE_REQUIRED")
    need(isinstance(handlers,Mapping)
         and set(handlers).issubset(TEST_ACTIONS)
         and all(callable(callback) for callback in handlers.values()),
         "UNREVIEWED_SCHEDULER_ADAPTER")
    with readonly_isolated_lock(lock_path):
        state=engine.load_state(state_path)
        def handler(item:Mapping[str,Any],key:str)->engine.Outcome:
            action=item.get("action")
            if action not in handlers:
                return engine.Outcome(
                    status="blocked",
                    reason="missing_trusted_preproduction_adapter")
            outcome=handlers[action](item,key)
            need(isinstance(outcome,engine.Outcome)
                 and outcome.status in (
                     "complete","waiting","retry","blocked","external")
                 and len(outcome.receipt)<512,
                 "TEST_HANDLER_UNTRUSTED_OUTCOME")
            return outcome
        result=engine.execute_cycle(
            state,facts=dict(facts or {}),handler=handler,
            capacity=capacity,checkpoint=lambda item:engine.atomic_write(
                state_path,item))
        engine.atomic_write(state_path,result)
        return {
            "status":"isolated_existing_engine_schedule_tick",
            "cycle":result["cycle"],"metrics":result["metrics"],
            "receipts":len(result["receipts"]),
            "provider_calls":0,"production_mutations":False,
            "release_promotions":0,"owner_approvals_issued":0,
        }
