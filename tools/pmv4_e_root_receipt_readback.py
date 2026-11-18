#!/usr/bin/env python3
"""Root-only, strictly read-only PMv4 Stage E protected acceptance evidence.

This code never authorizes retirement, disables legacy workers or writes a
protected source. It is a preparation component for a separately signed
one-owner Stage E retirement release, not a privileged installer.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

STAGE_C_PATH=Path(
    "/var/lib/jason/pmv4-stage-c/receipts/"
    "owner-owner-mcp-8fb03f9faea44336b216456b5afcf663.json")
STAGE_D_PATH=Path(
    "/etc/jason-owner-release/pmv4-d-runbook-read/"
    "6dc78887b636dce5066871a3076bfe75bcd84ad3-accepted.json")
A1_RECEIPT=Path(
    "/var/lib/jason/pmv4-shadow/receipts/"
    "owner-owner-mcp-e547ca784f76418391ca5bd938afd237.json")
A1_AUDIT=Path(
    "/var/lib/jason/pmv4-shadow/control/"
    "a1-exact-atomic-bootstrap-v5-9859463e5255.jsonl")
ACTIVE_POLICY=Path(
    "/etc/jason/release-readback-recovery/production-desired-state.json")
STAGE_C_SHA="7aaa2c3fc3ac51279c3488a16ab39b6e7a03007e"
STAGE_D_SHA="6dc78887b636dce5066871a3076bfe75bcd84ad3"
STAGE_D_SCOPE="72a0a13156aa29eab559d36ff44e56e38dc5ee22f0b3ca6b0cfc3c95ae42cf01"
A1_SHA="9859463e5255ecf7040de21d73e9f4062b46a18e"
A1_PRIOR="75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
A1_OWNER="owner-mcp-e547ca784f76418391ca5bd938afd237"
A1_SCOPE="71c4e48acc2cba183ebd2d87d974614f351b6d35364aa971865960b898b79c40"
A1_MANIFEST="3fde47c74c59b7d93cdc8e04f232e58e0540610901fb5942fab0bffad9fd0678"
A1_FREEZE="c1e6aa23c48df9f87aa98c549086ad65a6fd38716e5a1a5cafd727fbd69fe928"
ACTIVE_POLICY_SHA="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"

LEGACY_REQUIRED_USER={
    "jason-release-manager.timer",
    "jason-release-approval-only.timer",
    "jason-support-repair-worker.timer",
}
LEGACY_REQUIRED_SYSTEM={
    "jason-release-control-readback.timer",
    "jason-release-control-transition.timer",
    "jason-release-host-reconcile.path",
}


class StageERootEvidenceDenied(PermissionError):
    pass


def require(ok:bool,code:str)->None:
    if not ok:
        raise StageERootEvidenceDenied("PMV4_E_"+code)


def canonical(record:Mapping[str,Any])->bytes:
    return json.dumps(record,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def trusted_bytes(path:Path, *, maximum:int=100_000,mode:int=0o600)->bytes:
    try:
        meta=path.lstat()
        require(stat.S_ISREG(meta.st_mode) and not path.is_symlink()
                and meta.st_uid==0 and meta.st_gid==0 and meta.st_nlink==1
                and stat.S_IMODE(meta.st_mode)==mode
                and 0<meta.st_size<=maximum,
                "PROTECTED_SOURCE_NOT_TRUSTED")
        raw=path.read_bytes()
        require(len(raw)==meta.st_size,
                "PROTECTED_SOURCE_CHANGED_DURING_READ")
        return raw
    except (OSError,ValueError,TypeError) as exc:
        raise StageERootEvidenceDenied("PMV4_E_PROTECTED_SOURCE_UNAVAILABLE") from exc


def exact_json(path:Path, *, maximum:int=100_000)->dict[str,Any]:
    try:
        record=json.loads(trusted_bytes(path,maximum=maximum))
        require(isinstance(record,dict),"ROOT_DOCUMENT_NOT_OBJECT")
        return record
    except (ValueError,TypeError) as exc:
        raise StageERootEvidenceDenied("PMV4_E_ROOT_DOCUMENT_INVALID") from exc


def c_acceptance(path:Path|None=None)->None:
    path=path if path is not None else STAGE_C_PATH
    x=exact_json(path)
    scans=x.get("scan_cycle_ids")
    require(x.get("schema_version")=="1.0"
            and x.get("status")=="postmigration_stage_c_accepted"
            and x.get("candidate_sha")==STAGE_C_SHA
            and x.get("approval_id")=="owner-mcp-8fb03f9faea44336b216456b5afcf663"
            and isinstance(scans,list) and len(scans)==2
            and all(isinstance(s,str) and s.startswith("scan-")
                    and len(s)==37 for s in scans)
            and scans[0]!=scans[1]
            and x.get("no_database_relocation") is True
            and x.get("mcp_restarts")==0,
            "C_ROOT_ACCEPTANCE_NOT_EXACT")


def d_acceptance(path:Path|None=None)->None:
    path=path if path is not None else STAGE_D_PATH
    x=exact_json(path)
    require(x.get("schema_version")=="1.0"
            and x.get("status")=="independent_runbook_read_service_accepted"
            and x.get("source_sha")==STAGE_D_SHA
            and x.get("scope_sha256")==STAGE_D_SCOPE
            and isinstance(x.get("owner_approval_id"),str)
            and x["owner_approval_id"].startswith("pmv4-d-owner-")
            and x.get("native_drift")=="pass"
            and x.get("provider_writes")==0
            and x.get("runtime_restarts")==0
            and x.get("mcp_restarts")==0
            and x.get("ticket_core_restarts")==0
            and x.get("production_freeze_unchanged") is True,
            "D_ROOT_ACCEPTANCE_NOT_EXACT")


def a1_acceptance(path:Path|None=None)->None:
    path=path if path is not None else A1_RECEIPT
    x=exact_json(path)
    require(x.get("schema_version")=="1.0"
            and x.get("service")=="jason-pmv4-shadow"
            and x.get("state")=="accepted"
            and x.get("candidate_sha")==A1_SHA
            and x.get("rollback_sha")==A1_PRIOR
            and x.get("approval_id")==A1_OWNER
            and x.get("release_id")=="release-"+A1_SHA[:16]
            and x.get("manifest_sha256")==A1_MANIFEST
            and x.get("scope_sha256")==A1_SCOPE
            and x.get("freeze_sha256")==A1_FREEZE
            and x.get("no_pmv3_or_provider_mutation") is True,
            "A1_ROOT_ACCEPTANCE_NOT_EXACT")


def a1_audit(path:Path|None=None)->int:
    path=path if path is not None else A1_AUDIT
    raw=trusted_bytes(path,maximum=250_000)
    prev="0"*64
    lines=raw.splitlines()
    require(5<len(lines)<120,"A1_ROOT_AUDIT_LENGTH_UNTRUSTED")
    events=[]
    for i,line in enumerate(lines):
        require(0<len(line)<15000,"A1_AUDIT_ROW_LENGTH_INVALID")
        try:
            row=json.loads(line)
        except (TypeError,ValueError) as exc:
            raise StageERootEvidenceDenied("PMV4_E_A1_AUDIT_ROW_INVALID") from exc
        require(isinstance(row,dict),"A1_AUDIT_ROW_NOT_OBJECT")
        digest=row.pop("hash",None)
        require(isinstance(digest,str)
                and len(digest)==64
                and row.get("schema_version")=="1.0"
                and type(row.get("index")) is int
                and row["index"]==i
                and row.get("previous_sha256")==prev
                and row.get("approval_id")==A1_OWNER
                and row.get("source_sha")==A1_SHA
                and sha256(canonical(row)).hexdigest()==digest,
                "A1_ROOT_AUDIT_HASH_OR_SCOPE_CHANGED")
        prev=digest
        events.append(row.get("event"))
    require(events[0]=="begin" and events[-1]=="committed"
            and "requires_review" not in events
            and "rolled_back" not in events,
            "A1_ROOT_AUDIT_NOT_COMMITTED")
    return len(lines)


def live_policy(path:Path|None=None)->None:
    path=path if path is not None else ACTIVE_POLICY
    raw=trusted_bytes(path,maximum=100_000)
    require(sha256(raw).hexdigest()==ACTIVE_POLICY_SHA,
            "ROOT_DESIRED_STATE_NOT_REVIEWED")
    try:
        policy=json.loads(raw)
    except (TypeError,ValueError) as exc:
        raise StageERootEvidenceDenied("PMV4_E_POLICY_NOT_JSON") from exc
    require(isinstance(policy,dict) and policy.get("schema_version")=="1.0"
            and LEGACY_REQUIRED_USER.issubset(
                set(policy.get("required_user_units") or []))
            and LEGACY_REQUIRED_SYSTEM.issubset(
                set(policy.get("required_system_units") or []))
            and "jason-runbook-management-read.service" in (
                policy.get("allowed_system_units") or []),
            "ROOT_POLICY_PRE_RETIREMENT_UNTRUSTED")


def inspect()->dict[str,Any]:
    require(os.geteuid()==0,"EXACT_ROOT_READ_ONLY_REQUIRED")
    c_acceptance()
    d_acceptance()
    a1_acceptance()
    count=a1_audit()
    live_policy()
    return {
        "status":"pre_retirement_root_acceptance_verified",
        "phase":"E","stage_c_root_acceptance_verified":True,
        "stage_d_root_acceptance_verified":True,
        "a1_root_acceptance_verified":True,
        "a1_root_audit_rows":count,
        "protected_live_policy_sha256":ACTIVE_POLICY_SHA,
        "legacy_units_still_required":True,
        "replacement_controller_parity_verified":False,
        "retirement_authorized":False,
        "production_mutations":False,
    }


if __name__=="__main__":
    try:
        print(json.dumps(inspect(),sort_keys=True))
    except StageERootEvidenceDenied as exc:
        print(json.dumps({"status":"not_verified","code":str(exc),
                          "retirement_authorized":False,
                          "production_mutations":False},sort_keys=True))
        raise SystemExit(2)
