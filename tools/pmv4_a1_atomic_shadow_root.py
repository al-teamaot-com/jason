#!/usr/bin/env python3
"""One authenticated Owner decision: Stage A1 exact root staging plus isolated shadow.

This module is source-only until independently reviewed, hash-pinned, copied
into a root-owned 0400 one-shot staging directory and run by an actual Owner
TTY. Preflight cannot install, sign, start containers or alter any controls.
The only permitted live mutation is one isolated shadow component namespace.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any,Mapping

TRUSTED=Path("/usr/local/lib/jason/pmv4-trusted")
# Production imports only immutable root-owned A0 code; local source-only tests
# deliberately exercise pure helpers without reading root-only trust files.
if os.geteuid()==0 and TRUSTED.is_dir():
    sys.path.insert(0,str(TRUSTED))
from tools import pmv4_shadow_release as shadow
from tools import pmv4_shadow_docker_adapter as docker_shadow
from tools import pmv4_host_release_guard as guard_lib
from tools import pmv4_shadow_ci as ci

CANDIDATE="8c2064193d74cc41b52369681febbc0a74fa96f7"
ROLLBACK="0"*40
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
IMAGE="sha256:779bf783c83cdefad82e34ac99335e2a2c017d8aa5588edb0ed2844a885aa9ed"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ACTION="pmv4-a1-one-owner-exact-shadow-bootstrap-and-activate-v1"
ROOT=shadow.PRODUCTION_ROOT
ARCHIVE=Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+CANDIDATE)
PLAN=ARCHIVE/"root-release-plan.json"
OWNER_PROOF=ARCHIVE/"root-oneowner-proof.json"
TARGET=ROOT/"releases"/CANDIDATE
CURRENT=ROOT/"current"
AUDIT=ROOT/"control"/"a1-exact-atomic-bootstrap.jsonl"
SHADOW_FREEZE=ROOT/"control"/"shadow-freeze.json"
GLOBAL_FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
GLOBAL_HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
ACTIVE_WATCHDOG_POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
ROOT_PIN=shadow.TRUST_PATH
APPROVED=ROOT/"control"/"approved-manifest.json"
REVIEWED=ROOT/"control"/"reviewed-scope.json"
TOKEN=ROOT/"control"/"gateway-token"
TRUSTED_SCRIPT=Path("/run/jason-pmv4-a1-oneowner-8c20/installer.py")
FILES=(
    "config/openclaw-specialists/manifest.json",
    "config/pmv4-shadow/docker-compose.yml",
    "tools/pmv4_shadow_ci.py",
    "tools/pmv4_shadow_docker_adapter.py",
    "tools/pmv4_shadow_host_runtime.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_owner_issuer.py",
    "tools/pmv4_shadow_release.py",
)
PROTECTED_CONTAINER_NAMES=("jason-runtime","jason-mcp-pilot")
IMAGE_IDS={
    "jason-runtime":"sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132",
    "jason-mcp-pilot":"sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477",
}


class A1RootDenied(RuntimeError):
    pass


def need(value:bool,code:str)->None:
    if not value: raise A1RootDenied(code)


def canon(obj:Mapping[str,Any])->bytes:
    return json.dumps(dict(obj),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def sha(raw:bytes)->str:
    return sha256(raw).hexdigest()


def read_json(path:Path, *, maxsize:int=50000)->dict[str,Any]:
    try:
        info=path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1
             and not path.is_symlink() and 0<info.st_size<=maxsize,
             "A1_SOURCE_FILE_UNTRUSTED")
        value=json.loads(path.read_bytes())
        need(isinstance(value,dict),"A1_SOURCE_DOCUMENT_NOT_OBJECT")
        return value
    except (OSError,ValueError,TypeError) as exc:
        raise A1RootDenied("A1_SOURCE_UNAVAILABLE") from exc


def root_script_trusted()->None:
    need(os.geteuid()==0,"A1_ROOT_EXECUTION_REQUIRED")
    script=Path(__file__).resolve(strict=True)
    info=script.lstat()
    need(script==TRUSTED_SCRIPT and not script.is_symlink()
         and stat.S_ISREG(info.st_mode) and info.st_nlink==1
         and info.st_uid==0 and info.st_gid==0
         and stat.S_IMODE(info.st_mode)==0o400,
         "A1_EXECUTOR_NOT_ROOT_INSTALLED")
    for item in (TRUSTED,ROOT_PIN,SHADOW_FREEZE):
        need(item.exists() and not item.is_symlink(),"A1_TRUSTED_ROOT_NOT_PROVISIONED")


def plan_and_source()->tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    plan=read_json(PLAN)
    need(set(plan)=={
        "schema_version","action","candidate_sha","rollback_sha",
        "root_executor_sha256","image_digest","bundle_sha256",
        "shadow_scope_sha256","shadow_manifest_sha256",
        "shadow_freeze_sha256","global_freeze_sha256",
        "global_hold_sha256","production_lkg_sha",
        "original_runtime_images","gateway_secret_generation",
        "source_files","owner_consents","standing_authority",
        "root_stage_before_owner_authorization","scope_sha256",
    },"A1_REVIEW_PLAN_SCHEMA_CHANGED")
    expected_scope=plan.pop("scope_sha256")
    digest=sha(canon(plan))
    plan["scope_sha256"]=expected_scope
    need(digest==expected_scope and plan["schema_version"]=="1.0"
         and plan["action"]==ACTION and plan["candidate_sha"]==CANDIDATE
         and plan["rollback_sha"]==ROLLBACK
         and plan["image_digest"]==IMAGE
         and plan["global_freeze_sha256"]==FREEZE_SHA
         and plan["global_hold_sha256"]==HOLD_SHA
         and plan["production_lkg_sha"]==LKG
         and plan["original_runtime_images"]==IMAGE_IDS
         and plan["gateway_secret_generation"]=="root_secure_random_48"
         and plan["owner_consents"]==1
         and plan["standing_authority"] is False
         and plan["root_stage_before_owner_authorization"] is False
         and set(plan["source_files"])==set(FILES),
         "A1_REVIEW_PLAN_NOT_EXACT")
    # The script is root-owned ONLY after the Owner-local staged copy.
    need(sha(TRUSTED_SCRIPT.read_bytes())==plan["root_executor_sha256"],
         "A1_ROOT_EXECUTOR_SHA_CHANGED")
    manifest=read_json(ARCHIVE/"release"/"release-manifest.json")
    scope=read_json(ARCHIVE/"reviewed-scope.json")
    shadow.manifest_check(manifest)
    need(manifest["candidate_sha"]==CANDIDATE
         and manifest["rollback_sha"]==ROLLBACK
         and manifest["image_digest"]==IMAGE
         and manifest["scope_sha256"]==plan["shadow_scope_sha256"]
         and manifest["bundle_sha256"]==plan["bundle_sha256"]
         and sha(canon(manifest))==plan["shadow_manifest_sha256"]
         and sha(canon(scope))==manifest["scope_sha256"]
         and set(scope["files"])==set(FILES)
         and scope["provider_writes"] is False
         and scope["protected_core"]==["ticket-processing"],
         "A1_SOURCE_SCOPE_NOT_EXACT")
    bundle=ARCHIVE/"release"/"bundle"
    need(shadow.bundle_digest(bundle)==plan["bundle_sha256"],
         "A1_SOURCE_BUNDLE_CHANGED")
    for rel in FILES:
        src=bundle/rel
        need(src.is_file() and not src.is_symlink()
             and sha(src.read_bytes())==plan["source_files"][rel],
             "A1_SOURCE_BLOB_CHANGED")
    evidence=read_json(ARCHIVE/"evidence.json")
    need(evidence.get("status")=="preproduction_candidate_not_authorized"
         and evidence.get("scope_sha256")==manifest["scope_sha256"]
         and evidence.get("manifest_sha256")==plan["shadow_manifest_sha256"]
         and evidence.get("bundle_sha256")==plan["bundle_sha256"]
         and evidence.get("image_digest")==IMAGE
         and evidence.get("production_mutations") is False
         and evidence.get("shadow_activation_performed") is False,
         "A1_SOURCE_PREP_EVIDENCE_CHANGED")
    return plan,manifest,scope


def runner_as_al(args,**kwargs):
    allowed=("/usr/bin/gh","gh")
    need(isinstance(args,(list,tuple)) and len(args)>1
         and args[0] in allowed and args[1]=="api",
         "A1_GITHUB_RUNNER_COMMAND_NOT_ALLOWLISTED")
    return subprocess.run(
        ["/usr/sbin/runuser","-u","al","--","/usr/bin/gh",*args[1:]],
        **kwargs,
    )


def active_shadow_allowlist(*, path:Path=ACTIVE_WATCHDOG_POLICY,
                            expected_uid:int=0)->str:
    """Fail BEFORE Owner consent when the live drift watchdog would reject A1.

    The active root-installed watchdog policy may differ from the repository
    copy. Never disable or change the watchdog to make this check pass.
    """
    need(path==ACTIVE_WATCHDOG_POLICY or expected_uid!=0,
         "A1_WATCHDOG_POLICY_PATH_NOT_PINNED")
    try:
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_uid==expected_uid and meta.st_nlink==1
             and not meta.st_mode&0o022 and 0<meta.st_size<=128000,
             "A1_ACTIVE_WATCHDOG_POLICY_NOT_TRUSTED")
        doc=json.loads(path.read_bytes())
    except (OSError,ValueError,TypeError) as exc:
        raise A1RootDenied("A1_ACTIVE_WATCHDOG_POLICY_UNAVAILABLE") from exc
    allowed=doc.get("allowed_running_containers") if isinstance(doc,dict) else None
    need(isinstance(doc,dict) and doc.get("schema_version")=="1.0"
         and isinstance(allowed,list)
         and all(isinstance(x,str) and x for x in allowed)
         and len(allowed)==len(set(allowed))
         and "jason-pmv4-shadow-gateway" in allowed,
         "A1_SHADOW_NOT_ALLOWED_BY_ACTIVE_PRODUCTION_WATCHDOG")
    return sha(path.read_bytes())


def protected_source_and_health()->guard_lib.IndependentHostGuard:
    active_shadow_allowlist()
    need(sha(GLOBAL_FREEZE.read_bytes())==FREEZE_SHA
         and sha(GLOBAL_HOLD.read_bytes())==HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "A1_GLOBAL_PRODUCTION_CONTROLS_CHANGED")
    need(ci.protected_main_ci_verified(CANDIDATE,runner=runner_as_al),
         "A1_PROTECTED_MAIN_CI_NOT_CURRENT")
    host=guard_lib.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True
         and host.host_mutation_quiescent() is True,
         "A1_PRODUCTION_BREAKER_OR_CORE_NOT_READY")
    for container,expected in IMAGE_IDS.items():
        proc=subprocess.run(["/usr/bin/docker","inspect",container],
                            capture_output=True,text=True,check=False,timeout=15)
        need(proc.returncode==0,"A1_EXISTING_RUNTIME_NOT_AVAILABLE")
        records=json.loads(proc.stdout)
        need(len(records)==1 and records[0].get("Image")==expected
             and records[0].get("State",{}).get("Running") is True,
             "A1_EXISTING_RUNTIME_IMAGE_CHANGED")
    image=subprocess.run(["/usr/bin/docker","image","inspect",IMAGE],
                         capture_output=True,text=True,check=False,timeout=15)
    need(image.returncode==0,"A1_SHADOW_IMAGE_NOT_LOCAL")
    item=json.loads(image.stdout)
    need(len(item)==1 and item[0]["Id"]==IMAGE
         and item[0]["Config"]["Labels"]["com.aot.jason.component"]=="pmv4-shadow"
         and item[0]["Config"]["Labels"]["com.aot.jason.lifecycle"]=="preproduction-only"
         and item[0]["Config"]["Labels"]["com.aot.jason.source_revision"]==CANDIDATE,
         "A1_SHADOW_IMAGE_NOT_REVIEWED")
    return host


def empty_baseline()->None:
    need(CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+ROLLBACK,
         "A1_SHADOW_ROLLBACK_NOT_INITIAL_ABSENCE")
    for p in (TARGET,APPROVED,REVIEWED,TOKEN,AUDIT):
        need(not p.exists() and not p.is_symlink(),"A1_AUDITED_TARGET_NOT_EMPTY")
    for p in (ROOT,ROOT/"control",ROOT/"releases",ROOT/"receipts"):
        info=p.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid==0
             and not p.is_symlink() and not (info.st_mode&0o022),
             "A1_NATIVE_ROOT_BOUNDARY_UNTRUSTED")
    receipts=list((ROOT/"receipts").iterdir())
    need(not receipts,"A1_REVIEW_EXISTING_RELEASE_RECEIPTS")
    adapter=docker_shadow.DockerShadowAdapter(
        root=ROOT,core_continuity_probe=lambda:True)
    need(adapter._owned_or_absent() is None,
         "A1_SHADOW_CONTAINER_ALREADY_PRESENT")


def preflight()->tuple[dict[str,Any],dict[str,Any],dict[str,Any],
                       guard_lib.IndependentHostGuard]:
    root_script_trusted()
    plan,manifest,scope=plan_and_source()
    empty_baseline()
    host=protected_source_and_health()
    return plan,manifest,scope,host


def verify_owner(plan:dict[str,Any],manifest:dict[str,Any],
                 *, recovery:bool=False)->tuple[dict[str,Any],dict[str,Any]]:
    record=read_json(OWNER_PROOF,maxsize=30000)
    need(set(record)=={"schema_version","action","source_sha","scope_sha256",
                       "manifest_sha256","approval_id","signed_root_release",
                       "signed_shadow_release"},
         "A1_OWNER_PROOF_SCHEMA_NOT_EXACT")
    need(record["schema_version"]=="1.0" and record["action"]==ACTION
         and record["source_sha"]==CANDIDATE
         and record["scope_sha256"]==plan["scope_sha256"]
         and record["manifest_sha256"]==sha(canon(plan))
         and re.fullmatch(r"owner-mcp-[a-f0-9]{32}",record["approval_id"]),
         "A1_OWNER_PROOF_PLAN_MISMATCH")
    public=shadow.read_pinned_root_owner_public_key(
        ROOT_PIN,require_root_owned=True)
    approved=record["signed_root_release"]
    child=record["signed_shadow_release"]
    moment=datetime.now(timezone.utc)
    if recovery:
        # Read-only postflight may verify an expired signed decision ONLY at
        # its recorded original use time, under an already committed native
        # audit chain. This branch is never called by execute/promote.
        rows=audit_rows()
        need(rows and rows[0]["event"]=="begin"
             and rows[-1]["event"]=="committed"
             and rows[0]["approval_id"]==record["approval_id"]
             and rows[-1]["approval_id"]==record["approval_id"],
             "A1_HISTORICAL_APPROVAL_NOT_COMMITTED")
        try:
            moment=datetime.fromisoformat(rows[0]["occurred_at"])
            finished=datetime.fromisoformat(rows[-1]["occurred_at"])
        except (TypeError,ValueError,KeyError) as exc:
            raise A1RootDenied("A1_HISTORICAL_AUDIT_TIMESTAMP_INVALID") from exc
        need(moment.tzinfo is not None and finished.tzinfo is not None
             and moment<=finished
             and (finished-moment)<=timedelta(minutes=15),
             "A1_HISTORICAL_COMMIT_TIME_NOT_BOUND")
    root_approval=shadow.verify_exact_owner_release(
        approved,public_key=public,at=moment,
        expected_candidate_sha=CANDIDATE,expected_rollback_sha=ROLLBACK,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=sha(canon(plan)),
        expected_freeze_sha256=plan["shadow_freeze_sha256"])
    shadow_approval=shadow.verify_exact_owner_release(
        child,public_key=public,at=moment,
        expected_candidate_sha=CANDIDATE,expected_rollback_sha=ROLLBACK,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=sha(canon(manifest)),
        expected_freeze_sha256=plan["shadow_freeze_sha256"])
    need(root_approval["approval_id"]==record["approval_id"]
         and shadow_approval["approval_id"]==record["approval_id"]
         and root_approval["owner_oid"]==shadow_approval["owner_oid"]
         and root_approval["owner_principal"]==shadow_approval["owner_principal"]
         and root_approval["issued_at"]==shadow_approval["issued_at"]
         and root_approval["expires_at"]==shadow_approval["expires_at"],
         "A1_ONE_OWNER_PARENT_CHILD_PROOF_MISMATCH")
    return root_approval,child


def source_git_attestation(plan:dict[str,Any])->None:
    repo="/home/al/.local/lib/jason/engineering-source-repo"
    for rel in FILES:
        query=subprocess.run(
            ["/usr/sbin/runuser","-u","al","--","/usr/bin/git",
             "-C",repo,"show",CANDIDATE+":"+rel],
            capture_output=True,check=False,timeout=20,
        )
        need(query.returncode==0 and 0<len(query.stdout)<=1_000_000
             and sha(query.stdout)==plan["source_files"][rel],
             "A1_PROTECTED_GIT_BLOB_CHANGED")


def audit_rows()->list[dict[str,Any]]:
    if not AUDIT.exists(): return []
    need(AUDIT.is_file() and not AUDIT.is_symlink(),
         "A1_ROOT_AUDIT_NOT_REGULAR")
    info=AUDIT.lstat()
    need(info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600,
         "A1_ROOT_AUDIT_PERMISSIONS_CHANGED")
    prior="0"*64
    rows=[]
    for line in AUDIT.read_bytes().splitlines():
        row=json.loads(line)
        next_hash=row.pop("hash")
        need(row["index"]==len(rows)
             and row["previous_sha256"]==prior
             and sha(canon(row))==next_hash,
             "A1_ROOT_AUDIT_CHAIN_CHANGED")
        rows.append({**row,"hash":next_hash})
        prior=next_hash
    return rows


def append(event:str,approval:str,details:Mapping[str,Any])->None:
    rows=audit_rows()
    entry={
        "schema_version":"1.0","index":len(rows),
        "previous_sha256":rows[-1]["hash"] if rows else "0"*64,
        "event":event,"approval_id":approval,
        "source_sha":CANDIDATE,"details":dict(details),
        "occurred_at":datetime.now(timezone.utc).isoformat(),
    }
    entry["hash"]=sha(canon(entry))
    flags=os.O_WRONLY|os.O_APPEND|os.O_CREAT|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(AUDIT,flags,0o600)
    try:
        with os.fdopen(fd,"ab") as output:
            output.write(canon(entry)+b"\n")
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        raise


def owned_stage_directory(path:Path)->None:
    need(not path.exists() and not path.is_symlink(),
         "A1_ROOT_STAGE_DIRECTORY_ALREADY_PRESENT")
    path.mkdir(mode=0o700)
    meta=path.lstat()
    need(meta.st_uid==os.geteuid() and stat.S_IMODE(meta.st_mode)==0o700,
         "A1_ROOT_STAGE_DIRECTORY_NOT_TRUSTED")


def write_exclusive(path:Path,raw:bytes,*,mode:int=0o400)->None:
    need(not path.exists() and not path.is_symlink()
         and len(raw)<1_000_000 and mode==0o400,
         "A1_ROOT_STAGED_FILE_NOT_EXCLUSIVE")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags,mode)
    with os.fdopen(fd,"wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    meta=path.lstat()
    need(meta.st_uid==os.geteuid() and meta.st_gid==os.getegid() and meta.st_nlink==1
         and stat.S_IMODE(meta.st_mode)==mode
         and sha(path.read_bytes())==sha(raw),
         "A1_ROOT_STAGED_FILE_VERIFY_FAILED")


def stage_exact(plan:dict[str,Any],manifest:dict[str,Any],
                scope:dict[str,Any],approval_id:str)->None:
    """Create-only exclusively inside isolated PMv4 shadow root."""
    def record_file(path:Path,raw:bytes)->None:
        append("intent-create-file",approval_id,
               {"path":str(path),"sha256":sha(raw),"mode":"0400"})
        write_exclusive(path,raw)
        append("created-file",approval_id,
               {"path":str(path),"sha256":sha(raw),
                "inode":path.lstat().st_ino,"mode":"0400"})
    append("intent-create-root",approval_id,
           {"path":str(TARGET),"mode":"0500"})
    owned_stage_directory(TARGET)
    owned_stage_directory(TARGET/"bundle")
    created=[TARGET,TARGET/"bundle"]
    for rel in FILES:
        parent=TARGET/"bundle"/rel
        for ancestor in reversed(parent.parents):
            if ancestor==TARGET/"bundle": break
        cursor=TARGET/"bundle"
        for part in Path(rel).parts[:-1]:
            cursor=cursor/part
            if cursor not in created:
                owned_stage_directory(cursor)
                created.append(cursor)
        raw=(ARCHIVE/"release"/"bundle"/rel).read_bytes()
        need(sha(raw)==plan["source_files"][rel],
             "A1_STAGED_GIT_SOURCE_CHANGED")
        record_file(TARGET/"bundle"/rel,raw)
    record_file(TARGET/"release-manifest.json",canon(manifest))
    record_file(REVIEWED,canon(scope))
    record_file(APPROVED,canon(manifest))
    # The generated token itself is NEVER written to an audit or model output.
    import secrets
    secret=secrets.token_urlsafe(48).encode()
    need(32<=len(secret)<=128,"A1_ROOT_SECRET_GENERATION_FAILED")
    record_file(TOKEN,secret)
    append("root-stage-verified",approval_id,
           {"source_files":len(FILES),"bundle_sha256":plan["bundle_sha256"],
            "shadow_manifest_sha256":plan["shadow_manifest_sha256"],
            "source_tree":str(TARGET)})


def cleanup_exact_unpromoted(approval_id:str)->None:
    """Rollback ONLY exact recorded root-created files, refuse foreign inodes."""
    rows=audit_rows()
    need(rows and rows[0]["approval_id"]==approval_id,
         "A1_ROLLBACK_NOT_ORIGINAL_OWNER")
    intents={}
    created={}
    for row in rows:
        if row["event"]=="intent-create-file":
            d=row["details"]
            intents[d["path"]]=d
        if row["event"]=="created-file":
            d=row["details"]
            created[d["path"]]=d
    allowed=(TARGET,REVIEWED,APPROVED,TOKEN)
    for name,d in list(intents.items())[::-1]:
        path=Path(name)
        need(path==REVIEWED or path==APPROVED or path==TOKEN
             or TARGET in path.parents,
             "A1_ROLLBACK_FILE_OUTSIDE_FIXED_SCOPE")
        if not path.exists() and not path.is_symlink():
            continue
        need(path.is_file() and not path.is_symlink()
             and path.lstat().st_uid==os.geteuid()
             and stat.S_IMODE(path.lstat().st_mode)==0o400
             and sha(path.read_bytes())==d["sha256"]
             and (name not in created
                  or path.lstat().st_ino==created[name]["inode"]),
             "A1_ROLLBACK_FOREIGN_OR_CHANGED_FILE")
        path.unlink()
    # Only remove this exact candidate tree and no pre-existing parent.
    if TARGET.is_dir():
        for p in sorted(TARGET.rglob("*"),key=lambda x:len(x.parts),reverse=True):
            need(not p.is_symlink() and p.is_dir() and p.lstat().st_uid==os.geteuid()
                 and stat.S_IMODE(p.lstat().st_mode)==0o700,
                 "A1_ROLLBACK_FOREIGN_OR_CHANGED_DIRECTORY")
            p.rmdir()
        TARGET.rmdir()
    need(not TARGET.exists() and not REVIEWED.exists()
         and not APPROVED.exists() and not TOKEN.exists(),
         "A1_ROLLBACK_NOT_EXACT_ORIGINAL_ABSENCE")


def controller(host:guard_lib.IndependentHostGuard):
    adapter=docker_shadow.DockerShadowAdapter(
        root=ROOT,core_continuity_probe=host.preexisting_core_health)
    return adapter,shadow.ShadowController(
        ROOT,public_key_path=ROOT_PIN,
        protected_ci_check=lambda source:ci.protected_main_ci_verified(
            source,runner=runner_as_al),
        activate_shadow=adapter.activate_shadow,
        verify_shadow_and_core=lambda path:(
            adapter.verify_shadow_and_core(path) is True
            and host.protected_release_status().get("ready") is True
            and host.preexisting_core_health() is True),
        restore_shadow=adapter.restore_shadow,
        host_mutation_quiescent=host.host_mutation_quiescent,
        preexisting_core_health=host.preexisting_core_health,
        host_release_transaction=host.host_release_transaction,
    )


def execute()->None:
    plan,manifest,scope,host=preflight()
    owner,child=verify_owner(plan,manifest)
    approval=owner["approval_id"]
    source_git_attestation(plan)
    watchdog_before=active_shadow_allowlist()
    with host.host_release_transaction():
        need(active_shadow_allowlist()==watchdog_before,
             "A1_ACTIVE_WATCHDOG_POLICY_CHANGED_BEFORE_RELEASE")
        # Recheck under both original and independent release locks.
        host._assert_protected_release_state()
        need(host.preexisting_core_health() is True,
             "A1_CORE_NOT_HEALTHY_UNDER_NATIVE_LOCK")
        need(CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+ROLLBACK,
             "A1_ORIGINAL_ZERO_BASELINE_MOVED")
        need(not AUDIT.exists(),"A1_ROOT_RELEASE_ALREADY_ATTEMPTED")
        append("begin",approval,
               {"parent_scope_sha256":plan["scope_sha256"],
                "shadow_manifest_sha256":plan["shadow_manifest_sha256"],
                "active_watchdog_policy_sha256":watchdog_before})
        promoted=False
        try:
            stage_exact(plan,manifest,scope,approval)
            adapter,worker=controller(host)
            result=worker._promote_locked(manifest,child)
            need(result.get("status")=="shadow_accepted"
                 and result.get("candidate_sha")==CANDIDATE
                 and CURRENT.is_symlink()
                 and os.readlink(CURRENT)=="releases/"+CANDIDATE,
                 "A1_PROMOTION_OR_POSTFLIGHT_FAILED")
            promoted=True
            need(host.preexisting_core_health() is True
                 and host.protected_release_status().get("ready") is True
                 and active_shadow_allowlist()==watchdog_before
                 and sha(GLOBAL_FREEZE.read_bytes())==FREEZE_SHA
                 and sha(GLOBAL_HOLD.read_bytes())==HOLD_SHA
                 and Path("/opt/jason/current").resolve(strict=True).name==LKG,
                 "A1_FINAL_PRODUCTION_CONTINUITY_FAILED")
            append("committed",approval,
                   {"shadow_accepted":True,
                    "ticket_runtime_mcp_changed":False,
                    "production_freeze_hold_changed":False})
            print("A1_ONE_OWNER_ISOLATED_SHADOW=VERIFIED",flush=True)
            print("ROOT_BUNDLE_AND_PRODUCTION_CONTROLS=VERIFIED",flush=True)
            print("NEW_OWNER_APPROVALS_TOTAL=1",flush=True)
        except BaseException:
            # A native shadow rollback restores the initial empty pointer.
            # Any foreign object/raced Docker state fails closed for review.
            try:
                adapter,worker=controller(host)
                if promoted and CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+CANDIDATE:
                    worker._switch(CURRENT,ROLLBACK)
                    adapter.restore_shadow(ROOT/"releases"/ROLLBACK)
                need(CURRENT.is_symlink()
                     and os.readlink(CURRENT)=="releases/"+ROLLBACK
                     and adapter._owned_or_absent() is None,
                     "A1_ROLLBACK_SHADOW_STILL_ACTIVE")
                cleanup_exact_unpromoted(approval)
                append("rolled_back",approval,{"root_exact_absence":True})
            except BaseException:
                append("requires_review",approval,
                       {"reason":"A1_FAIL_CLOSED_ROOT_RECOVERY"})
            raise


def postflight()->None:
    root_script_trusted()
    plan,manifest,scope=plan_and_source()
    rows=audit_rows()
    need(rows and rows[-1]["event"]=="committed",
         "A1_ROOT_TRANSACTION_NOT_COMMITTED")
    need(rows[0].get("details",{}).get("active_watchdog_policy_sha256")
         ==active_shadow_allowlist(),
         "A1_ACTIVE_WATCHDOG_POLICY_CHANGED_AFTER_RELEASE")
    owner,child=verify_owner(plan,manifest,recovery=True)
    need(owner["approval_id"]==rows[0]["approval_id"],
         "A1_ROOT_COMMIT_OWNER_PROOF_MISMATCH")
    host=protected_source_and_health()
    adapter,worker=controller(host)
    with host.host_release_transaction():
        host._assert_protected_release_state()
        need(CURRENT.is_symlink()
             and os.readlink(CURRENT)=="releases/"+CANDIDATE
             and shadow.bundle_digest(TARGET/"bundle")==plan["bundle_sha256"]
             and adapter.verify_shadow_and_core(TARGET) is True
             and host.preexisting_core_health() is True,
             "A1_FINAL_ROOT_INDEPENDENT_READBACK_FAILED")
    print("A1_ONE_OWNER_ATOMIC_FULL_POSTFLIGHT=PASS")


def main()->int:
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight",action="store_true")
    mode.add_argument("--execute",action="store_true")
    mode.add_argument("--postflight",action="store_true")
    args=p.parse_args()
    try:
        if args.preflight:
            plan,manifest,scope,host=preflight()
            source_git_attestation(plan)
            print("A1_PRIVILEGED_EMPTY_BASELINE_AND_ROOT_PREFLIGHT=PASS")
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        elif args.execute: execute()
        else: postflight()
        return 0
    except Exception as exc:
        code=str(exc)
        if len(code)>140 or "/" in code:code="A1_INTERNAL_DENIED"
        print("A1_ROOT=DENIED "+type(exc).__name__+":"+code,
              file=sys.stderr,flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
