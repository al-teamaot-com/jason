#!/usr/bin/env python3
"""Exact, one-use RMM-authorized Root installer for the audit-only executor.

This installs ONLY the temporary signed-Owner audit request watcher. The
caller (AOT RMM component) must independently authenticate an exact per-run
technician/Owner consent. A CLI flag alone is NOT an Owner signature and
cannot authorize archival cutover. No MCP restart, database write, general
release promotion, freeze removal, or provider action occurs here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

SOURCE_PREFIX=Path("/srv/jason/archive/engineering-worktrees")
ROOT_CODE=Path("/usr/local/lib/jason/audit-journal-owner-executor/worker.py")
ROOT_POLICY=Path("/etc/jason-owner-release/audit-journal-owner-executor-v1.json")
NATIVE_UNIT_DIR=Path("/etc/systemd/system")
TRUST_DIR=Path("/var/lib/jason-owner-release")
PUBLIC=Path("/var/lib/jason/authority/audit-journal-release")
CONTROL_READBACK=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
DRIFT_READBACK=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
FAST_READBACK=Path("/var/lib/jason/openclaw/operational-health.json")
FULL_READBACK=Path("/var/lib/jason/openclaw/operational-full-health.json")
FREEZE_PATH=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
CANONICAL_DB=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE_DRIVE=Path("/srv/jason/archive")
ROLLBACK_SHA="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
MCP_BASE="sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
ACTION="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
SHA=re.compile(r"[0-9a-f]{40}\Z")
SOURCE=(
 "tools/audit_journal_owner_executor_bootstrap.py",
 "tools/audit_journal_owner_native_worker.py",
 "tools/audit_journal_install.py",
 "tools/audit_journal_signed_owner_bridge.py",
 "implementation/mcp_service/src/jason_mcp/audit_journal_adoption_approval.py",
 "infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.service",
 "infrastructure/jason-audit-journal-owner-executor/jason-audit-journal-owner-executor.path",
 "infrastructure/jason-audit-journal-owner-executor/mcp_overlay.py",
 "infrastructure/jason-audit-journal-owner-executor/mcp-overlay.Dockerfile",
)
UNIT_SERVICE="jason-audit-journal-owner-executor.service"
UNIT_PATH="jason-audit-journal-owner-executor.path"
BASE_ENV=(
 "GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
 "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
 "GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
 "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
 "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null",
)

class AuditBootstrapDenied(PermissionError):pass
def require(ok,code):
    if not ok:raise AuditBootstrapDenied("AUDIT_EXACT_ROOT_BOOTSTRAP_"+code)
def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True).encode()
def digest(raw):return sha256(raw).hexdigest()
def command(argv,timeout=45):
    result=subprocess.run(argv,cwd="/",capture_output=True,text=True,
                          timeout=timeout,check=False)
    require(result.returncode==0,"COMMAND_FAILED_"+Path(argv[0]).name)
    return result.stdout.strip()
def al_git(source,*args):
    user=["/usr/sbin/runuser","-u","al","--"] if os.geteuid()==0 else []
    return command([*user,"/usr/bin/env",*BASE_ENV,
                    "/usr/bin/git","-C",str(source),*args],timeout=90)
def source_verified(source,candidate):
    require(isinstance(candidate,str) and SHA.fullmatch(candidate) is not None,
            "EXACT_SHA_REQUIRED")
    require(source.is_absolute() and not source.is_symlink()
            and source.resolve()==source
            and source.parent==SOURCE_PREFIX
            and source.name.startswith("audit-owner-main-"),
            "WORKTREE_SOURCE_PATH_NOT_EXACT")
    info=source.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==1000
            and not info.st_mode&0o022,"WORKTREE_SOURCE_UNSAFE")
    require(al_git(source,"rev-parse","HEAD")==candidate
            and not al_git(source,"status","--porcelain","--untracked-files=all")
            and al_git(source,"ls-remote","origin","refs/heads/main")
                ==candidate+"\trefs/heads/main",
            "PROTECTED_MAIN_NOT_EXACT_OR_CLEAN")
    out={}
    for name in SOURCE:
        p=source/name
        st=p.lstat()
        require(not p.is_symlink() and stat.S_ISREG(st.st_mode)
                and st.st_uid==1000 and not st.st_mode&0o022
                and st.st_nlink==1,"SOURCE_CUSTODY_"+p.name)
        body=p.read_bytes()
        reviewed=subprocess.check_output([
            *([ "/usr/sbin/runuser","-u","al","--"] if os.geteuid()==0 else []),
            "/usr/bin/env",*BASE_ENV,"/usr/bin/git","-C",str(source),
            "show",candidate+":"+name],timeout=20)
        require(body==reviewed,"PROTECTED_MAIN_SOURCE_DRIFT_"+p.name)
        out[name]=body
    # This script is run from a Root-private content-addressed temporary file.
    # It cannot safely execute directly from the mutable al-owned checkout.
    if os.geteuid()==0:
        current=Path(__file__).read_bytes()
        require(digest(current)==digest(out[SOURCE[0]])
                and Path(__file__).resolve().is_relative_to(Path("/run")),
                "ROOT_PRIVATE_SOURCE_HASH_REQUIRED")
    return out

def live_readonly_admission(source,candidate,payload):
    control=json.loads(CONTROL_READBACK.read_bytes())
    drift=json.loads(DRIFT_READBACK.read_bytes())
    health=json.loads(FAST_READBACK.read_bytes())
    full=json.loads(FULL_READBACK.read_bytes())
    require(control.get("circuit_breaker",{}).get("state")=="closed"
            and control.get("circuit_breaker",{}).get("revalidated_revision")==ROLLBACK_SHA,
            "PROTECTED_BREAKER_NOT_VERIFIED")
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(
            drift["observed_at"].replace("Z","+00:00"))).total_seconds()
    except (KeyError,ValueError,TypeError) as exc:
        raise AuditBootstrapDenied("AUDIT_EXACT_ROOT_BOOTSTRAP_DRIFT_TIME_INVALID") from exc
    require(drift.get("status")=="pass" and drift.get("problems")==[]
            and 0<=age<=180,
            "PRODUCTION_DRIFT_NOT_FRESH_PASS")
    require(health.get("status")=="pass" and health.get("failures")==[]
            and full.get("status")=="pass" and full.get("failures")==[],
            "GENUINE_HEALTH_NOT_PASS")
    freeze=FREEZE_PATH
    fm=freeze.lstat()
    require(not freeze.is_symlink() and stat.S_ISREG(fm.st_mode)
            and fm.st_uid==1000 and stat.S_IMODE(fm.st_mode)==0o600,
            "PRODUCTION_FREEZE_CUSTODY")
    fr=json.loads(freeze.read_bytes())
    require(fr.get("status")=="active"
            and fr.get("scope")=="manual-and-automatic-production-promotions"
            and fr.get("release_exception")=="none approved",
            "GLOBAL_FREEZE_MUST_REMAIN_UNCHANGED")
    journal=CANONICAL_DB
    st=journal.stat()
    archive=ARCHIVE_DRIVE
    require(archive.is_mount() and st.st_dev!=archive.stat().st_dev,
            "ARCHIVE_DRIVE_NOT_SEPARATE")
    require(shutil.disk_usage(archive).free>3*st.st_size+4563402752
            and shutil.disk_usage(journal.parent).free>4563402752,
            "DATASET_SAFETY_RESERVE")
    mcp=json.loads(command(["/usr/bin/docker","inspect","jason-mcp-pilot"]))
    require(isinstance(mcp,list) and len(mcp)==1 and
            mcp[0].get("Image")==MCP_BASE and mcp[0]["State"]["Running"],
            "MCP_LKG_IMAGE_NOT_RUNNING")
    target="jason-audit-owner-overlay:source-only-"+candidate[:8]
    image=json.loads(command(["/usr/bin/docker","image","inspect",target]))
    require(len(image)==1 and image[0]["Id"].startswith("sha256:")
            and image[0]["Config"]["Labels"].get(
                "com.teamaot.jason.audit_overlay_reviewed_main_sha")==candidate
            and image[0]["Config"]["Labels"].get(
                "com.teamaot.jason.audit_overlay_base_image_sha256")==MCP_BASE.split(":",1)[1]
            and image[0]["Config"]["Labels"].get(
                "com.teamaot.jason.audit_overlay_purpose")=="one-use-owner-archive-adoption"
            and image[0]["Config"].get("User")=="1000:1000",
            "ADDITIVE_MCP_IMAGE_SOURCE_NOT_PINNED")
    # Exact base-layer ancestry, *only three* additive layers, identical
    # original image environment/entrypoint and runtime UID. A fake local
    # image with plausible labels alone is never a trusted Owner signer.
    original=json.loads(command(["/usr/bin/docker","image","inspect",MCP_BASE]))
    require(len(original)==1 and original[0]["Id"]==MCP_BASE,
            "IMMUTABLE_PRODUCTION_MCP_BASE_UNAVAILABLE")
    base_layers=(original[0].get("RootFS") or {}).get("Layers",[])
    overlay_layers=(image[0].get("RootFS") or {}).get("Layers",[])
    original_config=original[0]["Config"]
    addon_config=image[0]["Config"]
    require(isinstance(base_layers,list) and len(base_layers)>0
            and isinstance(overlay_layers,list)
            and overlay_layers[:len(base_layers)]==base_layers
            and len(overlay_layers)==len(base_layers)+3
            and addon_config.get("Env")==original_config.get("Env")
            and addon_config.get("Entrypoint")==original_config.get("Entrypoint")
            and addon_config.get("WorkingDir")==original_config.get("WorkingDir")
            and original_config.get("Cmd")==["jason-mcp"]
            and addon_config.get("Cmd")==["python","/opt/jason-src/mcp_overlay.py"],
            "MCP_ADDITIVE_IMAGE_EXACT_BASE_ANCESTRY_DENIED")
    # Validate both added source files in a no-network, no-host-mount,
    # no-privilege isolated image before any Root installation.
    probe=("import hashlib,json;from pathlib import Path;"
           "paths={'mcp_overlay':'/opt/jason-src/mcp_overlay.py',"
           "'owner_approval':'/opt/jason-src/audit_journal_adoption_approval_overlay.py'};"
           "print(json.dumps({k:hashlib.sha256(Path(v).read_bytes()).hexdigest()"
           " for k,v in paths.items()},sort_keys=True))")
    observed=json.loads(command([
        "/usr/bin/docker","run","--rm","--network=none","--read-only",
        "--cap-drop=ALL","--security-opt=no-new-privileges",
        "--entrypoint","python",image[0]["Id"],"-B","-c",probe],timeout=90))
    require(observed=={
        "mcp_overlay":digest(payload[
            "infrastructure/jason-audit-journal-owner-executor/mcp_overlay.py"]),
        "owner_approval":digest(payload[
            "implementation/mcp_service/src/jason_mcp/audit_journal_adoption_approval.py"]),
    },"EXACT_MCP_ADDITIVE_CODE_DIGEST_MISMATCH")
    require(not ROOT_CODE.exists() and not ROOT_CODE.is_symlink()
            and not ROOT_POLICY.exists() and not ROOT_POLICY.is_symlink()
            and not (NATIVE_UNIT_DIR/UNIT_SERVICE).exists()
            and not (NATIVE_UNIT_DIR/UNIT_PATH).exists()
            and not PUBLIC.exists()
            and not (TRUST_DIR/"audit-journal-signed-stage").exists(),
            "ROOT_BOOTSTRAP_NOT_FRESH")
    return {"schema_version":"1.0","reviewed_main_sha":candidate,
            "original_mcp_image_id":MCP_BASE,
            "mcp_overlay_image_id":image[0]["Id"],
            "source_digest_sha256":{k:digest(v) for k,v in payload.items()},
            "original_freeze_sha256":digest(freeze.read_bytes()),
            "canonical_journal_inode":st.st_ino,
            "canonical_journal_bytes":st.st_size,
            "separate_archive_volume":True,"breaker":"closed",
            "drift":"pass","full_health":"pass","fast_health":"pass",
            "archive_only":True,"freeze_left_active":True}

def exclusive(path,raw,uid,mode):
    require(not os.path.lexists(path),"TARGET_ALREADY_EXISTS")
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb",closefd=False) as stream:
            os.fchown(fd,uid,uid)
            os.fchmod(fd,mode)
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:os.close(fd)
    return path

def root_install(source,candidate,payload,facts):
    require(os.geteuid()==0,"EXACT_HOST_ROOT_REQUIRED")
    for parent,uid in ((ROOT_CODE.parent.parent,0),
                       (ROOT_POLICY.parent,0),(NATIVE_UNIT_DIR,0),
                       (TRUST_DIR,0),(PUBLIC.parent,1000)):
        m=parent.lstat()
        require(not parent.is_symlink() and stat.S_ISDIR(m.st_mode)
                and m.st_uid==uid and not m.st_mode&0o022,
                "ROOT_INSTALL_PARENT_UNSAFE")
    require(not ROOT_CODE.parent.exists(),"ROOT_EXECUTOR_PARENT_ALREADY_PRESENT")
    created=[]
    path_enabled=False
    try:
        ROOT_CODE.parent.mkdir(mode=0o755)
        created.append(ROOT_CODE.parent)
        os.chown(ROOT_CODE.parent,0,0)
        ROOT_CODE.parent.chmod(0o755)
        created.append(exclusive(ROOT_CODE,payload["tools/audit_journal_owner_native_worker.py"],0,0o444))
        for folder,uid in ((PUBLIC,1000),(PUBLIC/"requests",1000),
                           (PUBLIC/"processed",1000),(PUBLIC/"results",1000),
                           (PUBLIC/"offers",1000),(PUBLIC/"owner-approvals",1000),
                           (TRUST_DIR/"audit-journal-signed-stage",0)):
            folder.mkdir(mode=0o700)
            created.append(folder)
            os.chown(folder,uid,uid)
            folder.chmod(0o700)
        policy={
            "schema_version":"1.0","action":ACTION,
            "candidate_sha":candidate,"rollback_sha":ROLLBACK_SHA,
            "worker_sha256":digest(payload["tools/audit_journal_owner_native_worker.py"]),
            "installer_sha256":digest(payload["tools/audit_journal_install.py"]),
            "mcp_base_image_id":MCP_BASE,
            "mcp_overlay_image_id":facts["mcp_overlay_image_id"],
            "source_worktree":str(source),"standing_authority":False,
            "one_use_executor":True,
            "permitted_actions":["audit_archive_adopt","audit_archive_stage"],
            "expires_at":(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat(),
            "licensed_owner_oid":OID,"global_freeze_unchanged":True,
        }
        created.append(exclusive(ROOT_POLICY,canonical(policy)+b"\n",0,0o600))
        for name in (UNIT_SERVICE,UNIT_PATH):
            src="infrastructure/jason-audit-journal-owner-executor/"+name
            created.append(exclusive(NATIVE_UNIT_DIR/name,payload[src],0,0o644))
        command(["/usr/bin/systemd-analyze","verify",
                 str(NATIVE_UNIT_DIR/UNIT_SERVICE),str(NATIVE_UNIT_DIR/UNIT_PATH)],timeout=25)
        command(["/usr/bin/systemctl","daemon-reload"],timeout=30)
        path_enabled=True
        command(["/usr/bin/systemctl","enable","--now",UNIT_PATH],timeout=30)
        active=command(["/usr/bin/systemctl","is-active",UNIT_PATH])
        require(active=="active","EXACT_WATCHER_NOT_ACTIVE")
        return {"status":"root_exact_audit_executor_installed",
                "reviewed_main_sha":candidate,"worker_sha256":policy["worker_sha256"],
                "installer_sha256":policy["installer_sha256"],
                "expires_at":policy["expires_at"],
                "root_path_enabled":True,
                "owner_signature_not_yet_issued":True,
                "mcp_not_restarted":True,"archive_not_deployed":True,
                "freeze_unmodified":True,"production_database_unchanged":True}
    except Exception:
        if path_enabled:
            subprocess.run(["/usr/bin/systemctl","disable","--now",UNIT_PATH],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        # Remove only files and empty directories created by this invocation.
        for p in reversed(created):
            try:
                if p.is_dir():p.rmdir()
                else:p.unlink()
            except OSError:pass
        subprocess.run(["/usr/bin/systemctl","daemon-reload"],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        raise

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate-sha",required=True)
    parser.add_argument("--source-worktree",required=True)
    parser.add_argument("--preflight-only",action="store_true")
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--approval-marker",default="")
    args=parser.parse_args()
    require(args.preflight_only != args.apply,"EXACT_ONE_OPERATION_REQUIRED")
    source=Path(args.source_worktree)
    payload=source_verified(source,args.candidate_sha)
    facts=live_readonly_admission(source,args.candidate_sha,payload)
    print("AUDIT_RMM_ROOT_BOOTSTRAP_PREFLIGHT=PASS",flush=True)
    print("REVIEWED_MAIN_SHA="+args.candidate_sha,flush=True)
    print("CANDIDATE_SOURCE_SHA256="+digest(payload[SOURCE[0]]),flush=True)
    print("LIVE_MCP_IMAGE_SHA="+MCP_BASE,flush=True)
    print("GLOBAL_PRODUCTION_FREEZE_UNCHANGED=true",flush=True)
    if args.preflight_only:
        print("NO_OWNER_AUTH_GRANTED;NO_PRODUCTION_MUTATION=true",flush=True)
        return
    require(os.geteuid()==0 and sys.flags.isolated==1
            and args.approval_marker==
                 "INSTALL-EXACT-AUDIT-ROOT-EXECUTOR-"+args.candidate_sha[:16].upper(),
            "RMM_GOVERNED_EXACT_ACTION_APPROVAL_REQUIRED")
    # The RMM component's authenticated per-run acceptance is the actual
    # external authorization. The marker is an exact-scope interlock, NOT
    # an untrusted model assertion, and never grants Owner archive cutover.
    row=root_install(source,args.candidate_sha,payload,facts)
    print("AUDIT_RMM_EXACT_BOOTSTRAP="+json.dumps(row,sort_keys=True),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("AUDIT_RMM_ROOT_BOOTSTRAP=DENIED "+
              (str(exc).split(":")[0][:160] if isinstance(exc,AuditBootstrapDenied)
               else type(exc).__name__),file=sys.stderr)
        raise SystemExit(2)
