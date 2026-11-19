#!/usr/bin/env python3
"""Root-only admission for legacy vs exact PMv4 host reconciliation.

This never authorizes a cutover, installs a service, writes a receipt, or
accepts an unsigned caller mode. Missing accepted marker means legacy.
Present-but-invalid accepted marker means DENY, never PMv3 fallback.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

TRUST_ROOT=Path("/opt/jason/pmv4-e-trusted")
TRUST_ENTRY=TRUST_ROOT/"tools/pmv4_e_root_reconcile_admission.py"
MARKER=Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
UNIT_GUARD=TRUST_ROOT/"tools/pmv4_e_unit_admission.py"
SHA=re.compile(r"^[0-9a-f]{40}$")


class RootReconcileAdmissionDenied(PermissionError):
    pass


def need(ok:bool,why:str)->None:
    if not ok:
        raise RootReconcileAdmissionDenied("PMV4_E_RECONCILE_"+why)


def checked_trust_root(root:Path=TRUST_ROOT)->None:
    need(root==TRUST_ROOT,
         "ROOT_SOURCE_CANNOT_BE_SUBSTITUTED")
    for p in (root,root/"tools",TRUST_ENTRY,UNIT_GUARD):
        try:
            v=p.lstat()
        except OSError as exc:
            raise RootReconcileAdmissionDenied(
                "PMV4_E_RECONCILE_ROOT_GUARD_NOT_INSTALLED") from exc
        need(not p.is_symlink() and v.st_uid==0 and v.st_gid==0
             and v.st_mode&0o022==0
             and (stat.S_ISDIR(v.st_mode) if p in (root,root/"tools")
                  else stat.S_ISREG(v.st_mode)),
             "INSTALLED_ROOT_GUARD_UNTRUSTED")


def decide(*,source_revision:str,
           marker:Path=MARKER,
           guard=None,
           require_installed:bool=True)->dict:
    need(os.geteuid()==0,
         "ROOT_IDENTITY_REQUIRED")
    need(isinstance(source_revision,str)
         and SHA.fullmatch(source_revision) is not None,
         "SOURCE_REVISION_NOT_EXACT")
    try:
        marker.lstat()
    except FileNotFoundError:
        return {"status":"legacy_pre_retirement",
                "mode":"legacy",
                "cutover_accepted":False,
                "production_mutations":False}
    except OSError as exc:
        raise RootReconcileAdmissionDenied(
            "PMV4_E_RECONCILE_MARKER_UNAVAILABLE") from exc
    # A present but corrupt/ambiguous marker cannot silently use PMv3.
    if require_installed:
        checked_trust_root()
    if guard is None:
        sys.path.insert(0,str(TRUST_ROOT))
        from tools import pmv4_e_unit_admission as unit_admission
        guard=unit_admission
    try:
        receipt=guard.read_root_marker(marker)
    except (PermissionError,OSError,ValueError,TypeError) as exc:
        raise RootReconcileAdmissionDenied(
            "PMV4_E_RECONCILE_ROOT_ACCEPTED_PROOF_INVALID") from exc
    rollback=receipt.get("source_rollback_sha") if isinstance(receipt,dict) else None
    need(isinstance(receipt,dict)
         and receipt.get("state")=="accepted"
         and receipt.get("source_sha")==source_revision
         and isinstance(rollback,str)
         and SHA.fullmatch(rollback) is not None
         and rollback!=source_revision,
         "ROOT_RELEASE_SOURCE_OR_RECEIPT_NOT_EXACT")
    return {"status":"replacement_root_acceptance_verified",
            "mode":"replacement",
            "cutover_accepted":True,
            "source_revision":source_revision,
            "runtime_mcp_source_revision":rollback,
            "production_mutations":False}


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-revision",required=True)
    choices=parser.add_mutually_exclusive_group()
    choices.add_argument("--mode-only",action="store_true",
                         help="Emit only the validated mode for shell admission")
    choices.add_argument("--runtime-baseline-only",action="store_true",
                         help="Emit exact root-accepted original runtime/MCP SHA")
    args=parser.parse_args(argv)
    try:
        # Only the installed root-owned file is the deployable entrypoint.
        need(Path(__file__).resolve()==TRUST_ENTRY,
             "REVIEWED_ROOT_ENTRYPOINT_NOT_INSTALLED")
        result=decide(source_revision=args.source_revision)
        if args.runtime_baseline_only:
            need(result["mode"]=="replacement"
                 and isinstance(result.get("runtime_mcp_source_revision"),str)
                 and SHA.fullmatch(result["runtime_mcp_source_revision"]) is not None,
                 "UNACCEPTED_RUNTIME_MCP_BASELINE")
            print(result["runtime_mcp_source_revision"])
        else:
            print(result["mode"] if args.mode_only else json.dumps(result,sort_keys=True))
        return 0
    except RootReconcileAdmissionDenied as exc:
        print(str(exc)[:180],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
