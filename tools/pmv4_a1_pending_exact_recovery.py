#!/usr/bin/env python3
"""Recover ONLY the already Owner-signed failed A1 shadow transaction.

No new Entra authorization, promotion, gateway startup, provider access, PMv3
release changes or standing recovery capability. The original exact signed
decision authorizes only restoring the original EMPTY shadow baseline.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

TRUSTED=Path("/usr/local/lib/jason/pmv4-trusted")
if os.geteuid()==0 and TRUSTED.is_dir():
    sys.path.insert(0,str(TRUSTED))
from tools import pmv4_shadow_release as shadow
from tools import pmv4_host_release_guard as host_guard

SOURCE="8c2064193d74cc41b52369681febbc0a74fa96f7"
ROLLBACK="0"*40
APPROVAL_ID="owner-mcp-319c697027a146beac98818e5305a971"
EXACT_SCOPE="7e1f62de1a10e46db934792967f43e03e778990d2764ea42cbdde1657dc61716"
EXACT_ROOT_EXECUTOR_SHA="ea259a6a281d3a04d16e7fe4a8fe7b90a00b78e02fe0c9dbecdadd5ccc1c9e1b"
ROOT=shadow.PRODUCTION_ROOT
ORIGINAL=Path("/run/jason-pmv4-a1-oneowner-8c20/installer.py")
RUN_DIR=Path("/run/jason-pmv4-a1-reconcile-8c20")
ROOT_SCRIPT=RUN_DIR/"recovery.py"
RECEIPT=ROOT/"receipts"/("owner-"+APPROVAL_ID+".json")
AUDIT=ROOT/"control"/"a1-exact-atomic-bootstrap.jsonl"
SOURCE_PROOF=Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+SOURCE+"/root-oneowner-proof.json")


class A1RecoveryDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:raise A1RecoveryDenied(reason)


def is_real_root_script()->None:
    need(os.geteuid()==0,"A1_RECOVERY_ROOT_TTY_REQUIRED")
    p=Path(__file__).resolve(strict=True)
    m=p.lstat()
    need(p==ROOT_SCRIPT and not p.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==0 and m.st_gid==0 and m.st_nlink==1
         and stat.S_IMODE(m.st_mode)==0o400,
         "A1_RECOVERY_SCRIPT_NOT_EXACT_ROOT_STAGE")
    parent=p.parent.lstat()
    need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==0
         and parent.st_gid==0 and stat.S_IMODE(parent.st_mode)==0o700,
         "A1_RECOVERY_STAGE_DIRECTORY_UNTRUSTED")


def original_executor():
    m=ORIGINAL.lstat()
    need(not ORIGINAL.is_symlink() and m.st_uid==0 and m.st_gid==0
         and m.st_nlink==1 and stat.S_ISREG(m.st_mode)
         and stat.S_IMODE(m.st_mode)==0o400,
         "A1_ORIGINAL_EXECUTOR_NOT_TRUSTED")
    raw=ORIGINAL.read_bytes()
    from hashlib import sha256
    need(sha256(raw).hexdigest()==EXACT_ROOT_EXECUTOR_SHA,
         "A1_ORIGINAL_OWNER_BOUND_EXECUTOR_CHANGED")
    spec=importlib.util.spec_from_file_location("a1_exact_owner_root",ORIGINAL)
    need(spec is not None and spec.loader is not None,
         "A1_ORIGINAL_EXECUTOR_IMPORT_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    need(module.CANDIDATE==SOURCE and module.ROLLBACK==ROLLBACK
         and module.ACTION=="pmv4-a1-one-owner-exact-shadow-bootstrap-and-activate-v1",
         "A1_ORIGINAL_RELEASE_SCOPE_UNTRUSTED")
    return module


def read_exact_receipt(*,expected_uid:int=0,expected_gid:int=0)->dict[str,Any]:
    need(RECEIPT.is_file() and not RECEIPT.is_symlink(),
         "A1_PREVIOUS_OWNER_RECEIPT_NOT_PRESENT")
    m=RECEIPT.lstat()
    need(m.st_uid==expected_uid and m.st_gid==expected_gid and m.st_nlink==1
         and stat.S_IMODE(m.st_mode)==0o600,
         "A1_PREVIOUS_RECEIPT_METADATA_CHANGED")
    r=shadow.read_json(RECEIPT)
    need(set(r)=={
        "schema_version","service","state","release_id",
        "approval_id","candidate_sha","rollback_sha",
        "manifest_sha256","scope_sha256","freeze_sha256",
        "started_at","no_pmv3_or_provider_mutation",
    } and r["schema_version"]=="1.0"
         and r["service"]=="jason-pmv4-shadow"
         and r["state"]=="started"
         and r["approval_id"]==APPROVAL_ID
         and r["release_id"]=="release-"+SOURCE[:16]
         and r["candidate_sha"]==SOURCE
         and r["rollback_sha"]==ROLLBACK
         and r["no_pmv3_or_provider_mutation"] is True,
         "A1_PENDING_RECEIPT_NOT_EXACT_OR_ALREADY_RECONCILED")
    need(len(list(RECEIPT.parent.glob("owner-*.json")))==1,
         "A1_MULTIPLE_PENDING_RECEIPTS")
    return r


def authenticate_historical_recovery(original,receipt:dict[str,Any]):
    plan,manifest,scope=original.plan_and_source()
    need(plan["scope_sha256"]==EXACT_SCOPE
         and manifest["candidate_sha"]==SOURCE
         and manifest["rollback_sha"]==ROLLBACK,
         "A1_ORIGINAL_IMMUTABLE_PLAN_CHANGED")
    proof=original.read_json(SOURCE_PROOF,maxsize=30000)
    need(proof.get("schema_version")=="1.0"
         and proof.get("approval_id")==APPROVAL_ID
         and proof.get("source_sha")==SOURCE
         and proof.get("scope_sha256")==EXACT_SCOPE
         and proof.get("manifest_sha256")==original.sha(original.canon(plan)),
         "A1_ORIGINAL_SIGNED_ROOT_PROOF_NOT_EXACT")
    journal=original.audit_rows()
    need(journal and journal[0]["event"]=="begin"
         and journal[0]["approval_id"]==APPROVAL_ID
         and journal[0]["details"]["parent_scope_sha256"]==EXACT_SCOPE
         and journal[0]["details"]["shadow_manifest_sha256"]==plan["shadow_manifest_sha256"]
         and all(r["approval_id"]==APPROVAL_ID for r in journal)
         and not any(r["event"]=="committed" for r in journal),
         "A1_ROOT_AUDIT_NOT_PENDING_OR_SCOPE_CHANGED")
    try:
        signed_start=datetime.fromisoformat(
            proof["signed_root_release"]["payload"]["issued_at"])
        native_start=datetime.fromisoformat(receipt["started_at"])
    except (TypeError,KeyError,ValueError) as exc:
        raise A1RecoveryDenied("A1_OWNER_NATIVE_RECEIPT_TIME_INVALID") from exc
    need(signed_start.tzinfo is not None and native_start.tzinfo is not None
         and signed_start<=native_start
         and native_start-signed_start<=timedelta(minutes=15),
         "A1_NATIVE_RECEIPT_NOT_FROM_ORIGINAL_CONSENT")
    public=shadow.read_pinned_root_owner_public_key(
        original.ROOT_PIN,require_root_owned=True)
    expected=((proof["signed_root_release"],EXACT_SCOPE,
               original.sha(original.canon(plan))),
              (proof["signed_shadow_release"],manifest["scope_sha256"],
               original.sha(original.canon(manifest))))
    historical_owners=[]
    for signed,signed_scope,signed_manifest in expected:
        owner=shadow.verify_exact_owner_release(
            signed,public_key=public,at=native_start,
            expected_candidate_sha=SOURCE,expected_rollback_sha=ROLLBACK,
            expected_release_id="release-"+SOURCE[:16],
            expected_scope_sha256=signed_scope,
            expected_manifest_sha256=signed_manifest,
            expected_freeze_sha256=plan["shadow_freeze_sha256"],
        )
        need(owner["approval_id"]==APPROVAL_ID,
             "A1_OWNER_PROOF_HISTORICAL_SIGNATURE_UNVERIFIED")
        historical_owners.append(owner)
    need(historical_owners[0]["owner_oid"]==historical_owners[1]["owner_oid"]
         and historical_owners[0]["owner_principal"]==historical_owners[1]["owner_principal"]
         and historical_owners[0]["issued_at"]==historical_owners[1]["issued_at"]
         and historical_owners[0]["expires_at"]==historical_owners[1]["expires_at"],
         "A1_ORIGINAL_ONE_OWNER_PROOF_PAIR_NOT_MATCHED")
    need(receipt["manifest_sha256"]==original.sha(original.canon(manifest))
         and receipt["scope_sha256"]==manifest["scope_sha256"]
         and receipt["freeze_sha256"]==plan["shadow_freeze_sha256"],
         "A1_NATIVE_JOURNAL_NOT_SIGNED_CHILD")
    return plan


def preflight():
    is_real_root_script()
    original=original_executor()
    receipt=read_exact_receipt()
    plan=authenticate_historical_recovery(original,receipt)
    need(original.CURRENT.is_symlink()
         and os.readlink(original.CURRENT)=="releases/"+ROLLBACK,
         "A1_PREVIOUS_EMPTY_BASELINE_POINTER_NOT_RESTORED")
    host=host_guard.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True
         and host.host_mutation_quiescent() is True,
         "A1_PROTECTED_PRODUCTION_NOT_READY_TO_RECOVER")
    need(original.sha(original.GLOBAL_FREEZE.read_bytes())==original.FREEZE_SHA
         and original.sha(original.GLOBAL_HOLD.read_bytes())==original.HOLD_SHA
         and original.active_shadow_allowlist(),
         "A1_PROTECTED_CONTROLS_CHANGED")
    adapter,controller=original.controller(host)
    need(adapter._owned_or_absent() is None,
         "A1_FAILED_SHADOW_STILL_PRESENT")
    return original,host,adapter,controller,plan


def recover():
    original,host,adapter,controller,plan=preflight()
    result=controller.reconcile_pending_rollback(
        rollback_acceptance=lambda prior:(
            host.preexisting_core_health() is True
            and host.protected_release_status().get("ready") is True
            and prior.name==ROLLBACK
            and original.shadow.read_json(prior/"baseline.json")=={
                "schema_version":"1.0","service":"jason-pmv4-shadow",
                "baseline":"no_prior_shadow_runtime"}
            and adapter._owned_or_absent() is None
        )
    )
    need(result.get("status")=="shadow_rollback_verified"
         and result.get("rollback_sha")==ROLLBACK,
         "A1_NATIVE_PENDING_ROLLBACK_NOT_ACCEPTED")
    print("A1_NATIVE_SIGNED_RECEIPT_ROLLBACK=VERIFIED",flush=True)
    # Only original-owner-root staged files are removable, using the exact
    # original root audit inodes; no new issuance or shadow promotion.
    original.cleanup_exact_unpromoted(APPROVAL_ID)
    original.append("reconciled_original_exact_owner_rollback",APPROVAL_ID,{
        "native_receipt_state":"rolled_back",
        "shadow_runtime_absent":True,
        "original_empty_baseline_restored":True,
        "new_owner_approval":False,
    })
    need(adapter._owned_or_absent() is None
         and original.CURRENT.is_symlink()
         and os.readlink(original.CURRENT)=="releases/"+ROLLBACK
         and not original.TARGET.exists()
         and not original.APPROVED.exists()
         and not original.REVIEWED.exists()
         and not original.TOKEN.exists()
         and host.preexisting_core_health() is True,
         "A1_EXACT_SOURCE_OR_CORE_RECOVERY_INCOMPLETE")
    print("A1_ORIGINAL_SIGNED_ROOT_RELEASE_RECOVERY=VERIFIED",flush=True)
    print("OWNER_APPROVAL_REUSED_FOR_ROLLBACK_ONLY="+APPROVAL_ID,flush=True)
    print("NEW_OWNER_AUTHENTICATION_REQUIRED=false",flush=True)
    print("TICKET_CORE_AND_FREEZE_UNCHANGED=true",flush=True)


def main()->int:
    parser=argparse.ArgumentParser()
    options=parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--preflight",action="store_true")
    options.add_argument("--recover",action="store_true")
    args=parser.parse_args()
    try:
        if args.preflight:
            preflight()
            print("A1_ORIGINAL_SIGNED_PENDING_RECOVERY_PREFLIGHT=PASS")
            print("PRODUCTION_MUTATIONS=false; NEW_OWNER_APPROVAL=false")
        else:recover()
        return 0
    except Exception as exc:
        reason=str(exc)
        if len(reason)>130 or "/" in reason:reason="A1_RECOVERY_INTERNAL_DENIAL"
        print("A1_RECOVERY=DENIED "+type(exc).__name__+":"+reason,
              flush=True,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
