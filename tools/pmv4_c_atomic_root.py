#!/usr/bin/env python3
"""One exact Owner-authorized PMv4 Stage C Ticket Core cutover.

Source-only until copied to a root-owned 0400 /run stage by the exact launcher.
Preflight is read-only. Execute is the only mutating path and requires an exact
cryptographically signed Owner proof. Later PMv4 stages are NOT authorized.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

# Root release subprocess resolution is pinned; reviewed helpers may invoke
# "docker" but cannot inherit an Owner-controlled PATH.
os.environ["PATH"]="/usr/bin:/bin"

HERE=Path(__file__).resolve()
if HERE.parent.name=="tools":
    sys.path.insert(0,str(HERE.parents[1]))
else:
    sys.path.insert(0,str(HERE.parent/"src"))

from tools import deploy_live_container as clone
from tools import pmv4_c_service_manifest as service_contract
from tools import pmv4_c_sqlite_family_handoff as sqlite_handoff
from tools import pmv4_host_release_guard as host_guard
from tools import pmv4_shadow_ci as protected_ci

ACTION="pmv4-c-one-owner-exact-ticket-core-cutover-v1"
OWNER_SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OWNER_PUBLIC_KEY=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
WATCHDOG=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
TICKET_SOURCE=Path("/var/lib/jason/openclaw")
TICKET_TARGET=Path("/var/lib/jason/ticket-core")
SHARED_TARGET=Path("/var/lib/jason/governed-ticket-shared")
STAGE_C_ROOT=Path("/var/lib/jason/pmv4-stage-c")
CONTAINERS=("jason-runtime","jason-mcp-pilot")
WORKER=service_contract.CONTAINER_NAME

COMMON_STATE_ENV={
    "JASON_AUTONOMY_WORKER_DB":
        "/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3",
    "JASON_AUTONOMY_PROMOTION_DB":
        "/var/lib/jason/ticket-core/playbook-autonomy.sqlite3",
    "JASON_AUTONOMY_TARGETED_WAKE_DB":
        "/var/lib/jason/ticket-core/autonomy-targeted-wakes.sqlite3",
    "JASON_TEAMS_IDENTITY_BINDINGS_DB":
        "/var/lib/jason/governed-ticket-shared/teams-identity-bindings.sqlite3",
    "JASON_ORCHESTRATION_EVENTS_DB":
        "/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3",
    "JASON_GOVERNED_EXECUTION_DB":
        "/var/lib/jason/governed-ticket-shared/governed-execution.sqlite3",
    "JASON_RESOLUTION_MEMORY_DB":
        "/var/lib/jason/governed-ticket-shared/resolution-memory.sqlite3",
    "JASON_REFLECTION_DB":
        "/var/lib/jason/governed-ticket-shared/reflection.sqlite3",
    "JASON_MODEL_USAGE_DB":
        "/var/lib/jason/governed-ticket-shared/model-usage.sqlite3",
}
RUNTIME_ENV_OVERRIDES={
    **COMMON_STATE_ENV,"JASON_TICKET_WORKER_HOSTING":"external",
}
MCP_ENV_OVERRIDES=dict(COMMON_STATE_ENV)

PLAN_KEYS={
    "schema_version","action","candidate_sha","rollback_sha",
    "production_lkg_sha","worker_image_digest",
    "runtime_container_id","mcp_container_id",
    "runtime_image_digest","mcp_image_digest",
    "freeze_sha256","hold_sha256",
    "watchdog_path","watchdog_base_sha256","watchdog_candidate_sha256",
    "service_manifest_sha256","root_executor_sha256","owner_issuer_sha256",
    "staged_source_files","db_identities","credential_paths",
    "provider_state_metadata","runtime_env_overrides","mcp_env_overrides",
    "service_restarts","normal_ticket_processing_after_activation",
    "two_scan_acceptance","owner_consents","standing_authority",
    "later_stages_authorized","baseline_scan_cycle_id","baseline_scanned_at",
    "scope_sha256",
}

class StageCRootDenied(RuntimeError):
    pass

def need(value:bool,code:str)->None:
    if not value:
        raise StageCRootDenied(code)

def canon(value:Mapping[str,Any])->bytes:
    return json.dumps(dict(value),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def sha(raw:bytes)->str:
    return sha256(raw).hexdigest()

def read_json(path:Path, *, maxsize:int=3_000_000)->dict[str,Any]:
    try:
        info=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_nlink==1 and 0<info.st_size<=maxsize,
             "C_SOURCE_DOCUMENT_UNTRUSTED")
        value=json.loads(path.read_bytes())
        need(isinstance(value,dict),"C_SOURCE_DOCUMENT_NOT_OBJECT")
        return value
    except (OSError,ValueError,TypeError) as exc:
        raise StageCRootDenied("C_SOURCE_DOCUMENT_UNAVAILABLE") from exc

def _trusted_module(path:Path,digest:str,name:str):
    meta=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==0 and not meta.st_mode&0o022
         and sha(path.read_bytes())==digest,
         "C_OWNER_SIGNER_TRUST_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "C_OWNER_SIGNER_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _run(args:list[str], *, check:bool=True,
         capture:bool=False, timeout:int=30, env:dict[str,str]|None=None):
    need(args and args[0].startswith("/"),"C_COMMAND_NOT_ABSOLUTE")
    return subprocess.run(
        args,check=check,text=True,timeout=timeout,env=env,
        capture_output=capture,
    )

def _docker_json(name:str)->dict[str,Any]:
    need(name in {CONTAINERS[0],CONTAINERS[1],WORKER}
         or name.startswith("jason-runtime-rollback-pmv4c-")
         or name.startswith("jason-mcp-pilot-rollback-pmv4c-"),
         "C_DOCKER_NAME_NOT_ALLOWLISTED")
    proc=_run(["/usr/bin/docker","inspect",name],check=False,capture=True)
    need(proc.returncode==0 and len(proc.stdout)<=3_000_000,
         "C_DOCKER_INSPECT_UNAVAILABLE")
    try:
        rows=json.loads(proc.stdout)
    except ValueError as exc:
        raise StageCRootDenied("C_DOCKER_INSPECT_INVALID") from exc
    need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),
         "C_DOCKER_INSPECT_INVALID")
    return rows[0]

def _docker_exists(name:str)->bool:
    proc=_run(["/usr/bin/docker","inspect",name],
              check=False,capture=True,timeout=15)
    return proc.returncode==0

def _container_env(container:Mapping[str,Any])->dict[str,str]:
    out={}
    for item in (container.get("Config") or {}).get("Env") or []:
        need(isinstance(item,str) and "=" in item,"C_CONTAINER_ENV_INVALID")
        key,value=item.split("=",1)
        out[key]=value
    return out

def _container_running(name:str)->bool:
    return bool((_docker_json(name).get("State") or {}).get("Running"))

def _metadata(path:Path)->dict[str,int]:
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_nlink==1,"C_FILE_IDENTITY_NOT_REGULAR")
    return {
        "device":info.st_dev,"inode":info.st_ino,"uid":info.st_uid,
        "gid":info.st_gid,"mode":stat.S_IMODE(info.st_mode),
    }

def _dir_metadata(path:Path)->dict[str,int]:
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(info.st_mode),
         "C_DIRECTORY_IDENTITY_NOT_TRUSTED")
    return {
        "device":info.st_dev,"inode":info.st_ino,"uid":info.st_uid,
        "gid":info.st_gid,"mode":stat.S_IMODE(info.st_mode),
    }

def _plan(path:Path)->dict[str,Any]:
    plan=read_json(path)
    need(set(plan)==PLAN_KEYS and plan["schema_version"]=="1.0"
         and plan["action"]==ACTION
         and plan["owner_consents"]==1
         and plan["standing_authority"] is False
         and plan["later_stages_authorized"] is False
         and plan["normal_ticket_processing_after_activation"] is True
         and plan["two_scan_acceptance"] is True
         and plan["service_restarts"]==list(CONTAINERS)
         and plan["runtime_env_overrides"]==RUNTIME_ENV_OVERRIDES
         and plan["mcp_env_overrides"]==MCP_ENV_OVERRIDES,
         "C_PLAN_SCHEMA_OR_AUTHORITY_NOT_EXACT")
    scope=plan["scope_sha256"]
    unsigned=dict(plan);unsigned.pop("scope_sha256")
    need(isinstance(scope,str) and sha(canon(unsigned))==scope,
         "C_PLAN_SCOPE_HASH_MISMATCH")
    candidate=plan["candidate_sha"]
    rollback=plan["rollback_sha"]
    need(isinstance(candidate,str) and len(candidate)==40
         and all(x in "0123456789abcdef" for x in candidate)
         and isinstance(rollback,str) and len(rollback)==40
         and rollback==plan["production_lkg_sha"]
         and plan["watchdog_path"]==str(WATCHDOG),
         "C_PLAN_REVISION_INVALID")
    need(path.parent.name=="pmv4-c-"+candidate
         and path.name=="root-release-plan.json",
         "C_PLAN_ARTIFACT_PATH_NOT_EXACT")
    return plan

def _artifact(plan_path:Path)->Path:
    return plan_path.parent

def _service_manifest(plan_path:Path,plan:Mapping[str,Any])->dict[str,Any]:
    path=_artifact(plan_path)/"service-manifest.json"
    doc=read_json(path)
    need(sha(canon(doc))==plan["service_manifest_sha256"]
         and doc.get("source_sha")==plan["candidate_sha"]
         and doc.get("image_digest")==plan["worker_image_digest"]
         and doc.get("owner_authorization_issued") is False
         and doc.get("production_mutations") is False,
         "C_SERVICE_MANIFEST_CHANGED")
    return doc

def _watchdog_base_artifact(plan_path:Path,plan:Mapping[str,Any])->bytes:
    path=_artifact(plan_path)/"production-desired-state.base.json"
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_nlink==1 and 0<info.st_size<200_000,
         "C_WATCHDOG_BASE_ARTIFACT_UNTRUSTED")
    raw=path.read_bytes()
    need(sha(raw)==plan["watchdog_base_sha256"],
         "C_WATCHDOG_BASE_ARTIFACT_CHANGED")
    return raw

def _watchdog_candidate(plan_path:Path,plan:Mapping[str,Any])->bytes:
    path=_artifact(plan_path)/"production-desired-state.stage-c.json"
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_nlink==1 and 0<info.st_size<200_000,
         "C_WATCHDOG_CANDIDATE_UNTRUSTED")
    raw=path.read_bytes()
    need(sha(raw)==plan["watchdog_candidate_sha256"],
         "C_WATCHDOG_CANDIDATE_CHANGED")
    base_raw=_watchdog_base_artifact(plan_path,plan)
    try:
        candidate=json.loads(raw)
        current=json.loads(WATCHDOG.read_bytes())
        base_artifact=json.loads(base_raw)
    except (OSError,ValueError,TypeError) as exc:
        raise StageCRootDenied("C_WATCHDOG_POLICY_UNAVAILABLE") from exc
    need(isinstance(candidate,dict) and isinstance(current,dict)
         and sha(WATCHDOG.read_bytes())==plan["watchdog_base_sha256"],
         "C_WATCHDOG_BASE_CHANGED")
    need(current==base_artifact,"C_WATCHDOG_ACTIVE_BASE_NOT_REVIEWED")
    expected=json.loads(json.dumps(current))
    allowed=expected.get("allowed_running_containers")
    need(isinstance(allowed,list)
         and WORKER not in allowed
         and "jason-pmv4-shadow-gateway" in allowed,
         "C_WATCHDOG_BASE_NOT_EXPECTED")
    allowed.append(WORKER)
    need(candidate==expected,"C_WATCHDOG_TRANSITION_NOT_SINGLE_ADDITION")
    return raw

def _stage_trust(plan_path:Path,plan:Mapping[str,Any])->None:
    need(os.geteuid()==0,"C_ROOT_EXECUTION_REQUIRED")
    script=Path(__file__).resolve(strict=True)
    info=script.lstat()
    need(not script.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid==0 and info.st_gid==0
         and stat.S_IMODE(info.st_mode)==0o400
         and sha(script.read_bytes())==plan["root_executor_sha256"],
         "C_ROOT_EXECUTOR_NOT_EXACT")
    stage=script.parent/"src"
    for rel,digest in plan["staged_source_files"].items():
        item=stage/rel
        meta=item.lstat()
        need(not item.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_uid==0 and meta.st_gid==0
             and stat.S_IMODE(meta.st_mode)==0o400
             and sha(item.read_bytes())==digest,
             "C_STAGED_SOURCE_NOT_EXACT:"+rel)

def _runner_as_al(args,**kwargs):
    need(isinstance(args,(list,tuple)) and len(args)>1
         and args[0] in ("/usr/bin/gh","gh") and args[1]=="api",
         "C_GITHUB_COMMAND_NOT_ALLOWLISTED")
    return subprocess.run(
        ["/usr/sbin/runuser","-u","al","--","/usr/bin/gh",*args[1:]],
        **kwargs)

def _source_and_ci(plan:Mapping[str,Any])->None:
    main=subprocess.check_output(
        ["/usr/sbin/runuser","-u","al","--","/usr/bin/gh","api",
         "repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
        text=True,timeout=20).strip()
    need(main==plan["candidate_sha"],"C_PROTECTED_MAIN_CHANGED")
    need(protected_ci.protected_main_ci_verified(
        plan["candidate_sha"],runner=_runner_as_al),
        "C_PROTECTED_MAIN_CI_NOT_CURRENT")

def _control_continuity(plan:Mapping[str,Any])->host_guard.IndependentHostGuard:
    need(sha(FREEZE.read_bytes())==plan["freeze_sha256"]
         and sha(HOLD.read_bytes())==plan["hold_sha256"]
         and Path("/opt/jason/current").resolve(strict=True).name
             ==plan["production_lkg_sha"],
         "C_PRODUCTION_CONTROL_CHANGED")
    host=host_guard.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True
         and host.host_mutation_quiescent() is True,
         "C_PROTECTED_CORE_NOT_READY")
    return host

def _container_baseline(plan:Mapping[str,Any])->None:
    for name,id_key,image_key in (
        ("jason-runtime","runtime_container_id","runtime_image_digest"),
        ("jason-mcp-pilot","mcp_container_id","mcp_image_digest"),
    ):
        item=_docker_json(name)
        need(item.get("Id")==plan[id_key]
             and item.get("Image")==plan[image_key]
             and (item.get("State") or {}).get("Running") is True,
             "C_PROTECTED_CONTAINER_CHANGED:"+name)
    need(not _docker_exists(WORKER),"C_EXTERNAL_WORKER_ALREADY_EXISTS")
    short=plan["candidate_sha"][:12]
    need(not _docker_exists("jason-runtime-rollback-pmv4c-"+short)
         and not _docker_exists("jason-mcp-pilot-rollback-pmv4c-"+short),
         "C_ROLLBACK_CONTAINER_ALREADY_EXISTS")
    image=_run(["/usr/bin/docker","image","inspect",
                plan["worker_image_digest"]],check=False,capture=True)
    need(image.returncode==0,"C_WORKER_IMAGE_NOT_LOCAL")
    rows=json.loads(image.stdout)
    need(len(rows)==1 and rows[0].get("Id")==plan["worker_image_digest"],
         "C_WORKER_IMAGE_ID_MISMATCH")
    labels=(rows[0].get("Config") or {}).get("Labels") or {}
    need(labels.get("com.aot.jason.component")=="pmv4-ticket-core"
         and labels.get("com.aot.jason.source_revision")==plan["candidate_sha"]
         and labels.get("com.aot.jason.lifecycle")=="production-candidate",
         "C_WORKER_IMAGE_NOT_REVIEWED")

def _service_manifest_from_plan(plan:Mapping[str,Any])->dict[str,Any]:
    candidate=plan["candidate_sha"]
    path=Path("/srv/jason/archive/engineering-artifacts")/(
        "pmv4-c-"+candidate)/"service-manifest.json"
    doc=read_json(path)
    need(sha(canon(doc))==plan["service_manifest_sha256"],
         "C_SERVICE_MANIFEST_CHANGED")
    return doc

def _data_baseline(plan:Mapping[str,Any])->None:
    allowed_modes={
        "/var/lib/jason/openclaw/governed-execution.sqlite3":0o644,
        "/var/lib/jason/openclaw/resolution-memory.sqlite3":0o644,
    }
    for raw,expected in plan["db_identities"].items():
        path=Path(raw)
        actual=_metadata(path)
        need(actual==expected,"C_DB_IDENTITY_CHANGED:"+path.name)
        if expected["mode"]!=0o600:
            need(allowed_modes.get(raw)==expected["mode"],
                 "C_UNREVIEWED_DB_MODE:"+path.name)
    expected_credentials=sorted({
        str(m["Source"]) for m in _service_manifest_from_plan(plan).get("mounts",[])
        if str(m.get("Destination","")).startswith("/run/jason-secrets/")
    })
    need(plan["credential_paths"]==expected_credentials,
         "C_CREDENTIAL_PATH_SCOPE_CHANGED")
    for raw in expected_credentials:
        path=Path(raw)
        try: info=path.lstat()
        except OSError as exc:
            raise StageCRootDenied("C_CREDENTIAL_FILE_UNAVAILABLE") from exc
        mode=stat.S_IMODE(info.st_mode)
        need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_nlink==1 and info.st_uid in (0,1000)
             and not (mode&0o022) and 0<info.st_size<65536,
             "C_CREDENTIAL_FILE_NOT_TRUSTED")
    for raw,expected in plan["provider_state_metadata"].items():
        need(_dir_metadata(Path(raw))==expected,
             "C_PROVIDER_STATE_IDENTITY_CHANGED")
    need(not TICKET_TARGET.exists() and not TICKET_TARGET.is_symlink()
         and not SHARED_TARGET.exists() and not SHARED_TARGET.is_symlink(),
         "C_TARGET_STATE_ALREADY_EXISTS")

def _verify_owner(plan_path:Path,plan:Mapping[str,Any], *,
                  recovery:bool=False)->dict[str,Any]:
    proof_path=_artifact(plan_path)/"root-oneowner-proof.json"
    record=read_json(proof_path)
    need(record.get("schema_version")=="1.0"
         and record.get("action")==ACTION
         and record.get("source_sha")==plan["candidate_sha"]
         and record.get("scope_sha256")==plan["scope_sha256"]
         and record.get("plan_sha256")==sha(canon(plan))
         and isinstance(record.get("signed_release"),dict),
         "C_OWNER_PROOF_NOT_EXACT")
    signer=_trusted_module(OWNER_SIGNER,OWNER_SIGNER_SHA,"c_owner_signer")
    public=signer.read_pinned_root_owner_public_key(OWNER_PUBLIC_KEY)
    at=datetime.now(timezone.utc)
    if recovery:
        rows=_audit_rows(plan)
        need(rows and rows[0]["event"]=="begin",
             "C_HISTORICAL_OWNER_AUDIT_MISSING")
        at=datetime.fromisoformat(rows[0]["occurred_at"])
    approved=signer.verify_exact_owner_release(
        record["signed_release"],public_key=public,at=at,
        expected_candidate_sha=plan["candidate_sha"],
        expected_rollback_sha=plan["rollback_sha"],
        # The pinned issuer enforces the cryptographic release-* namespace.
        # Stage C host artifacts remain separately named pmv4-c-*.
        expected_release_id="release-"+plan["candidate_sha"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=sha(canon(plan)),
        expected_freeze_sha256=plan["freeze_sha256"])
    need(approved["approval_id"]==record["approval_id"],
         "C_OWNER_SIGNATURE_APPROVAL_MISMATCH")
    return approved

def _audit_path(plan:Mapping[str,Any])->Path:
    return STAGE_C_ROOT/"control"/(
        "cutover-"+plan["candidate_sha"][:12]+".jsonl")

def _receipt_path(plan:Mapping[str,Any],approval:str)->Path:
    return STAGE_C_ROOT/"receipts"/("owner-"+approval+".json")

def _audit_rows(plan:Mapping[str,Any])->list[dict[str,Any]]:
    path=_audit_path(plan)
    if not path.exists():
        return []
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600,
         "C_AUDIT_NOT_TRUSTED")
    rows=[];prior="0"*64
    for raw in path.read_bytes().splitlines():
        item=json.loads(raw)
        digest=item.pop("hash")
        need(item.get("index")==len(rows)
             and item.get("previous_sha256")==prior
             and item.get("candidate_sha")==plan["candidate_sha"]
             and sha(canon(item))==digest,
             "C_AUDIT_CHAIN_INVALID")
        rows.append({**item,"hash":digest});prior=digest
    return rows

def _append(plan:Mapping[str,Any],approval:str,event:str,
            details:Mapping[str,Any])->None:
    path=_audit_path(plan)
    rows=_audit_rows(plan)
    entry={
        "schema_version":"1.0","index":len(rows),
        "previous_sha256":rows[-1]["hash"] if rows else "0"*64,
        "event":event,"approval_id":approval,
        "candidate_sha":plan["candidate_sha"],
        "occurred_at":datetime.now(timezone.utc).isoformat(),
        "details":dict(details),
    }
    entry["hash"]=sha(canon(entry))
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"ab") as out:
            out.write(canon(entry)+b"\n");out.flush();os.fsync(out.fileno())
    except BaseException:
        raise

def _ensure_root_state()->None:
    if not STAGE_C_ROOT.exists():
        STAGE_C_ROOT.mkdir(mode=0o700)
    for part in (STAGE_C_ROOT,STAGE_C_ROOT/"control",STAGE_C_ROOT/"receipts"):
        if not part.exists():
            part.mkdir(mode=0o700)
        info=part.lstat()
        need(not part.is_symlink() and stat.S_ISDIR(info.st_mode)
             and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,
             "C_ROOT_STATE_NOT_TRUSTED")

def _atomic_policy(raw:bytes, *, meta:os.stat_result)->None:
    parent=WATCHDOG.parent
    fd,name=tempfile.mkstemp(prefix=".pmv4-c-policy-",dir=parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.chmod(temp,stat.S_IMODE(meta.st_mode))
        os.chown(temp,meta.st_uid,meta.st_gid)
        os.replace(temp,WATCHDOG)
        dfd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        temp.unlink(missing_ok=True)

def _prepare_dir(path:Path)->None:
    need(not path.exists() and not path.is_symlink(),
         "C_TARGET_DIRECTORY_ALREADY_EXISTS")
    path.mkdir(mode=0o700)
    os.chown(path,1000,1000)
    os.chmod(path,0o700)
    info=path.lstat()
    need(info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o700,
         "C_TARGET_DIRECTORY_NOT_EXACT")

def _repair_modes(plan:Mapping[str,Any])->dict[str,int]:
    changed={}
    for raw,expected in plan["db_identities"].items():
        path=Path(raw)
        original=expected["mode"]
        if original==0o600:
            continue
        need(raw in (
            "/var/lib/jason/openclaw/governed-execution.sqlite3",
            "/var/lib/jason/openclaw/resolution-memory.sqlite3",
        ) and original==0o644,"C_MODE_REPAIR_NOT_ALLOWLISTED")
        os.chmod(path,0o600);changed[raw]=original
        need(stat.S_IMODE(path.lstat().st_mode)==0o600,
             "C_MODE_REPAIR_FAILED")
    return changed

def _restore_modes(changed:Mapping[str,int], *, target:bool)->None:
    for raw,mode in changed.items():
        src=Path(raw)
        path=(SHARED_TARGET/src.name) if target else src
        if path.exists():
            os.chmod(path,mode)

def _clone_command(plan:Mapping[str,Any], source_name:str,
                   target_name:str, kind:str,
                   overrides:Mapping[str,str],
                   add_dirs:tuple[Path,...]):
    need(kind in ("runtime","mcp"),"C_CLONE_KIND_INVALID")
    image=(plan["runtime_image_digest"] if kind=="runtime"
           else plan["mcp_image_digest"])
    cmd,env,secondary,source=clone._build_create_command(
        live=source_name,image=image,source_revision=plan["production_lkg_sha"],
        harden=True,set_env=tuple(k+"="+v for k,v in overrides.items()))
    existing={str(x.get("Destination")) for x in source.get("Mounts") or []}
    extra=[]
    for directory in add_dirs:
        need(str(directory) not in existing,"C_CLONE_MOUNT_DESTINATION_COLLISION")
        extra += ["--mount",
                  "type=bind,src="+str(directory)+",dst="+str(directory)]
    need(cmd and cmd[-1]==image and "--name" in cmd,
         "C_CLONE_COMMAND_SHAPE_INVALID")
    index=cmd.index("--name")+1
    need(cmd[index]==source_name,"C_CLONE_SOURCE_NAME_MISMATCH")
    cmd[index]=target_name
    cmd=cmd[:-1]+extra+[cmd[-1]]
    cmd[0]="/usr/bin/docker"
    return cmd,env,secondary


def _worker_create(manifest:Mapping[str,Any])->list[str]:
    args=["/usr/bin/docker","create","--name",WORKER,
          "--user",manifest["user"],
          "--restart",manifest["restart_policy"],
          "--read-only","--cap-drop","ALL",
          "--security-opt","no-new-privileges:true",
          "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=32m",
          "--memory",str(manifest["memory_bytes"]),
          "--cpus","1.0","--pids-limit",str(manifest["pids_limit"]),
          "--network",manifest["network_mode"]]
    for key,value in sorted(manifest["environment"].items()):
        args += ["--env",key+"="+value]
    for m in manifest["mounts"]:
        spec=("type=bind,src="+m["Source"]+",dst="+m["Destination"]
              +(",readonly" if not m["RW"] else ""))
        args += ["--mount",spec]
    for key,value in sorted(manifest["labels"].items()):
        args += ["--label",key+"="+value]
    h=manifest["healthcheck"]
    args += [
        "--health-cmd",h["test"][1],
        "--health-interval",str(h["interval_ns"])+"ns",
        "--health-timeout",str(h["timeout_ns"])+"ns",
        "--health-retries",str(h["retries"]),
        "--health-start-period",str(h["start_period_ns"])+"ns",
    ]
    args.append(manifest["image_digest"])
    args.extend(manifest["command"])
    return args

def _connect_and_start(name:str,secondary:list[str],
                       *,env:dict[str,str]|None=None)->None:
    for network in secondary:
        _run(["/usr/bin/docker","network","connect",network,name],env=env)
    _run(["/usr/bin/docker","start",name],env=env)

def _wait_container(name:str, *, healthy:bool, seconds:int=180)->dict[str,Any]:
    end=time.monotonic()+seconds
    last=None
    while time.monotonic()<end:
        try:last=_docker_json(name)
        except StageCRootDenied:
            time.sleep(2);continue
        state=last.get("State") or {}
        if state.get("Running") is True:
            if not healthy or (state.get("Health") or {}).get("Status")=="healthy":
                return last
        time.sleep(2)
    raise StageCRootDenied("C_CONTAINER_HEALTH_TIMEOUT:"+name)

def _stop(name:str)->None:
    if _docker_exists(name) and _container_running(name):
        _run(["/usr/bin/docker","stop","-t","30",name],timeout=45)

def _rm(name:str)->None:
    if _docker_exists(name):
        _run(["/usr/bin/docker","rm","-f",name],check=False,timeout=30)

def _verify_stopped(rollback_runtime:str,rollback_mcp:str)->None:
    need(not _docker_exists("jason-runtime")
         and not _docker_exists("jason-mcp-pilot")
         and _docker_exists(rollback_runtime)
         and _docker_exists(rollback_mcp)
         and not _container_running(rollback_runtime)
         and not _container_running(rollback_mcp),
         "C_PRODUCER_QUIESCENCE_CONTAINER_STATE_INVALID")

def _wait_ticket_idle(path:Path, *, seconds:int=150)->tuple[str,str]:
    end=time.monotonic()+seconds
    uri="file:"+str(path)+"?mode=ro"
    while time.monotonic()<end:
        with closing(sqlite3.connect(uri,uri=True,timeout=2)) as db:
            heartbeat=db.execute(
                "SELECT last_completed_at,state FROM autonomy_ticket_worker_heartbeat "
                "WHERE singleton_id=1").fetchone()
            latest=db.execute(
                "SELECT cycle_id,scanned_at FROM autonomy_ticket_scan_cycle "
                "ORDER BY scanned_at DESC LIMIT 1").fetchone()
        if (heartbeat is not None and latest is not None
            and heartbeat[1] in ("idle","completed")
            and isinstance(heartbeat[0],str)
            and latest[1]==heartbeat[0]):
            return str(latest[0]),str(latest[1])
        time.sleep(2)
    raise StageCRootDenied("C_PRECUTOVER_WORKER_DID_NOT_BECOME_IDLE")


def _scan_rows(path:Path,baseline:str)->list[tuple]:
    uri="file:"+str(path)+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,timeout=2)) as db:
        return list(db.execute(
            "SELECT cycle_id,scanned_at,pages_traversed,provider_items,"
            "duplicate_items,evaluated FROM autonomy_ticket_scan_cycle "
            "WHERE scanned_at > ? ORDER BY scanned_at ASC",(baseline,)))

def _wait_two_scans(baseline_scanned_at:str, *, seconds:int=240)->list[tuple]:
    db=TICKET_TARGET/"autonomy-operational-work.sqlite3"
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        rows=_scan_rows(db,baseline_scanned_at)
        valid=[r for r in rows if r[2]>0 and r[3]>0 and r[4]==0 and r[5]>0]
        if len(valid)>=2 and len({r[0] for r in valid})>=2:
            return valid[:2]
        time.sleep(5)
    raise StageCRootDenied("C_TWO_REAL_SCAN_ACCEPTANCE_TIMEOUT")

def preflight(plan_path:Path):
    plan=_plan(plan_path)
    _stage_trust(plan_path,plan)
    _service_manifest(plan_path,plan)
    _watchdog_candidate(plan_path,plan)
    _source_and_ci(plan)
    host=_control_continuity(plan)
    _container_baseline(plan)
    _data_baseline(plan)
    audit=_audit_path(plan)
    need(not audit.exists() and not audit.is_symlink(),
         "C_RELEASE_ALREADY_ATTEMPTED")
    proof=_artifact(plan_path)/"root-oneowner-proof.json"
    need(not proof.exists() and not proof.is_symlink(),
         "C_OWNER_ALREADY_AUTHORIZED")
    return plan,host

def execute(plan_path:Path)->None:
    plan=_plan(plan_path)
    _stage_trust(plan_path,plan)
    manifest=_service_manifest(plan_path,plan)
    candidate_policy=_watchdog_candidate(plan_path,plan)
    _source_and_ci(plan)
    host=_control_continuity(plan)
    _container_baseline(plan)
    _data_baseline(plan)
    owner=_verify_owner(plan_path,plan)
    approval=owner["approval_id"]
    runtime_rb="jason-runtime-rollback-pmv4c-"+plan["candidate_sha"][:12]
    mcp_rb="jason-mcp-pilot-rollback-pmv4c-"+plan["candidate_sha"][:12]
    runtime_cmd,runtime_env,runtime_secondary=_clone_command(
        plan,"jason-runtime","jason-runtime","runtime",
        plan["runtime_env_overrides"],(TICKET_TARGET,SHARED_TARGET))
    mcp_cmd,mcp_env,mcp_secondary=_clone_command(
        plan,"jason-mcp-pilot","jason-mcp-pilot","mcp",
        plan["mcp_env_overrides"],(TICKET_TARGET,SHARED_TARGET))
    worker_cmd=_worker_create(manifest)
    policy_meta=WATCHDOG.lstat()
    base_policy=WATCHDOG.read_bytes()
    changed_modes={}
    ticket_plan=None;shared_plan=None
    new_writer_admitted=False
    old_containers_renamed=False
    with host.host_release_transaction():
        host._assert_protected_release_state()
        _ensure_root_state()
        need(not _audit_path(plan).exists(),"C_RELEASE_ALREADY_ATTEMPTED")
        need(host.preexisting_core_health() is True,
             "C_CORE_NOT_HEALTHY_UNDER_RELEASE_LOCK")
        _container_baseline(plan);_data_baseline(plan)
        baseline_cycle,baseline_scanned=_wait_ticket_idle(
            TICKET_SOURCE/"autonomy-operational-work.sqlite3")
        _append(plan,approval,"begin",{
            "scope_sha256":plan["scope_sha256"],
            "runtime_restart":True,"mcp_restart":True,
            "external_worker":WORKER,
            "cutover_baseline_cycle_id":baseline_cycle,
            "cutover_baseline_scanned_at":baseline_scanned})
        try:
            _stop("jason-runtime");_stop("jason-mcp-pilot")
            _run(["/usr/bin/docker","rename","jason-runtime",runtime_rb])
            _run(["/usr/bin/docker","rename","jason-mcp-pilot",mcp_rb])
            old_containers_renamed=True
            _verify_stopped(runtime_rb,mcp_rb)
            _prepare_dir(TICKET_TARGET);_prepare_dir(SHARED_TARGET)
            changed_modes=_repair_modes(plan)
            fence=lambda: need(host._held is True,
                               "C_NATIVE_HOST_RELEASE_LOCK_LOST")
            stopped=lambda: _verify_stopped(runtime_rb,mcp_rb)
            ticket_plan=sqlite_handoff.preview(
                TICKET_SOURCE,TICKET_TARGET,kind="ticket",uid=1000)
            shared_plan=sqlite_handoff.preview(
                TICKET_SOURCE,SHARED_TARGET,kind="shared",uid=1000)
            _append(plan,approval,"data_plan",{
                "ticket_plan_sha256":ticket_plan.digest,
                "shared_plan_sha256":shared_plan.digest,
                "bytes_not_copied":
                    ticket_plan.bytes_not_copied+shared_plan.bytes_not_copied})
            ticket_journal=STAGE_C_ROOT/"control"/(
                "pmv4-c-"+ticket_plan.digest+".jsonl")
            shared_journal=STAGE_C_ROOT/"control"/(
                "pmv4-c-"+shared_plan.digest+".jsonl")
            sqlite_handoff.move_under_signed_root(
                ticket_plan,journal=ticket_journal,
                signed_host_fence=fence,verify_all_producers_stopped=stopped,
                journal_owner_uid=0)
            sqlite_handoff.move_under_signed_root(
                shared_plan,journal=shared_journal,
                signed_host_fence=fence,verify_all_producers_stopped=stopped,
                journal_owner_uid=0)
            _atomic_policy(candidate_policy,meta=policy_meta)
            need(sha(WATCHDOG.read_bytes())==plan["watchdog_candidate_sha256"],
                 "C_WATCHDOG_POLICY_INSTALL_FAILED")
            _run(runtime_cmd,env=runtime_env)
            _connect_and_start("jason-runtime",runtime_secondary,env=runtime_env)
            _run(mcp_cmd,env=mcp_env)
            _connect_and_start("jason-mcp-pilot",mcp_secondary,env=mcp_env)
            _wait_container("jason-runtime",healthy=True,seconds=120)
            _wait_container("jason-mcp-pilot",healthy=False,seconds=120)
            _run(worker_cmd)
            _run(["/usr/bin/docker","start",WORKER])
            # From this point forward no stale pre-cutover DB path may be
            # restored even if health/acceptance later fails.
            new_writer_admitted=True
            worker=_wait_container(WORKER,healthy=True,seconds=180)
            service_contract.validate_effective_inspect(worker,manifest)
            _append(plan,approval,"activated",{
                "new_canonical_state":True,
                "runtime_image_unchanged":True,
                "mcp_image_unchanged":True,
                "worker_image":plan["worker_image_digest"]})
        except BaseException as original:
            try:
                _rm(WORKER)
                _rm("jason-runtime");_rm("jason-mcp-pilot")
                if not new_writer_admitted:
                    if shared_plan is not None:
                        shared_journal=STAGE_C_ROOT/"control"/(
                            "pmv4-c-"+shared_plan.digest+".jsonl")
                        if shared_journal.exists():
                            sqlite_handoff.rollback_before_new_writer(
                                shared_plan,journal=shared_journal,
                                signed_host_fence=lambda: need(host._held,
                                    "C_NATIVE_HOST_RELEASE_LOCK_LOST"),
                                verify_no_new_writer_or_provider_action=lambda:None,
                                journal_owner_uid=0)
                    if ticket_plan is not None:
                        ticket_journal=STAGE_C_ROOT/"control"/(
                            "pmv4-c-"+ticket_plan.digest+".jsonl")
                        if ticket_journal.exists():
                            sqlite_handoff.rollback_before_new_writer(
                                ticket_plan,journal=ticket_journal,
                                signed_host_fence=lambda: need(host._held,
                                    "C_NATIVE_HOST_RELEASE_LOCK_LOST"),
                                verify_no_new_writer_or_provider_action=lambda:None,
                                journal_owner_uid=0)
                    _restore_modes(changed_modes,target=False)
                    if sha(WATCHDOG.read_bytes())!=plan["watchdog_base_sha256"]:
                        _atomic_policy(base_policy,meta=policy_meta)
                    for target in (TICKET_TARGET,SHARED_TARGET):
                        if target.exists() and not any(target.iterdir()):
                            target.rmdir()
                    if old_containers_renamed:
                        _run(["/usr/bin/docker","rename",runtime_rb,"jason-runtime"])
                        _run(["/usr/bin/docker","rename",mcp_rb,"jason-mcp-pilot"])
                        _run(["/usr/bin/docker","start","jason-mcp-pilot"])
                        _run(["/usr/bin/docker","start","jason-runtime"])
                        _wait_container("jason-runtime",healthy=True,seconds=90)
                        _wait_container("jason-mcp-pilot",healthy=False,seconds=90)
                    _append(plan,approval,"rolled_back_pre_activation",{
                        "original_paths_restored":True})
                elif new_writer_admitted:
                    _recover_to_embedded_new_canonical(
                        plan_path,plan,approval,host,already_held=True)
            except BaseException:
                _append(plan,approval,"requires_review",{
                    "reason":"C_FAIL_CLOSED_RECOVERY"})
            raise original
    print("PMV4_C_ATOMIC_ACTIVATION=VERIFIED",flush=True)
    print("OWNER_APPROVALS_TOTAL=1",flush=True)

def _recover_to_embedded_new_canonical(
    plan_path:Path,plan:Mapping[str,Any],approval:str,
    host:host_guard.IndependentHostGuard, *, already_held:bool,
)->None:
    runtime_rb="jason-runtime-rollback-pmv4c-"+plan["candidate_sha"][:12]
    mcp_rb="jason-mcp-pilot-rollback-pmv4c-"+plan["candidate_sha"][:12]
    def body()->None:
        need(_docker_exists(runtime_rb) and _docker_exists(mcp_rb),
             "C_POSTWRITE_ROLLBACK_CONTAINERS_MISSING")
        _stop(WORKER);_rm(WORKER)
        _stop("jason-runtime");_stop("jason-mcp-pilot")
        _rm("jason-runtime");_rm("jason-mcp-pilot")
        embedded=dict(plan["runtime_env_overrides"])
        embedded["JASON_TICKET_WORKER_HOSTING"]="embedded"
        rcmd,renv,rsecondary=_clone_command(
            plan,runtime_rb,"jason-runtime","runtime",
            embedded,(TICKET_TARGET,SHARED_TARGET))
        mcmd,menv,msecondary=_clone_command(
            plan,mcp_rb,"jason-mcp-pilot","mcp",
            plan["mcp_env_overrides"],(TICKET_TARGET,SHARED_TARGET))
        _run(mcmd,env=menv)
        _connect_and_start("jason-mcp-pilot",msecondary,env=menv)
        _run(rcmd,env=renv)
        _connect_and_start("jason-runtime",rsecondary,env=renv)
        _wait_container("jason-runtime",healthy=True,seconds=120)
        _wait_container("jason-mcp-pilot",healthy=False,seconds=120)
        meta=WATCHDOG.lstat()
        base=_watchdog_base_artifact(plan_path,plan)
        _atomic_policy(base,meta=meta)
        need(sha(WATCHDOG.read_bytes())==plan["watchdog_base_sha256"],
             "C_POSTWRITE_WATCHDOG_ROLLBACK_FAILED")
        _append(plan,approval,"rolled_back_to_embedded_new_canonical",{
            "stale_database_restore":False,
            "new_canonical_state_retained":True,
            "external_worker_present":False})
    if already_held:
        need(host._held is True,"C_NATIVE_HOST_RELEASE_LOCK_LOST")
        body()
    else:
        with host.host_release_transaction():
            host._assert_protected_release_state()
            body()


def postflight(plan_path:Path)->None:
    plan=_plan(plan_path)
    _stage_trust(plan_path,plan)
    manifest=_service_manifest(plan_path,plan)
    rows=_audit_rows(plan)
    need(rows and rows[-1]["event"]=="activated",
         "C_TRANSACTION_NOT_ACTIVATED")
    owner=_verify_owner(plan_path,plan,recovery=True)
    need(owner["approval_id"]==rows[0]["approval_id"],
         "C_POSTFLIGHT_OWNER_MISMATCH")
    approval=owner["approval_id"]
    host=host_guard.IndependentHostGuard()
    try:
        need(sha(WATCHDOG.read_bytes())==plan["watchdog_candidate_sha256"],
             "C_POSTFLIGHT_WATCHDOG_CHANGED")
        runtime=_wait_container("jason-runtime",healthy=True,seconds=30)
        mcp=_wait_container("jason-mcp-pilot",healthy=False,seconds=30)
        worker=_wait_container(WORKER,healthy=True,seconds=60)
        need(runtime.get("Image")==plan["runtime_image_digest"]
             and mcp.get("Image")==plan["mcp_image_digest"],
             "C_POSTFLIGHT_PROTECTED_IMAGE_CHANGED")
        service_contract.validate_effective_inspect(worker,manifest)
        for raw,expected in plan["db_identities"].items():
            source=Path(raw)
            target=(TICKET_TARGET/source.name
                    if source.name in sqlite_handoff.ALLOWED_TICKET
                    else SHARED_TARGET/source.name)
            need(target.exists() and target.lstat().st_ino==expected["inode"]
                 and target.lstat().st_dev==expected["device"],
                 "C_POSTFLIGHT_CANONICAL_INODE_CHANGED:"+source.name)
        # Read-only drift evaluation first: never open the breaker just to
        # discover a post-cutover inconsistency.
        drift=_run(
            ["/usr/bin/python3",
             "/opt/jason/current/tools/production_drift_guard.py",
             "--config",str(WATCHDOG)],
            check=False,capture=True,timeout=45)
        need(drift.returncode==0,"C_POSTFLIGHT_READONLY_DRIFT_FAILED")
        baseline=rows[0].get("details",{}).get("cutover_baseline_scanned_at")
        need(isinstance(baseline,str) and baseline,
             "C_POSTFLIGHT_CUTOVER_BASELINE_MISSING")
        scans=_wait_two_scans(baseline)
        # Only after read-only drift + real scans pass, persist normal watchdog
        # evidence. The breaker is already closed and is never auto-closed here.
        proc=_run(
            ["/usr/bin/python3",
             "/opt/jason/current/tools/production_drift_watchdog.py",
             "--config",str(WATCHDOG)],
            check=False,capture=True,timeout=45)
        need(proc.returncode==0,"C_POSTFLIGHT_DRIFT_WATCHDOG_FAILED")
        host._assert_protected_release_state()
        _append(plan,approval,"committed",{
            "scan_cycle_ids":[scans[0][0],scans[1][0]],
            "duplicate_items":[scans[0][4],scans[1][4]],
            "provider_items":[scans[0][3],scans[1][3]],
            "watchdog_pass":True})
        receipt={
            "schema_version":"1.0","status":"stage_c_accepted",
            "approval_id":approval,"candidate_sha":plan["candidate_sha"],
            "plan_sha256":sha(canon(plan)),
            "scan_cycle_ids":[scans[0][0],scans[1][0]],
            "committed_at":datetime.now(timezone.utc).isoformat(),
        }
        rp=_receipt_path(plan,approval)
        need(not rp.exists() and not rp.is_symlink(),
             "C_RECEIPT_ALREADY_EXISTS")
        fd=os.open(rp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as out:
            out.write(canon(receipt));out.flush();os.fsync(out.fileno())
        print("PMV4_C_TWO_REAL_SCANS=VERIFIED",flush=True)
        print("PMV4_C_INDEPENDENT_TICKET_CORE=VERIFIED_POSTFLIGHT",flush=True)
        print("PMV4_LATER_PHASES_ARE_NOT_AUTHORIZED",flush=True)
    except BaseException as original:
        try:
            _recover_to_embedded_new_canonical(
                plan_path,plan,approval,host,already_held=False)
        except BaseException:
            _append(plan,approval,"requires_review",{
                "reason":"C_POSTFLIGHT_FAIL_CLOSED_RECOVERY"})
        raise original

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight",action="store_true")
    mode.add_argument("--execute",action="store_true")
    mode.add_argument("--postflight",action="store_true")
    args=p.parse_args()
    try:
        if args.preflight:
            preflight(args.plan)
            print("PMV4_C_ROOT_PREFLIGHT=PASS")
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        elif args.execute:
            execute(args.plan)
        else:
            postflight(args.plan)
        return 0
    except BaseException as exc:
        code=str(exc)
        if len(code)>180: code="C_INTERNAL_DENIED"
        print("PMV4_C_ROOT=DENIED "+type(exc).__name__+":"+code,
              file=sys.stderr,flush=True)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
