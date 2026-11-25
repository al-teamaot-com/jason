#!/usr/bin/env python3
"""Recover ONLY the already Owner-signed failed A1 v3 shadow transaction.

No new Entra authorization, promotion, gateway startup, provider access, PMv3
release changes or standing recovery capability. The original exact signed
decision authorizes only restoring the original EMPTY shadow baseline.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import argparse
import importlib.util
import json
import subprocess
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

SOURCE="c999216a3df9d2422833b90403c31530c323f467"
ROLLBACK="0"*40
APPROVAL_ID="owner-mcp-5bb561044cd444908d06280377822a9d"
EXACT_SCOPE="d7aa6c4643151f131bdbb23c18de47fde105ba36ce684547c412a4fef62a0afb"
EXACT_ROOT_EXECUTOR_SHA="bb8e88189c6a8cef3e9dec19bd4d637de2779e3c7f4c3f506c3185462dfbe83d"
ROOT=shadow.PRODUCTION_ROOT
ORIGINAL=Path("/run/jason-pmv4-a1-v3-c999216a3df9/installer.py")
RUN_DIR=Path("/run/jason-pmv4-a1-v3-consumed-rollback-c999216a")
ROOT_SCRIPT=RUN_DIR/"recovery.py"
RECEIPT=ROOT/"receipts"/("owner-"+APPROVAL_ID+".json")
AUDIT=ROOT/"control"/"a1-exact-atomic-bootstrap-v3-c999216a3df9.jsonl"
SHADOW="jason-pmv4-shadow-gateway"
PROJECT="jason-pmv4-shadow"
VOLUME="jason-pmv4-shadow-state"
EXPECTED_BIND=VOLUME+":/home/node/.openclaw:rw"
EXACT_CONTAINER_ID="950a0411ffd6cdd64f507c2a46156f2582748e87dc2c81755a3d24c743eb3837"
EXACT_IMAGE="sha256:238ff47453519f765390880d4ea9170b266c1b3226788eb5d91b54eb80d447c5"
DENIED_KEYS=("OPENAI_API_KEY","ANTHROPIC_API_KEY","AZURE_OPENAI_API_KEY",
             "GOOGLE_API_KEY","GEMINI_API_KEY","OPENROUTER_API_KEY",
             "DATTO_API_KEY","AUTOTASK_API_KEY","AWS_ACCESS_KEY_ID",
             "AWS_SECRET_ACCESS_KEY")
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
         and module.ACTION=="pmv4-a1-one-owner-exact-disconnected-shadow-bootstrap-v3",
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
    required={
        "schema_version","service","state","release_id",
        "approval_id","candidate_sha","rollback_sha",
        "manifest_sha256","scope_sha256","freeze_sha256",
        "started_at","no_pmv3_or_provider_mutation",
    }
    if r.get("state")=="rolled_back":
        required|={"finished_at","reconciled"}
    need(set(r)==required
         and r["schema_version"]=="1.0"
         and r["service"]=="jason-pmv4-shadow"
         and r["state"] in ("started","rolled_back")
         and r["approval_id"]==APPROVAL_ID
         and r["release_id"]=="release-"+SOURCE[:16]
         and r["candidate_sha"]==SOURCE
         and r["rollback_sha"]==ROLLBACK
         and r["no_pmv3_or_provider_mutation"] is True,
         "A1_PENDING_RECEIPT_NOT_EXACT_OR_ALREADY_RECONCILED")
    # Historical v1 and v2 receipts may exist. They must be settled and
    # authentic-looking, not ignored or mistaken for a second pending grant.
    pending=[]
    for path in RECEIPT.parent.iterdir():
        need(path.name.startswith("owner-") and path.suffix==".json"
             and not path.is_symlink() and path.is_file(),
             "A1_UNEXPECTED_RECEIPT_OBJECT")
        info=path.lstat()
        need(info.st_uid==expected_uid and info.st_gid==expected_gid
             and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,
             "A1_OTHER_RECEIPT_NOT_TRUSTED")
        other=shadow.read_json(path)
        need(isinstance(other,dict)
             and isinstance(other.get("approval_id"),str)
             and path.name=="owner-"+other["approval_id"]+".json"
             and other.get("state") in ("started","rolled_back","accepted"),
             "A1_UNTRUSTED_RECEIPT_OBJECT")
        if other.get("state")=="started": pending.append(path)
    need(pending==([RECEIPT] if r["state"]=="started" else []),
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
         and not any(r["event"] in ("committed","rolled_back")
                     for r in journal)
         and journal[-1]["event"] in (
             "requires_review", "exact_owner_rollback_intent",
             "exact_owner_rollback_native_verified",
             "reconciled_original_exact_owner_rollback"),
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


def inspect_exact_shadow(*,allow_absent:bool=True):
    proc=subprocess.run(["/usr/bin/docker","inspect",SHADOW],
                        shell=False,capture_output=True,text=True,
                        check=False,timeout=15)
    if proc.returncode:
        need(allow_absent and proc.returncode==1
             and proc.stderr.rstrip("\n") in (
                 "Error: No such object: "+SHADOW,
                 "error: no such object: "+SHADOW)
             and proc.stdout in ("", "[]", "[]\n"),
             "A1_V3_DOCKER_INSPECT_NOT_EXACT_ABSENCE")
        return None
    try: data=json.loads(proc.stdout)
    except (TypeError,ValueError) as exc:
        raise A1RecoveryDenied("A1_V3_DOCKER_INSPECT_NOT_JSON") from exc
    need(isinstance(data,list) and len(data)==1
         and isinstance(data[0],dict),
         "A1_V3_DOCKER_INSPECT_NOT_SINGLE")
    return data[0]


def only_exact_compose_project(*,expected_present:bool)->None:
    p=subprocess.run(["/usr/bin/docker","ps","-a","--filter",
                      "label=com.docker.compose.project="+PROJECT,
                      "--format","{{.Names}}"],shell=False,
                      capture_output=True,text=True,timeout=15,check=False)
    expected=[SHADOW] if expected_present else []
    need(p.returncode==0 and p.stdout.splitlines()==expected,
         "A1_V3_OTHER_COMPOSE_PROJECT_CONTAINER")


def validate_exact_running_shadow(d:dict[str,Any])->None:
    config=d.get("Config") or {}
    host=d.get("HostConfig") or {}
    labels=config.get("Labels") or {}
    need(d.get("Id")==EXACT_CONTAINER_ID and d.get("Image")==EXACT_IMAGE
         and d.get("Name")=="/"+SHADOW
         and labels.get("com.aot.jason.component")=="pmv4-shadow"
         and labels.get("com.aot.jason.production-core")=="excluded"
         and labels.get("com.aot.jason.provider-mutation")=="disabled"
         and labels.get("com.docker.compose.project")==PROJECT
         and labels.get("com.docker.compose.service")=="pmv4-shadow-gateway",
         "A1_V3_RUNNING_SHADOW_IS_NOT_ORIGINAL")
    need(host.get("NetworkMode")=="none"
         and host.get("ReadonlyRootfs") is True
         and host.get("Privileged") is False
         and config.get("User")=="1000:1000"
         and host.get("CapDrop")==["ALL"]
         and host.get("CapAdd") in (None,[])
         and isinstance(host.get("SecurityOpt"),list)
         and "no-new-privileges:true" in host["SecurityOpt"]
         and host.get("Init") is True
         and (host.get("RestartPolicy") or {}).get("Name") in ("no","")
         and host.get("PidsLimit")==256
         and host.get("Memory")==2*1024**3
         and host.get("NanoCpus")==1_000_000_000
         and host.get("PublishAllPorts") in (None,False)
         and host.get("PortBindings") in (None,{})
         and host.get("Devices") in (None,[])
         and host.get("Binds")==[EXPECTED_BIND],
         "A1_V3_RUNNING_SHADOW_SECURITY_DIFFERENT")
    mounts=d.get("Mounts")
    need(isinstance(mounts,list) and 1<=len(mounts)<=2
         and sum(isinstance(x,dict) and x.get("Type")=="volume"
                 and x.get("Name")==VOLUME
                 and x.get("Destination")=="/home/node/.openclaw"
                 for x in mounts)==1
         and all(isinstance(x,dict) and (
             (x.get("Type")=="volume" and x.get("Name")==VOLUME
              and x.get("Destination")=="/home/node/.openclaw")
             or (x.get("Type")=="tmpfs" and x.get("Destination")=="/tmp"))
             for x in mounts),
         "A1_V3_RUNNING_SHADOW_MOUNTS_DIFFERENT")
    env=config.get("Env")
    need(isinstance(env,list)
         and all(isinstance(e,str) and not any(e.startswith(k+"=")
                 for k in DENIED_KEYS) for e in env),
         "A1_V3_RUNNING_SHADOW_PROVIDER_CREDENTIALS_PRESENT")


def shutdown_original_shadow(original)->None:
    compose=original.ROOT/"control"/"docker-compose.yml"
    meta=compose.lstat()
    need(compose.is_file() and not compose.is_symlink()
         and meta.st_uid==0 and meta.st_nlink==1
         and not meta.st_mode&0o022
         and original.sha(compose.read_bytes())==
            "892f7a506fcb759887697f4a9882a76e2377969a701a4ca1aff240f6cb23277b",
         "A1_V3_ORIGINAL_ROLLBACK_COMPOSE_NOT_TRUSTED")
    token=original.TOKEN.read_text().strip()
    need(32<=len(token)<=128,"A1_V3_ORIGINAL_TOKEN_UNTRUSTED")
    # Exactly the originally approved isolated project, no --volumes and
    # no --remove-orphans. Do not modify existing production containers.
    proc=subprocess.run(["/usr/bin/docker","compose","--project-name",
                         PROJECT,"-f",str(compose),"down"],
                        shell=False,capture_output=True,text=True,
                        timeout=90,check=False,env={
                            "PATH":"/usr/bin:/bin",
                            "PMV4_SHADOW_IMAGE_SHA":EXACT_IMAGE,
                            "PMV4_SHADOW_GATEWAY_TOKEN":token})
    need(proc.returncode==0,"A1_V3_EXACT_SHADOW_DOWN_FAILED")
    need(inspect_exact_shadow() is None,
         "A1_V3_SHADOW_STILL_PRESENT_AFTER_DOWN")
    only_exact_compose_project(expected_present=False)


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
    live=inspect_exact_shadow()
    if live is not None:validate_exact_running_shadow(live)
    only_exact_compose_project(expected_present=live is not None)
    return original,host,adapter,controller,plan


def postflight()->None:
    is_real_root_script()
    original=original_executor()
    receipt=read_exact_receipt()
    authenticate_historical_recovery(original,receipt)
    need(receipt["state"]=="rolled_back",
         "A1_V3_NATIVE_SIGNED_RECEIPT_NOT_ROLLED_BACK")
    need(original.audit_rows()[-1]["event"]==
         "reconciled_original_exact_owner_rollback",
         "A1_V3_ORIGINAL_ROOT_AUDIT_NOT_CLOSED")
    need(original.CURRENT.is_symlink()
         and os.readlink(original.CURRENT)=="releases/"+ROLLBACK,
         "A1_V3_EMPTY_BASELINE_NOT_RESTORED")
    need(inspect_exact_shadow() is None,
         "A1_V3_SHADOW_STILL_RUNNING_AFTER_ROLLBACK")
    only_exact_compose_project(expected_present=False)
    need(all(not p.exists() and not p.is_symlink()
             for p in (original.TARGET,original.APPROVED,
                       original.REVIEWED,original.TOKEN)),
         "A1_V3_ROOT_SOURCE_CLEANUP_NOT_COMPLETE")
    host=host_guard.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True,
         "A1_V3_POSTFLIGHT_PRODUCTION_CORE_UNVERIFIED")
    print("A1_V3_PREVIOUS_OWNER_ROOT_ROLLBACK_POSTFLIGHT=PASS",flush=True)


def recover()->None:
    original,host,adapter,controller,plan=preflight()
    with host.host_release_transaction():
        host._assert_protected_release_state()
        need(host.preexisting_core_health() is True
             and original.sha(original.GLOBAL_FREEZE.read_bytes())==original.FREEZE_SHA
             and original.sha(original.GLOBAL_HOLD.read_bytes())==original.HOLD_SHA,
             "A1_V3_PRODUCTION_CORE_CHANGED_UNDER_LOCK")
        current=inspect_exact_shadow()
        if current is not None:validate_exact_running_shadow(current)
        only_exact_compose_project(expected_present=current is not None)
        need(original.CURRENT.is_symlink()
             and os.readlink(original.CURRENT)=="releases/"+ROLLBACK,
             "A1_V3_SHADOW_POINTER_CHANGED_BEFORE_ROLLBACK")
        receipt=read_exact_receipt()
        authenticate_historical_recovery(original,receipt)
        if original.audit_rows()[-1]["event"]=="requires_review":
            original.append("exact_owner_rollback_intent",APPROVAL_ID,{
                "original_owner_approval":True,
                "new_owner_approval":False,
                "exact_container_id":EXACT_CONTAINER_ID,
                "volumes_deleted":False,
            })
        if current is not None:
            shutdown_original_shadow(original)
        need(inspect_exact_shadow() is None,
             "A1_V3_FAILED_SHADOW_NOT_ABSENT")
        only_exact_compose_project(expected_present=False)
        if receipt["state"]=="started":
            # Already own both host locks. Never recurse through the public
            # lock-taking method. The native private path still takes its
            # dedicated shadow release lock and validates exact receipt.
            result=controller._reconcile_pending_rollback_locked(
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
                 "A1_V3_NATIVE_PENDING_ROLLBACK_NOT_VERIFIED")
            original.append("exact_owner_rollback_native_verified",APPROVAL_ID,{
                "native_receipt_state":"rolled_back",
                "new_owner_approval":False,
            })
        need(read_exact_receipt()["state"]=="rolled_back",
             "A1_V3_PREVIOUS_NATIVE_RECEIPT_NOT_ROLLED_BACK")
        original.cleanup_exact_unpromoted(APPROVAL_ID)
        original.append("reconciled_original_exact_owner_rollback",APPROVAL_ID,{
            "native_receipt_state":"rolled_back",
            "shadow_runtime_absent":True,
            "original_empty_baseline_restored":True,
            "new_owner_approval":False,
        })
    postflight()
    print("A1_V3_ORIGINAL_EXACT_OWNER_ROLLBACK=VERIFIED",flush=True)
    print("NEW_OWNER_AUTHENTICATION_REQUIRED=false",flush=True)
    print("TICKET_CORE_AND_PRODUCTION_FREEZE_UNCHANGED=true",flush=True)


def main()->int:
    parser=argparse.ArgumentParser()
    options=parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--preflight",action="store_true")
    options.add_argument("--recover",action="store_true")
    options.add_argument("--postflight",action="store_true")
    args=parser.parse_args()
    try:
        if args.preflight:
            preflight()
            print("A1_ORIGINAL_SIGNED_PENDING_RECOVERY_PREFLIGHT=PASS")
            print("PRODUCTION_MUTATIONS=false; NEW_OWNER_APPROVAL=false")
        elif args.recover:recover()
        else:postflight()
        return 0
    except Exception as exc:
        reason=str(exc)
        if len(reason)>130 or "/" in reason:reason="A1_RECOVERY_INTERNAL_DENIAL"
        print("A1_RECOVERY=DENIED "+type(exc).__name__+":"+reason,
              flush=True,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
