#!/usr/bin/env python3
"""Read-only, complete filesystem/source preflight before a Stage E decision."""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_exact_code_transaction as transaction
from tools import pmv4_e_replacement_unit_bundle as units

BASE=Path("/usr/local/lib/jason/pmv4-e-bootstrap")
NATIVE=BASE/"native"
RELEASES=BASE/"releases"
SOURCE=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
JOURNALS=tuple(Path("/var/lib/jason/independent-component-release")/name for name in
    ("stage-e-code-before","stage-e-physical-before","stage-e-step-audit"))
ORIGINAL=Path("/opt/jason/independent-component-release/trusted")
SHARED=Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
SHARED_SHA="dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896"
CATALOG=Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
SAFE_ENV=[
    "PATH=/usr/bin:/bin","GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
    "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1","GIT_GRAFT_FILE=/dev/null",
    "GIT_CONFIG_COUNT=2","GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
    "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null",
]

class InstallationPreflightDenied(PermissionError):
    pass

def need(ok,reason):
    if not ok:
        raise InstallationPreflightDenied("PMV4_E_INSTALLATION_"+reason)

def root_ancestry(path):
    path=Path(path)
    need(path.is_absolute(),"ABSOLUTE_PATH_REQUIRED")
    for item in (path,*path.parents):
        meta=item.lstat()
        need(not item.is_symlink() and stat.S_ISDIR(meta.st_mode)
             and meta.st_uid==meta.st_gid==0 and meta.st_mode&0o022==0,
             "ROOT_ANCESTRY_UNTRUSTED:"+str(item))

def read_file(path,uid,mode=None):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        meta=os.fstat(stream.fileno())
        link=path.lstat()
        need(stat.S_ISREG(meta.st_mode) and stat.S_ISREG(link.st_mode)
             and (meta.st_dev,meta.st_ino)==(link.st_dev,link.st_ino)
             and meta.st_uid==meta.st_gid==uid and meta.st_nlink==1
             and meta.st_mode&0o022==0 and 0<meta.st_size<1000000
             and (mode is None or stat.S_IMODE(meta.st_mode)==mode),
             "FILE_IDENTITY_UNTRUSTED:"+str(path))
        raw=stream.read(1000001)
        need(len(raw)==meta.st_size,"FILE_CHANGED:"+str(path))
        return raw

def checked_out_source(candidate):
    meta=SOURCE.lstat()
    need(not SOURCE.is_symlink() and stat.S_ISDIR(meta.st_mode)
         and meta.st_uid==meta.st_gid==1000
         and stat.S_IMODE(meta.st_mode)==0o700,"REVIEW_SOURCE_NOT_PRIVATE")
    prefix=["/usr/sbin/runuser","-u","al","--","/usr/bin/env","-i",*SAFE_ENV]
    for args,expected in ((["rev-parse","HEAD"],candidate),(["status","--porcelain"],"")):
        result=subprocess.run(prefix+["/usr/bin/git","-C",str(SOURCE),*args],
            cwd="/",capture_output=True,text=True,timeout=30,check=False)
        need(result.returncode==0 and result.stdout.strip()==expected,
             "CHECKED_OUT_REVISION_OR_WORKTREE_MISMATCH")
    for name in packet.REVIEWED_PATHS:
        approved=read_file(packet.ROOT/name,0,0o444)
        actual=read_file(SOURCE/name,1000)
        need(actual==approved,"CHECKED_OUT_FILE_MISMATCH:"+name)

def collect(candidate,*,require_layout=False):
    need(os.geteuid()==0,"ROOT_ONLY")
    need(type(candidate) is str and re.fullmatch("[0-9a-f]{40}",candidate),
         "EXACT_CANDIDATE_REQUIRED")
    root_ancestry(BASE)
    root_ancestry(packet.ROOT)
    need(not os.path.lexists(NATIVE),"NATIVE_TRUST_ALREADY_PRESENT")
    need(not os.path.lexists("/opt/jason/pmv4-e-trusted"),
         "LEGACY_NATIVE_TRUST_ALREADY_PRESENT")
    if RELEASES.exists() or RELEASES.is_symlink():
        root_ancestry(RELEASES)
        need(stat.S_IMODE(RELEASES.stat().st_mode)==0o755,"RELEASE_PARENT_MODE_CHANGED")
    else:
        need(not require_layout,"RELEASE_PARENT_MISSING")
    need(not os.path.lexists(RELEASES/candidate),"RELEASE_SOURCE_ALREADY_PRESENT")
    ledger=JOURNALS[0].parent
    meta=ledger.lstat()
    need(not ledger.is_symlink() and stat.S_ISDIR(meta.st_mode)
         and meta.st_uid==meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o700,
         "ORIGINAL_NATIVE_LEDGER_PARENT_UNTRUSTED")
    for directory in JOURNALS:
        if os.path.lexists(directory):
            meta=directory.lstat()
            need(not directory.is_symlink() and stat.S_ISDIR(meta.st_mode)
                 and meta.st_uid==meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o700,
                 "NATIVE_JOURNAL_DIRECTORY_UNTRUSTED:"+str(directory))
        else:need(not require_layout,"NATIVE_JOURNAL_DIRECTORY_MISSING:"+str(directory))
    for user,root in ((True,Path("/home/al/.config/systemd/user")),
                      (False,Path("/etc/systemd/system"))):
        meta=root.lstat();uid=1000 if user else 0
        need(not root.is_symlink() and stat.S_ISDIR(meta.st_mode)
             and meta.st_uid==meta.st_gid==uid and meta.st_mode&0o022==0,
             "SYSTEMD_TARGET_PARENT_UNTRUSTED:"+str(root))
    for name in units.generate(base=packet.ROOT):
        parts=Path(name).parts
        root=Path("/home/al/.config/systemd/user") if parts[-2]=="user" else Path("/etc/systemd/system")
        need(not os.path.lexists(root/parts[-1]),"SYSTEMD_TARGET_ALREADY_PRESENT:"+parts[-1])
    marker_parent=Path("/etc/jason-owner-release/pmv4-e")
    root_ancestry(marker_parent.parent)
    if os.path.lexists(marker_parent):
        root_ancestry(marker_parent)
        need(stat.S_IMODE(marker_parent.stat().st_mode)==0o755,"MARKER_PARENT_MODE_CHANGED")
    checked_out_source(candidate)
    for name,target in transaction.DEFAULT_TARGETS.items():
        uid,gid,mode=transaction.DEFAULT_IDENTITIES[name]
        raw=read_file(target,uid,mode)
        need(sha256(raw).hexdigest()==transaction.EXPECTED_BEFORE[name],
             "CONTROL_BEFORE_IMAGE_CHANGED:"+name)
    need(sha256(read_file(SHARED,0,0o755)).hexdigest()==SHARED_SHA,
         "SHARED_WORKER_CHANGED")
    policy=json.loads(read_file(CATALOG,0,0o600))
    need(policy.get("root_worker_sha256")==SHARED_SHA,"CATALOG_WORKER_PIN_CHANGED")
    for directory in (ORIGINAL,ORIGINAL/"tools",ORIGINAL/"implementation",
                      ORIGINAL/"implementation/kernel"):
        meta=directory.lstat()
        need(not directory.is_symlink() and stat.S_ISDIR(meta.st_mode)
             and meta.st_uid==meta.st_gid==0 and meta.st_mode&0o022==0,
             "ORIGINAL_NATIVE_DIRECTORY_CHANGED")
    for name in packet.ROOT_COMPONENTS_PREINSTALLED:
        need(read_file(ORIGINAL/name,0,0o444)==read_file(packet.ROOT/name,0,0o444),
             "ORIGINAL_NATIVE_BYTES_CHANGED:"+name)
    return {
        "status":"stage_e_installation_preflight_passed",
        "candidate_sha":candidate,"checked_out_files":len(packet.REVIEWED_PATHS),
        "native_trust":str(NATIVE),"immutable_release_parent":str(RELEASES),
        "root_ancestry_verified":True,"control_before_images_verified":True,
        "original_native_modules_verified":4,"production_mutations":False,
        "owner_approval_issued":False,
    }
