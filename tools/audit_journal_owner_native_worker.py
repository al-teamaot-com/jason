#!/usr/bin/env python3
"""One-time exact audit-only stage/adopt Root request worker.

The separately governed host bootstrap installs and pins this file. A request
is NEVER authority. Only an immutable Root stage, independently authenticated
one-use ChatGPT Owner signature, and the existing full original installer
may begin a migration. No arbitrary Root command, no generic release action.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import types

INSTALLED=Path("/usr/local/lib/jason/audit-journal-owner-executor/worker.py")
WORKTREE_PREFIX="/srv/jason/archive/engineering-worktrees/audit-owner-main-"
TRUST=Path("/etc/jason-owner-release/audit-journal-owner-executor-v1.json")
AUTH=Path("/var/lib/jason/authority/audit-journal-release")
REQUESTS=AUTH/"requests"
PROCESSED=AUTH/"processed"
RESULTS=AUTH/"results"
RECORD=Path("/var/lib/jason-owner-release/audit-journal-install")
SHA=re.compile(r"[a-f0-9]{40}\Z")
DIGEST=re.compile(r"[a-f0-9]{64}\Z")
IDENTITY=re.compile(r"[a-f0-9]{32}\Z")
ALLOWED=frozenset({"audit_archive_stage","audit_archive_adopt"})
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
SAFE=("GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
      "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
      "GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
      "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
      "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null")

class NativeArchiveDenied(PermissionError):pass
def need(ok,why):
    if not ok:raise NativeArchiveDenied("AUDIT_ROOT_NATIVE_"+why)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(raw):return sha256(raw).hexdigest()
def safe_file(path,uid,mode,maximum=30000):
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid==uid and stat.S_IMODE(info.st_mode)==mode
         and info.st_nlink==1 and 0<info.st_size<=maximum,
         "TRUSTED_FILE_CUSTODY")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        observed=os.fstat(fd)
        need((observed.st_dev,observed.st_ino,observed.st_size)==
             (info.st_dev,info.st_ino,info.st_size),
             "FILE_CHANGED_DURING_READ")
        raw=os.read(fd,maximum+1)
        need(len(raw)==info.st_size,"FILE_READ_MISMATCH")
        return raw
    finally:os.close(fd)
def root_stage_trust():
    need(os.geteuid()==0 and sys.flags.isolated==1 and
         Path(__file__).resolve()==INSTALLED,
         "EXACT_INSTALLED_ISOLATED_ROOT_WORKER_REQUIRED")
    root=INSTALLED.parent.lstat()
    need(root.st_uid==0 and stat.S_IMODE(root.st_mode)==0o755
         and not INSTALLED.parent.is_symlink(),
         "ROOT_CODE_DIRECTORY_CUSTODY")
    raw=safe_file(TRUST,0,0o600,8192)
    policy=json.loads(raw)
    expected={
       "schema_version","action","candidate_sha","rollback_sha",
       "worker_sha256","installer_sha256","mcp_base_image_id",
       "mcp_overlay_image_id","source_worktree",
       "standing_authority","one_use_executor","permitted_actions",
       "expires_at","licensed_owner_oid","global_freeze_unchanged",
    }
    need(isinstance(policy,dict) and set(policy)==expected
         and policy["schema_version"]=="1.0"
         and policy["action"]==ACTION
         and SHA.fullmatch(policy["candidate_sha"]) is not None
         and policy["rollback_sha"]==ROLLBACK
         and all(DIGEST.fullmatch(policy[k]) is not None
                 for k in ("worker_sha256","installer_sha256"))
         and policy["mcp_base_image_id"]==
             "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
         and re.fullmatch(r"sha256:[a-f0-9]{64}",
             policy["mcp_overlay_image_id"]) is not None
         and policy["permitted_actions"]==sorted(ALLOWED)
         and policy["standing_authority"] is False
         and policy["one_use_executor"] is True
         and policy["global_freeze_unchanged"] is True
         and policy["licensed_owner_oid"]==
             "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
         and sha(safe_file(INSTALLED,0,0o444,150000))==
             policy["worker_sha256"],
         "ROOT_PINNED_WORKER_POLICY_INVALID")
    expires=datetime.fromisoformat(policy["expires_at"])
    need(expires.tzinfo is not None and
         datetime.now(timezone.utc)<expires<=
         datetime.now(timezone.utc)+timedelta(hours=24),
         "ROOT_WORKER_BOOTSTRAP_EXPIRED")
    worktree=Path(policy["source_worktree"])
    need(worktree.is_absolute() and str(worktree).startswith(
         WORKTREE_PREFIX)
         and not worktree.is_symlink(),
         "EXACT_REVIEWED_WORKTREE_PATH")
    info=worktree.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==1000
         and not info.st_mode&0o022,
         "REVIEWED_WORKTREE_CUSTODY")
    return policy,worktree

def request_folders():
    info=AUTH.lstat()
    need(stat.S_ISDIR(info.st_mode) and not AUTH.is_symlink()
         and info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o700,
         "ROOT_REQUEST_AUTHORITY_PATH")
    for p in (REQUESTS,PROCESSED,RESULTS):
        s=p.lstat()
        need(not p.is_symlink() and stat.S_ISDIR(s.st_mode)
             and s.st_uid==1000 and stat.S_IMODE(s.st_mode)==0o700,
             "ROOT_REQUEST_SPOOL_UNTRUSTED")

def checked_request(path,policy):
    need(path.parent==REQUESTS and IDENTITY.fullmatch(path.stem or "") is not None
         and path.suffix==".json","REQUEST_FILENAME_INVALID")
    obj=json.loads(safe_file(path,1000,0o600,4096))
    need(isinstance(obj,dict) and set(obj)=={
        "schema_version","request_id","action","candidate_sha","release_id"
    } and obj.get("schema_version")=="1.0"
         and obj.get("request_id")==path.stem
         and obj.get("action") in ALLOWED
         and obj.get("candidate_sha")==policy["candidate_sha"]
         and obj.get("release_id")=="release-"+policy["candidate_sha"][:16],
         "ONE_USE_ROOT_REQUEST_SCHEMA_OR_SCOPE")
    return obj

def reviewed_git(worktree,*params,timeout=25):
    account=pwd.getpwnam("al")
    caller=["/usr/sbin/runuser","-u","al","--","/usr/bin/env",*SAFE,
            "/usr/bin/git","-C",str(worktree),*params]
    result=subprocess.run(caller,cwd="/",capture_output=True,
                          timeout=timeout,check=False)
    need(result.returncode==0,"REVIEWED_GIT_SOURCE_UNAVAILABLE")
    return result.stdout

def exact_main_installer(policy,worktree):
    sha_value=policy["candidate_sha"]
    head=reviewed_git(worktree,"rev-parse","HEAD").decode().strip()
    need(head==sha_value,"CURRENT_CHECKOUT_HEAD_MISMATCH")
    need(not reviewed_git(worktree,"status","--porcelain",
                          "--untracked-files=all").strip(),
         "CURRENT_CHECKOUT_DIRTY")
    remote=reviewed_git(worktree,"ls-remote","origin","refs/heads/main",
                        timeout=60).decode().strip()
    need(remote==sha_value+"\trefs/heads/main",
         "PROTECTED_MAIN_HAS_ADVANCED")
    filename="tools/audit_journal_install.py"
    raw=reviewed_git(worktree,"show",sha_value+":"+filename)
    need(sha(raw)==policy["installer_sha256"],
         "EXACT_AUDIT_INSTALLER_HASH_CHANGED")
    module=types.ModuleType("reviewed_oneuse_audit_installer")
    module.__file__=str(worktree/filename)
    # Executable source is ONLY the authenticated protected Main Git blob,
    # never a caller-writable Python path.
    exec(compile(raw,module.__file__,"exec"),module.__dict__)
    return module

def invoke_reviewed_installer(installer,policy,action):
    need(action in ALLOWED,"UNSUPPORTED_INSTALLED_ROOT_ACTION")
    previous=sys.argv
    try:
        sys.argv=[installer.__file__,"--candidate-sha",
                  policy["candidate_sha"],(
                      "--stage-signed-owner-offer" if action=="audit_archive_stage"
                      else "--adopt-signed-chatgpt-owner")]
        installer.main()
    finally:sys.argv=previous

def exclusive_result(path,result):
    need(not os.path.lexists(path),"ROOT_RESULT_REPLAY")
    raw=canonical(result)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=False) as f:
            os.fchown(fd,1000,1000)
            os.fchmod(fd,0o600)
            f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(d)
    finally:os.close(d)

def dispatch(path,policy,worktree):
    request=checked_request(path,policy)
    need(not os.path.lexists(PROCESSED/path.name),"ONE_USE_ROOT_REQUEST_REPLAY")
    # There may be an already-used Owner proof, which the original Installer
    # and Root bridge will independently deny. No mutable request is consent.
    installer=exact_main_installer(policy,worktree)
    invoke_reviewed_installer(installer,policy,request["action"])
    return {
        "schema_version":"1.0","request_id":request["request_id"],
        "release_id":request["release_id"],"action":request["action"],
        "candidate_sha":request["candidate_sha"],
        "status":("root_exact_owner_offer_staged" if
                  request["action"]=="audit_archive_stage"
                  else "signed_exact_owner_root_archive_queued"),
        "recorded_at":datetime.now(timezone.utc).isoformat(),
        "standing_authority":False,
        "provider_writes":False,
    }

def drain():
    policy,worktree=root_stage_trust()
    request_folders()
    paths=sorted(REQUESTS.glob("*.json"))
    need(len(paths)<=2,"EXACT_ROOT_REQUEST_CAPACITY_EXCEEDED")
    outcomes=[]
    for path in paths:
        need(not os.path.lexists(PROCESSED/path.name)
             and not os.path.lexists(RESULTS/path.name),
             "PREVIOUS_ROOT_REQUEST_RESULT_ALREADY_EXISTS")
        try:
            row=dispatch(path,policy,worktree)
        except Exception as exc:
            row={
                "schema_version":"1.0","request_id":path.stem,
                "status":"denied","denial":(
                   str(exc).split(":")[0][:100]
                   if isinstance(exc,NativeArchiveDenied)
                   else type(exc).__name__),
                "recorded_at":datetime.now(timezone.utc).isoformat(),
                "production_deployment_verified":False,
            }
        exclusive_result(RESULTS/path.name,row)
        # No os.replace(): it could overwrite an unrelated prior receipt.
        # Destination creation must fail if another actor races with it.
        os.link(path,PROCESSED/path.name,follow_symlinks=False)
        os.unlink(path)
        outcomes.append(row)
        # A successful adopt is only QUEUED. Never conflate scheduling and
        # eventual archive acceptance or reclaim.
    return outcomes

if __name__=="__main__":
    try:
        rows=drain()
        print(json.dumps({"status":"exact_oneuse_archive_root_drain",
                          "count":len(rows),"results":rows},
                         sort_keys=True))
    except Exception as exc:
        print("AUDIT_ROOT_NATIVE=DENIED:"+
              (str(exc).split(":")[0][:100]
               if isinstance(exc,NativeArchiveDenied)
               else type(exc).__name__),file=sys.stderr)
        raise SystemExit(2)
