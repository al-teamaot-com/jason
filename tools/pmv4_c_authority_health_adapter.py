#!/usr/bin/env python3
"""Stage C canonical authority fast health and fresh full-integrity proof.

Source-only until a separately authenticated Owner/root release installs the
exact reviewed file. No provider calls, state copying, path aliases, stale
proof adoption, expired emergency exceptions or synthetic integrity PASS.

Full integrity (including the ~41 GB orchestration audit) remains a separate,
bounded 90-minute low-priority systemd task, never a side effect of fast health.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping

INSTALLED=Path(
    "/usr/local/lib/jason/pmv4-c-canonical-health-v1/pmv4_c_authority_health_adapter.py"
)
LKG_TOOLS=Path("/opt/jason/current/tools")
AUTHORITY=Path("/var/lib/jason/authority/authority.sqlite3")
REPLAY=Path("/var/lib/jason/openclaw/replay.sqlite3")
SECURITY=Path("/var/lib/jason/openclaw/security-audit.sqlite3")
ORCH=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
LEGACY_ORCH=Path("/var/lib/jason/openclaw/orchestration-events.sqlite3")
REGISTRY=Path("/var/lib/jason/openclaw/trusted-keys/registry.json")
OUTPUT=Path("/var/lib/jason/openclaw/operational-health.json")
FULL=Path("/var/lib/jason/openclaw/operational-full-health.json")
ARCHIVE=Path("/srv/jason/archive")
MAX_FULL_SECONDS=5400
DATABASES={
    "authority":AUTHORITY,
    "replay":REPLAY,
    "security_audit":SECURITY,
    "orchestration_audit":ORCH,
}


class CanonicalHealthDenied(RuntimeError):
    pass


def need(condition:bool,reason:str)->None:
    if not condition:
        raise CanonicalHealthDenied(reason)


def canonical_path_gate(*,uid:int=1000) -> dict[str,tuple[int,int]]:
    """Only canonical new SQLite files: no ambiguous legacy aliases."""
    trusted={}
    for key,path in DATABASES.items():
        need(path.is_absolute() and not path.is_symlink(),
             "C_HEALTH_CANONICAL_PATH_NOT_TRUSTED:"+key)
        info=path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_uid==uid
             and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,
             "C_HEALTH_CANONICAL_DB_NOT_TRUSTED:"+key)
        trusted[key]=(info.st_dev,info.st_ino)
    need(not LEGACY_ORCH.exists() and not LEGACY_ORCH.is_symlink(),
         "C_HEALTH_SPLIT_BRAIN_ORCHESTRATION")
    return trusted


def _trusted_runtime():
    """Load only frozen LKG helpers; no import path from user worktrees."""
    need(LKG_TOOLS.is_dir() and
         LKG_TOOLS.resolve().parent==Path("/opt/jason/current").resolve(),
         "C_HEALTH_RUNTIME_HELPERS_CHANGED")
    if str(LKG_TOOLS) not in sys.path:
        sys.path.insert(0,str(LKG_TOOLS))
    fast=importlib.import_module("openclaw_authority_fast_health")
    snap=importlib.import_module("openclaw_authority_health_snapshot")
    return fast,snap


def _atomic_snapshot(writer:Callable[[Path,dict],None],path:Path,report:dict)->None:
    writer(path,report)


def fast_cycle(*, checker:Any, writer:Callable[[Path,dict],None],
               output:Path=OUTPUT,full:Path=FULL,uid:int=1000)->dict:
    canonical_path_gate(uid=uid)
    # The pinned LKG verifier requires the full proof to name the *same*
    # canonical path. The previous legacy-path PASS must not be reissued.
    report=checker.check(output=output,full_path=full,databases=dict(DATABASES))
    need(isinstance(report,dict),"C_HEALTH_FAST_RESULT_INVALID")
    _atomic_snapshot(writer,output,report)
    return report


def expected_full_report(result:Mapping[str,Any])->bool:
    """A zero-exit actual full SQLite+backup/restore proof, never a guess."""
    if (not isinstance(result,Mapping)
        or result.get("status")!="pass"
        or result.get("failures")!=[]
        or result.get("provider_contacted") is not False
        or result.get("provider_credentials_used") is not False):
        return False
    files=result.get("files")
    if not isinstance(files,Mapping) or set(files)!=set(DATABASES):
        return False
    for name,path in DATABASES.items():
        f=files.get(name)
        if not isinstance(f,Mapping) or (
            f.get("path")!=str(path)
            or f.get("present") is not True
            or f.get("mode")!="0o600"
            or f.get("integrity")!="ok"
        ):
            return False
    registry=result.get("trusted_key_registry")
    if not isinstance(registry,Mapping) or not (
        registry.get("present") is True
        and registry.get("mode")=="0o600"
        and type(registry.get("active_records")) is int
        and registry["active_records"]>=1
    ):
        return False
    delegations=result.get("delegations")
    if not isinstance(delegations,Mapping) or delegations.get("expired_active_records")!=0:
        return False
    proof=result.get("backup_restore_proof")
    if not isinstance(proof,Mapping) or not all((
        proof.get("backup_integrity")=="ok",
        proof.get("restore_integrity")=="ok",
        proof.get("backup_mode")=="0o600",
        proof.get("restore_mode")=="0o600",
        proof.get("counts_match") is True,
    )):
        return False
    return True


def full_cycle(*, writer:Callable[[Path,dict],None],
               runner:Callable[...,Any]=subprocess.run,
               output:Path=FULL,archive:Path=ARCHIVE,
               timeout:int=MAX_FULL_SECONDS,uid:int=1000)->dict:
    canonical_path_gate(uid=uid)
    need(timeout==MAX_FULL_SECONDS,"C_HEALTH_FULL_TIMEOUT_UNREVIEWED")
    with tempfile.TemporaryDirectory(
        prefix="pmv4-c-fresh-integrity-",dir=str(archive)
    ) as scratch:
        cmd=[
            sys.executable,
            str(LKG_TOOLS/"openclaw_authority_operational_health.py"),
            "--authority-database",str(AUTHORITY),
            "--replay-database",str(REPLAY),
            "--security-audit",str(SECURITY),
            "--orchestration-audit",str(ORCH),
            "--key-registry",str(REGISTRY),
            "--backup-temp-root",scratch,
        ]
        try:
            process=runner(cmd,check=False,capture_output=True,
                           text=True,timeout=timeout)
            if process.returncode==0:
                try:report=json.loads(process.stdout)
                except (ValueError,TypeError):report=None
                if isinstance(report,dict) and expected_full_report(report):
                    report["snapshot_source_exit_code"]=0
                    _atomic_snapshot(writer,output,report)
                    return report
            reason="canonical_full_integrity_invalid"
            code=process.returncode
        except subprocess.TimeoutExpired:
            reason="operational_health_timeout";code=124
        except (OSError,ValueError,TypeError):
            reason="canonical_full_integrity_launch_failure";code=2
        failure={
            "status":"fail",
            "failures":[reason],
            "snapshot_source_exit_code":code,
            "provider_contacted":False,
            "provider_credentials_used":False,
            "schema_version":"1.0",
            "canonical_orchestration_db":str(ORCH),
        }
        _atomic_snapshot(writer,output,failure)
        return failure


def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--mode",required=True,choices=("fast","full"))
    args=p.parse_args()
    # Critical: this source-only file must never become a user's bypass to
    # publish operational "PASS" outside exact root-installed release control.
    need(os.geteuid()==1000 and Path(__file__).resolve()==INSTALLED,
         "C_HEALTH_OWNER_ROOT_INSTALL_REQUIRED")
    fast,snapshot=_trusted_runtime()
    if args.mode=="fast":
        report=fast_cycle(checker=fast,writer=snapshot.write_atomic_snapshot)
    else:
        report=full_cycle(writer=snapshot.write_atomic_snapshot)
    print(json.dumps({
        "status":report.get("status"),
        "failures":report.get("failures"),
        "canonical_orchestration_db":str(ORCH),
        "full_integrity_is_distinct":True,
        "provider_contacted":False,
        "owner_release_required":True,
    },sort_keys=True),flush=True)
    return 0 if report.get("status")=="pass" and report.get("failures")==[] else 2


if __name__=="__main__":
    try:raise SystemExit(main())
    except CanonicalHealthDenied as exc:
        print("PMV4_C_AUTHORITY_HEALTH=DENIED "+str(exc),file=sys.stderr)
        raise SystemExit(2)
