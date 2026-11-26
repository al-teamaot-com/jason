#!/usr/bin/env python3
"""Submit one bounded request to a separately Root-attested archive executor.

Not production authority. Stage produces a Root-verified offer. Adopt only
asks the installed Root service to verify the one-use signed Owner proof.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
from uuid import uuid4

ROOT=Path("/var/lib/jason/authority/audit-journal-release")
WORKER=Path("/usr/local/lib/jason/audit-journal-owner-executor/worker.py")
UNIT="jason-audit-journal-owner-executor.path"
ACTIONS=frozenset({"audit_archive_stage","audit_archive_adopt"})
SHA=re.compile(r"[a-f0-9]{40}\Z")
OWNER=1000

class RequestDenied(PermissionError):pass
def need(value,reason):
    if not value:raise RequestDenied("AUDIT_JOURNAL_NATIVE_REQUEST_"+reason)
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def directory(p,owner=OWNER):
    m=p.lstat()
    need(not p.is_symlink() and stat.S_ISDIR(m.st_mode)
         and m.st_uid==owner and stat.S_IMODE(m.st_mode)==0o700,
         "REVIEWED_REQUEST_DIRECTORY_CUSTODY")
def available():
    m=WORKER.lstat()
    need(not WORKER.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==0 and stat.S_IMODE(m.st_mode)==0o444
         and m.st_nlink==1,
         "EXACT_ROOT_WORKER_NOT_INSTALLED")
    result=subprocess.run(["/usr/bin/systemctl","is-active","--quiet",UNIT],
                          capture_output=True,check=False,timeout=10)
    need(result.returncode==0,"EXACT_ROOT_WORKER_PATH_INACTIVE")
    for d in (ROOT,ROOT/"requests",ROOT/"processed",
              ROOT/"results",ROOT/"offers",ROOT/"owner-approvals"):
        directory(d)

def submit(action,candidate_sha):
    need(os.geteuid()==OWNER and action in ACTIONS
         and isinstance(candidate_sha,str) and SHA.fullmatch(candidate_sha),
         "APPROVED_ONE_USE_REQUEST_IDENTITY")
    available()
    release_id="release-"+candidate_sha[:16]
    if action=="audit_archive_adopt":
        approval=ROOT/"owner-approvals"/(release_id+".json")
        meta=approval.lstat()
        need(not approval.is_symlink()
             and stat.S_ISREG(meta.st_mode) and meta.st_uid==OWNER
             and stat.S_IMODE(meta.st_mode)==0o600
             and meta.st_nlink==1 and 0<meta.st_size<16384,
             "EXACT_OWNER_PROOF_MISSING")
    document={
        "schema_version":"1.0","request_id":uuid4().hex,
        "action":action,"candidate_sha":candidate_sha,
        "release_id":release_id,
    }
    path=ROOT/"requests"/(document["request_id"]+".json")
    raw=canon(document)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb",closefd=False) as f:
            os.fchmod(fd,0o600)
            f.write(raw);f.flush();os.fsync(fd)
    finally:os.close(fd)
    return {
        "status":"queued_for_exact_root_validation_not_deployed",
        "request_id":document["request_id"],
        "action":action,"release_id":release_id,
        "candidate_sha":candidate_sha,
        "root_result_file":str(ROOT/"results"/path.name),
        "owner_approval_created":False,
        "production_deployed":False,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--action",required=True,choices=sorted(ACTIONS))
    parser.add_argument("--candidate-sha",required=True)
    args=parser.parse_args()
    print(json.dumps(submit(args.action,args.candidate_sha),sort_keys=True))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("DENIED:"+(str(exc).split(":")[0]
              if isinstance(exc,RequestDenied) else type(exc).__name__))
        raise SystemExit(2)
