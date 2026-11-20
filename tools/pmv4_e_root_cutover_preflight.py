#!/usr/bin/env python3
"""PMv4 E root-only preflight. READ ONLY, NOT a release executor.

This reuses existing Stage C/D/A1 and native canary root attestors. It
never creates approval, writes policy, installs or stops a unit. Its purpose
is to deny a six-trigger cutover if any independently verifiable
production prerequisite is absent.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
import stat
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping
from types import SimpleNamespace
from tools.independent_component_release import (
    ComponentReleaseController, ComponentReleaseDenied, PROTECTED as NATIVE_PROTECTED,
)

from tools import pmv4_e_scheduler_parity as parity

MARKER=Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
OLD_USER=parity.USER_LEGACY
OLD_ROOT=parity.ROOT_LEGACY
NEW_USER=parity.USER_REPLACEMENT
NEW_ROOT=parity.ROOT_REPLACEMENT
PRESERVE_USER=parity.CONTINUITY_USER
PRESERVE_ROOT=parity.CONTINUITY_ROOT
SOURCE_POLICY=Path("/opt/jason/current/config/production-desired-state.json")
ROOT_POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
CONTROL_STATE=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
DRIFT_STATE=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"



class RootPreflightDenied(PermissionError):
    pass


def require(ok:bool,why:str)->None:
    if not ok:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_"+why)


def verify_native_protected(snapshot):
    """Use the original controller's exact protected-container health rule."""
    require(isinstance(snapshot,Mapping) and set(snapshot)==set(NATIVE_PROTECTED),
            "NATIVE_PROTECTED_SNAPSHOT_INCOMPLETE")
    for name,row in snapshot.items():
        require(isinstance(row,Mapping),"NATIVE_PROTECTED_RECORD_INVALID")
        require(row.get("running") is True and row.get("health") in ("healthy","none",None),
                "NATIVE_PROTECTED_UNHEALTHY:"+name)
    try:
        return ComponentReleaseController._verify_protected_snapshot(
            SimpleNamespace(verify_protected=lambda:snapshot))
    except ComponentReleaseDenied as exc:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_NATIVE_PROTECTED_RECORD_INVALID") from exc


def live_native_protected(*,runner=subprocess.run):
    observed={}
    for name in NATIVE_PROTECTED:
        result=runner(["/usr/bin/docker","inspect","--type","container",name],
                      capture_output=True,text=True,timeout=15,check=False)
        require(result.returncode==0,"NATIVE_PROTECTED_READ_UNAVAILABLE:"+name)
        try:
            data=json.loads(result.stdout)
            require(isinstance(data,list) and len(data)==1,"NATIVE_PROTECTED_READ_AMBIGUOUS")
            row=data[0];state=row["State"]
            observed[name]={"id":row["Id"],"image":row["Image"],
                "started_at":state["StartedAt"],"running":state["Running"],
                "health":(state.get("Health") or {}).get("Status","none")}
        except (ValueError,KeyError,TypeError) as exc:
            raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_NATIVE_PROTECTED_RECORD_INVALID") from exc
    return verify_native_protected(observed)


def evaluate(evidence:Mapping[str,Any])->dict[str,Any]:
    """Pure fail-closed decision; passed only independently measured evidence."""
    require(evidence.get("uid")==0,"ROOT_ONLY")
    verify_native_protected(evidence.get("native_protected"))
    require(evidence.get("root_cda1")=="verified","C_D_A1_ROOT_RECEIPT_UNVERIFIED")
    require(evidence.get("root_canary")=="verified","NATIVE_CANARY_UNVERIFIED")
    require(evidence.get("source_policy_valid") is True,
            "REVIEWED_SOURCE_POLICY_MISMATCH")
    require(evidence.get("root_policy_valid") is True,
            "PROTECTED_ROOT_POLICY_MISMATCH")
    require(evidence.get("marker_absent") is True,
            "CUTOVER_ALREADY_ACCEPTED_OR_MARKER_UNTRUSTED")
    require(evidence.get("breaker")=="closed","PRODUCTION_BREAKER_NOT_CLOSED")
    require(evidence.get("freeze")=="unchanged","FREEZE_CHANGED")
    require(evidence.get("ticket_unique_owner") is True,
            "TICKET_DISPATCH_OWNER_UNVERIFIED")
    require(evidence.get("scan_fresh") is True and
            evidence.get("duplicate_items")==0,
            "TICKET_SCANS_UNTRUSTED")
    for key,expected,required in (
        ("user_active_old",OLD_USER,True),
        ("root_active_old",OLD_ROOT,True),
        ("user_active_new",NEW_USER,False),
        ("root_active_new",NEW_ROOT,False),
        ("user_monitoring",PRESERVE_USER,True),
        ("root_monitoring",PRESERVE_ROOT,True),
    ):
        observed=evidence.get(key)
        require(isinstance(observed,Mapping),"UNIT_READBACK_MISSING_"+key.upper())
        for name in expected:
            require(observed.get(name) is required,
                    "UNIT_STATE_MISMATCH_"+name.replace(".","_").replace("-","_").upper())
    return {
        "status":"read_only_root_preflight_source_conditions_passed",
        "production_mutations":False,
        "owner_release_authorized":False,
        "pmv3_retirement_authorized":False,
        "native_protected_components_verified":len(NATIVE_PROTECTED),
        "legacy_triggers_verified":6,
        "replacement_triggers_verified_inert":6,
    }


def _active(unit:str,*,user:bool,runner:Callable[...,Any]=subprocess.run)->bool:
    args=(
        ["/usr/sbin/runuser","-u","al","--",
         "/usr/bin/env","XDG_RUNTIME_DIR=/run/user/1000",
         "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
         "/usr/bin/systemctl","--user","is-active",unit]
        if user else ["/usr/bin/systemctl","is-active",unit]
    )
    p=runner(args,capture_output=True,text=True,timeout=15,check=False)
    result=p.stdout.strip()
    # Live Jason systemctl returns exit 4 / "inactive" for the six PMv4
    # timers/paths not yet installed. Inert/absent NEW triggers are precisely
    # the expected pre-cutover state. Never extend this exception to old
    # legacy triggers or protected monitoring units.
    replacement=(NEW_USER if user else NEW_ROOT)
    if unit in replacement and p.returncode==4:
        require(result=="inactive","NEW_TRIGGER_ABSENCE_AMBIGUOUS")
        return False
    require(p.returncode in (0,3),"SYSTEMD_READBACK_UNAVAILABLE")
    require(result in ("active","inactive","failed"),"SYSTEMD_READBACK_UNKNOWN")
    return p.returncode==0 and result=="active"


def _root_json(path:Path, *, maximum:int=120000, allowed_uid:int=0)->dict[str,Any]:
    try:
        meta=path.lstat()
        require(stat.S_ISREG(meta.st_mode) and not path.is_symlink()
                and meta.st_uid==allowed_uid and meta.st_gid==allowed_uid
                and meta.st_nlink==1 and meta.st_mode&0o022==0
                and 0<meta.st_size<=maximum,
                "ROOT_PROTECTED_FILE_UNTRUSTED")
        raw=path.read_bytes()
        require(len(raw)==meta.st_size,"ROOT_PROTECTED_FILE_CHANGED")
        value=json.loads(raw)
        require(isinstance(value,dict),"ROOT_PROTECTED_JSON_INVALID")
        return value
    except (OSError,ValueError,TypeError) as exc:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_ROOT_FILE_UNAVAILABLE") from exc


def _root_evidence(*, historical:Mapping[str,Any], canary:Mapping[str,Any])->dict[str,Any]:
    """Read only root-owned release state, never derive permissions from caller flags."""
    require(historical.get("status")=="pre_retirement_root_acceptance_verified"
            and historical.get("stage_c_root_acceptance_verified") is True
            and historical.get("stage_d_root_acceptance_verified") is True
            and historical.get("a1_root_acceptance_verified") is True,
            "C_D_A1_ROOT_RECEIPT_UNVERIFIED")
    require(canary.get("status")=="native_providerfree_canary_accepted_and_removed"
            and canary.get("stage_c_d_a1_root_acceptance") is True
            and canary.get("canary_container_absent") is True
            and canary.get("canary_network_absent") is True
            and canary.get("active_pointer_absent") is True,
            "NATIVE_CANARY_UNVERIFIED")
    protected=_root_json(ROOT_POLICY)
    # The installed current-release tree has historically allowed group
    # write on some files. Treat it as evidence ONLY, not release authority;
    # never use it to grant a production action or select the candidate SHA.
    source=json.loads(SOURCE_POLICY.read_bytes())
    require(protected.get("schema_version")=="1.0"
            and source.get("schema_version")=="1.0",
            "SOURCE_POLICY_SCHEMA_NOT_REVIEWED")
    # Both checked-in source and live root must retain the exact historical
    # old six-control baseline; only the future authorized delta changes them.
    try:
        protected_plan=parity.plan_exact_unit_delta(protected)
        source_plan=parity.plan_exact_unit_delta(source)
    except (ValueError,TypeError,PermissionError) as exc:
        raise RootPreflightDenied(
            "PMV4_E_ROOT_PREFLIGHT_PRECUTOVER_POLICY_NOT_EXACT") from exc
    require(set(protected_plan["retire_user_units"])==set(source_plan["retire_user_units"])
            and set(protected_plan["retire_system_units"])==set(source_plan["retire_system_units"])
            and set(protected_plan["add_user_units"])==set(source_plan["add_user_units"])
            and set(protected_plan["add_system_units"])==set(source_plan["add_system_units"]),
            "SOURCE_POLICY_UNIT_SCOPE_CHANGED")
    state=_root_json(CONTROL_STATE,allowed_uid=1000)
    drift=_root_json(DRIFT_STATE,allowed_uid=1000)
    require(drift.get("status")=="pass" and drift.get("problems")==[],
            "PRODUCTION_DRIFT_NOT_PASS")
    try:
        freeze_meta=FREEZE.lstat()
        require(stat.S_ISREG(freeze_meta.st_mode) and not FREEZE.is_symlink()
                and freeze_meta.st_uid==1000 and freeze_meta.st_gid==1000
                and stat.S_IMODE(freeze_meta.st_mode)==0o600
                and sha256(FREEZE.read_bytes()).hexdigest()==FREEZE_SHA,
                "PRODUCTION_FREEZE_CHANGED")
    except OSError as exc:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_FREEZE_UNAVAILABLE") from exc
    return {
        "source_policy_valid":True,"root_policy_valid":True,
        "breaker":(state.get("circuit_breaker") or {}).get("state"),
        "freeze":"unchanged","root_cda1":"verified","root_canary":"verified",
        "protected_policy_before_sha256":historical.get(
            "protected_live_policy_sha256"),
        "protected_policy_candidate_sha256":protected_plan.get(
            "candidate_policy_sha256"),
    }


def collect(*,runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    """Live root observation, never grant production release authority."""
    require(os.geteuid()==0,"ROOT_ONLY")
    native_protected=live_native_protected(runner=runner)
    from tools import pmv4_e_root_receipt_readback as rootproof
    from tools import pmv4_e_canary_acceptance_readback as canaryproof
    from tools import pmv4_e_retirement_readiness as retirement
    from tools import pmv4_e_ticket_owner_readback as ownerproof
    # Trusted attestors verify exact source and the historic root audit chain.
    historical=rootproof.inspect()
    canary=canaryproof.inspect()
    details=_root_evidence(historical=historical,canary=canary)
    try:
        MARKER.lstat()
    except FileNotFoundError:
        marker_absent=True
    except OSError as exc:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_MARKER_NOT_READABLE") from exc
    else:
        marker_absent=False
    # Fail closed if the parent has not been root-reviewed; the actual root
    # transaction must create the exact marker only after old units stop.
    scans=retirement.scan_summary()
    owner=ownerproof.inspect(runner=runner)
    require(owner.get("status")=="live_external_ticket_core_exclusive_owner_verified"
            and owner.get("unique_owner") is True
            and owner.get("exclusive_owner_count")==1,
            "CURRENT_TICKET_DISPATCH_OWNER_UNVERIFIED")
    return {
        "uid":0,**details,"native_protected":native_protected,
        "marker_absent":marker_absent,
        "user_active_old":{u:_active(u,user=True,runner=runner) for u in OLD_USER},
        "root_active_old":{u:_active(u,user=False,runner=runner) for u in OLD_ROOT},
        "user_active_new":{u:_active(u,user=True,runner=runner) for u in NEW_USER},
        "root_active_new":{u:_active(u,user=False,runner=runner) for u in NEW_ROOT},
        "user_monitoring":{u:_active(u,user=True,runner=runner) for u in PRESERVE_USER},
        "root_monitoring":{u:_active(u,user=False,runner=runner) for u in PRESERVE_ROOT},
        # Fresh provider-backed scans are necessary but never sufficient to
        # assert one physical ticket dispatch owner. That needs a separate
        # root-owned live ticket-lock / controller attestation.
        "ticket_unique_owner":True,
        "ticket_owner_evidence":{
            "lock_inode":owner["lock_inode"],
            "lock_owner_pid":owner["lock_owner_pid"],
            "container_init_pid":owner["container_init_pid"],
            "exclusive_owner_count":owner["exclusive_owner_count"],
        },
        "scan_fresh":scans.get("status")=="fresh",
        "duplicate_items":scans.get("duplicate_items"),
    }


def main()->int:
    try:
        result=collect()
        evaluation=evaluate(result)
        print(json.dumps(evaluation,sort_keys=True))
        return 0
    except (RootPreflightDenied,PermissionError,OSError,ValueError) as exc:
        print(json.dumps({
            "status":"not_ready_for_six_unit_cutover",
            "reason":str(exc)[:180],
            "production_mutations":False,
            "pmv3_retirement_authorized":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
