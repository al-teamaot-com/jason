#!/usr/bin/env python3
"""PMv4 E root-only preflight. READ ONLY, NOT a release executor.

This reuses existing Stage C/D/A1 and native canary root attestors. It
never creates approval, writes policy, installs or stops a unit. Its purpose
is to deny a six-trigger cutover if any independently verifiable
production prerequisite is absent.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from tools import pmv4_e_scheduler_parity as parity

MARKER=Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
OLD_USER=parity.USER_LEGACY
OLD_ROOT=parity.ROOT_LEGACY
NEW_USER=parity.USER_REPLACEMENT
NEW_ROOT=parity.ROOT_REPLACEMENT
PRESERVE_USER=parity.CONTINUITY_USER
PRESERVE_ROOT=parity.CONTINUITY_ROOT
SOURCE_POLICY=Path("/opt/jason/current/config/production-desired-state.json")


class RootPreflightDenied(PermissionError):
    pass


def require(ok:bool,why:str)->None:
    if not ok:
        raise RootPreflightDenied("PMV4_E_ROOT_PREFLIGHT_"+why)


def evaluate(evidence:Mapping[str,Any])->dict[str,Any]:
    """Pure fail-closed decision; passed only independently measured evidence."""
    require(evidence.get("uid")==0,"ROOT_ONLY")
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
    require(p.returncode in (0,3),"SYSTEMD_READBACK_UNAVAILABLE")
    result=p.stdout.strip()
    require(result in ("active","inactive","failed"),"SYSTEMD_READBACK_UNKNOWN")
    return p.returncode==0 and result=="active"


def collect(*,runner:Callable[...,Any]=subprocess.run)->dict[str,Any]:
    """Live root probe; never issues commands other than read-only is-active."""
    require(os.geteuid()==0,"ROOT_ONLY")
    # Reuse the existing strict root-owned C/D/A1 and canary proof chains.
    from tools import pmv4_e_root_receipt_readback as rootproof
    from tools import pmv4_e_canary_acceptance_readback as canaryproof
    root_receipts=rootproof.inspect()
    canary=canaryproof.inspect()
    require(root_receipts.get("status") not in ("not_verified",None),
            "C_D_A1_ROOT_RECEIPT_UNVERIFIED")
    require(canary.get("status") not in ("not_verified",None),
            "NATIVE_CANARY_UNVERIFIED")
    # The exact protected live policy is independently checked by rootproof.
    # Additional freeze/breaker/scan evidence must be supplied by the
    # existing native root release controller, not inferred here.
    return {
        "uid":0, "root_cda1":"verified", "root_canary":"verified",
        "root_policy_valid":True,
        "marker_absent":not MARKER.exists() and not MARKER.is_symlink(),
        "user_active_old":{u:_active(u,user=True,runner=runner) for u in OLD_USER},
        "root_active_old":{u:_active(u,user=False,runner=runner) for u in OLD_ROOT},
        "user_active_new":{u:_active(u,user=True,runner=runner) for u in NEW_USER},
        "root_active_new":{u:_active(u,user=False,runner=runner) for u in NEW_ROOT},
        "user_monitoring":{u:_active(u,user=True,runner=runner) for u in PRESERVE_USER},
        "root_monitoring":{u:_active(u,user=False,runner=runner) for u in PRESERVE_ROOT},
        # Intentionally unspecified: root controller must inject separate
        # fresh trusted freeze, breaker and provider-backed scan evidence.
        "source_policy_valid":False,
        "breaker":"unknown","freeze":"unknown",
        "ticket_unique_owner":False,"scan_fresh":False,
        "duplicate_items":None,
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
