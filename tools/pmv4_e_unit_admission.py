#!/usr/bin/env python3
"""Fail-closed admission for six future PMv4 timer/path unit services.

No production service may start from a mere name change or source CI.
Absent root-accepted marker = legacy mode. Invalid marker = DENY, never
silently restore an old worker. This module only reads; no provider writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

# The later root installer must deploy BOTH the guard and its existing
# source-only scheduling contract under one immutable root-owned tree.
TRUST_ROOT=Path("/opt/jason/pmv4-e-trusted")
TRUST_ENTRY=TRUST_ROOT/"tools/pmv4_e_unit_admission.py"
if Path(__file__).resolve()==TRUST_ENTRY:
    sys.path.insert(0,str(TRUST_ROOT))
from tools import pmv4_e_scheduler_parity as parity

ACCEPTED=Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
ACTION="pmv4-e-oneowner-six-unit-replacement-and-retirement-v1"
FREEZE="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
PRIOR_POLICY="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"
OWNER_RE=re.compile(r"^owner-mcp-[0-9a-f]{32}$")
SOURCE_RE=re.compile(r"^[0-9a-f]{40}$")
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")
ROLE_UNITS={
    "engineering":("jason-pmv4-engineering.timer",False),
    "release-approval":("jason-pmv4-release-approval.timer",False),
    "component-release":("jason-pmv4-component-release.timer",False),
    "component-transition":("jason-pmv4-component-transition.timer",True),
    "component-readback":("jason-pmv4-component-readback.timer",True),
    "component-reconcile":("jason-pmv4-component-reconcile.path",True),
}


class PMv4EUnitAdmissionDenied(PermissionError):
    pass


def need(ok:bool,why:str)->None:
    if not ok:
        raise PMv4EUnitAdmissionDenied("PMV4_E_SCHEDULER_"+why)


def read_root_marker(path:Path=ACCEPTED)->dict[str,Any]|None:
    """Check root ownership and exact accepted scope before unit activation."""
    try:
        meta=path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PMv4EUnitAdmissionDenied("PMV4_E_SCHEDULER_RECEIPT_NOT_ACCESSIBLE") from exc
    need(not path.is_symlink()
         and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==0 and meta.st_gid==0 and meta.st_nlink==1
         and stat.S_IMODE(meta.st_mode)==0o444
         and 0<meta.st_size<=12000,
         "ROOT_RECEIPT_FILE_UNTRUSTED")
    for parent in (path.parent,path.parent.parent):
        try:
            p=parent.lstat()
        except OSError as exc:
            raise PMv4EUnitAdmissionDenied(
                "PMV4_E_SCHEDULER_ROOT_PARENT_NOT_ACCESSIBLE") from exc
        need(not parent.is_symlink() and stat.S_ISDIR(p.st_mode)
             and p.st_uid==0 and p.st_gid==0 and p.st_mode&0o022==0,
             "ROOT_PARENT_NOT_TRUSTED")
    try:
        raw=path.read_bytes()
        need(len(raw)==meta.st_size,"ROOT_RECEIPT_CHANGED")
        doc=json.loads(raw)
    except PMv4EUnitAdmissionDenied:
        raise
    except (OSError,ValueError,TypeError) as exc:
        raise PMv4EUnitAdmissionDenied(
            "PMV4_E_SCHEDULER_ROOT_RECEIPT_INVALID") from exc
    need(isinstance(doc,dict)
         and set(doc)=={
             "schema_version","action","state","source_sha",
             "owner_approval_id","source_scope_sha256",
             "source_rollback_sha","prior_policy_sha256",
             "accepted_policy_sha256","production_freeze_sha256",
             "replacement_user_units","replacement_system_units",
             "retired_user_units","retired_system_units",
             "watchdog_retargets_engineering","root_reconcile_no_legacy_install",
             "root_parity_checks_passed","native_drift",
             "accepted_at","rollback_receipt_sha256",
         }
         and doc["schema_version"]=="1.0"
         and doc["action"]==ACTION
         and doc["state"]=="accepted"
         and isinstance(doc["source_sha"],str)
         and SOURCE_RE.fullmatch(doc["source_sha"]) is not None
         and isinstance(doc["owner_approval_id"],str)
         and OWNER_RE.fullmatch(doc["owner_approval_id"]) is not None
         and isinstance(doc["source_scope_sha256"],str)
         and SHA256_RE.fullmatch(doc["source_scope_sha256"]) is not None
         and isinstance(doc["source_rollback_sha"],str)
         and SOURCE_RE.fullmatch(doc["source_rollback_sha"]) is not None,
         "ROOT_OWNER_RELEASE_IDENTITY_NOT_EXACT")
    # No caller can choose or override a new policy digest, Owner proof,
    # or rollback. Only the separately reviewed root transaction issues it.
    need(doc.get("prior_policy_sha256")==PRIOR_POLICY
         and doc.get("production_freeze_sha256")==FREEZE
         and all(isinstance(doc.get(k),str)
                 and SHA256_RE.fullmatch(doc[k]) is not None
                 for k in (
                    "source_scope_sha256",
                    "accepted_policy_sha256","rollback_receipt_sha256"))
         and doc["accepted_policy_sha256"]!=doc["prior_policy_sha256"]
         and all(isinstance(doc[k],list)
                 and all(isinstance(unit,str) for unit in doc[k])
                 and len(doc[k])==len(set(doc[k]))
                 for k in (
                     "replacement_user_units","replacement_system_units",
                     "retired_user_units","retired_system_units"))
         and doc["source_rollback_sha"]!=doc["source_sha"]
         and set(doc.get("replacement_user_units") or [])
             ==parity.USER_REPLACEMENT
         and set(doc.get("replacement_system_units") or [])
             ==parity.ROOT_REPLACEMENT
         and set(doc.get("retired_user_units") or [])
             ==parity.USER_LEGACY
         and set(doc.get("retired_system_units") or [])
             ==parity.ROOT_LEGACY
         and doc.get("watchdog_retargets_engineering") is True
         and doc.get("root_reconcile_no_legacy_install") is True
         and doc.get("root_parity_checks_passed") is True
         and doc.get("native_drift")=="pass",
         "ROOT_ACCEPTED_SCHEDULING_SCOPE_NOT_VERIFIED")
    try:
        when=datetime.fromisoformat(doc["accepted_at"].replace("Z","+00:00"))
    except (TypeError,AttributeError,ValueError) as exc:
        raise PMv4EUnitAdmissionDenied(
            "PMV4_E_SCHEDULER_ROOT_ACCEPTED_TIME_INVALID") from exc
    need(when.tzinfo is not None
         and when<=datetime.now(timezone.utc),
         "ROOT_ACCEPTANCE_TIME_NOT_HISTORICAL")
    return doc


def active_mode(*,root_path:Path=ACCEPTED)->str:
    return "replacement" if read_root_marker(root_path) is not None else "legacy"


def require_unit(role:str,*,root_path:Path=ACCEPTED,
                 uid:int|None=None)->dict[str,Any]:
    need(role in ROLE_UNITS,"UNREVIEWED_UNIT_ROLE")
    name,is_root=ROLE_UNITS[role]
    effective=os.geteuid() if uid is None else uid
    need((effective==0 if is_root else effective==1000),
         "UNEXPECTED_SERVICE_IDENTITY")
    need(active_mode(root_path=root_path)=="replacement",
         "ROOT_REPLACEMENT_CUTOVER_NOT_ACCEPTED")
    return {
        "status":"accepted_for_one_configured_service",
        "role":role,"unit":name,
        "production_changes_performed":False,
        "owner_authority_issued":False,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",required=True,choices=sorted(ROLE_UNITS))
    args=parser.parse_args(argv)
    try:
        result=require_unit(args.mode)
    except PMv4EUnitAdmissionDenied as exc:
        print(str(exc)[:130])
        return 255
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
