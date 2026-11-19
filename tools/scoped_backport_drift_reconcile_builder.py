#!/usr/bin/env python3
"""Immutable owner-signed recovery packet. Read-only until Owner executes."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from . import scoped_backport_drift_reconcile_root as root
from . import pmv4_shadow_ci as ci

SOURCE=Path(__file__).resolve().parents[1]
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
APPROVED_BASELINE=Path(
 "/srv/jason/archive/engineering-artifacts/"
 "pmv4-d-runbook-read-0467f3b29d2f6cbc0415ef9017627eb3c4a02915/policy-target.json"
)
ROOT_SCRIPT=SOURCE/"tools/scoped_backport_drift_reconcile_root.py"
OWNER_SCRIPT=SOURCE/"tools/scoped_backport_drift_reconcile_owner.py"

class PacketDenied(RuntimeError): pass

def need(ok,reason):
    if not ok:raise PacketDenied(reason)

def build():
    need(os.geteuid()==1000,"BUILDER_OWNER_REQUIRED")
    candidate=subprocess.check_output(["git","-C",str(SOURCE),"rev-parse","HEAD"],text=True,timeout=15).strip()
    main=subprocess.check_output(["gh","api","repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
                                  text=True,timeout=20).strip()
    need(candidate==main and
         not subprocess.check_output(["git","-C",str(SOURCE),"status","--porcelain"],text=True).strip(),
         "PROTECTED_MAIN_OR_CLEAN_TREE_REQUIRED")
    need(ci.protected_main_ci_verified(candidate),"PROTECTED_MAIN_CI_REQUIRED")
    base=APPROVED_BASELINE.read_bytes()
    expect=root.expected_policy(base)
    target=(json.dumps(expect,indent=2,sort_keys=True)+"\n").encode()
    unit_files={name:root.digest((Path("/etc/systemd/system")/name).read_bytes()) for name in root.CANDIDATE_NAMES}
    need(unit_files==root.PINNED_UNIT_SHA256,"PROTECTED_SCOPED_BACKPORT_UNIT_BLOBS_CHANGED")
    rollback=Path("/opt/jason/current").resolve(strict=True).name
    need(len(rollback)==40,"LKG_SHA_INVALID")
    freeze=root.digest(root.FREEZE.read_bytes())
    hold=root.digest(root.HOLD.read_bytes())
    plan={
        "schema_version":"1.0","action":root.ACTION,
        "source_sha":candidate,"candidate_sha":candidate,
        "rollback_sha":rollback,
        "production_lkg_sha":rollback,
        "baseline_policy_sha256":root.digest(base),
        "candidate_policy_sha256":root.digest(target),
        "scoped_backport_unit_names":list(root.CANDIDATE_NAMES),
        "unit_file_sha256":unit_files,
        "root_sha256":root.digest(ROOT_SCRIPT.read_bytes()),
        "owner_sha256":root.digest(OWNER_SCRIPT.read_bytes()),
        "freeze_sha256":freeze,"hold_sha256":hold,
        "owner_consents":1,"standing_authority":False,
        "later_stages_authorized":False,
        "restart_containers":[],
        "production_mutations":["root_scoped_backport_four_unit_allowlist","watchdog_oneshot","native_root_breaker_revalidation","restore_exact_baseline_on_failure","one_use_audit_receipts"],
    }
    plan["scope_sha256"]=root.digest(root.canon(plan))
    destination=ARTIFACTS/("scoped-backport-drift-"+candidate)
    staging=ARTIFACTS/(".scoped-backport-drift-"+candidate+".building")
    need(not destination.exists() and not staging.exists(),"PACKET_ALREADY_EXISTS")
    staging.mkdir(mode=0o700)
    try:
        (staging/"tools").mkdir(mode=0o700)
        for fname,data in (("root-release-plan.json",root.canon(plan)),
                           ("baseline.json",base),("candidate.json",target)):
            p=staging/fname;p.write_bytes(data);p.chmod(0o400)
        for src in (ROOT_SCRIPT,OWNER_SCRIPT):
            p=staging/"tools"/src.name
            shutil.copy2(src,p);p.chmod(0o400)
        launcher=staging/"tools"/"run-scoped-backport-drift-recovery.sh"
        launcher.write_text("""#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] || exit 2
[[ $(id -u) == 1000 ]] || { echo "LOCAL_UID_1000_REQUIRED" >&2; exit 2; }
A='"""+str(destination)+"""'
STAGE='/run/jason-scoped-backport-drift-"""+candidate[:12]+"""'
O="$A/tools/scoped_backport_drift_reconcile_owner.py"
R="$A/tools/scoped_backport_drift_reconcile_root.py"
PLAN="$A/root-release-plan.json"
printf '%s  %s\\n' '"""+plan["owner_sha256"]+"""' "$O" | sha256sum --check --status
printf '%s  %s\\n' '"""+plan["root_sha256"]+"""' "$R" | sha256sum --check --status
python3 -B "$O" --plan "$PLAN" --check-only
echo 'SCOPED_BACKPORT_DRIFT_IMMUTABLE_SIGNER_AND_SOURCE=PASS'
echo 'PRODUCTION_MUTATIONS=false; OWNER_PROOF=false'
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi
[[ -t 0 && -t 1 ]] || { echo "REAL_INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }
[[ ! -L "$STAGE" ]] || { echo "ROOT_STAGE_SYMLINK_DENIED" >&2; exit 2; }
echo 'SCOPE: four approved scoped-backport service/timer/path declarations; native watchdog oneshot ONLY'
echo 'TICKET CORE, MCP, FREEZE=UNMODIFIED; BREAKER=NATIVE ROOT REVALIDATION'
if [[ ! -e "$STAGE" ]]; then
  sudo /usr/bin/install -d -m 0700 -o root -g root "$STAGE"
  sudo /usr/bin/install -m 0400 -o root -g root "$R" "$STAGE/root.py"
fi
# An interrupted preflight may be repeated ONLY against the exact same
# root-owned file; the root executable itself verifies its pinned SHA.
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$PLAN" --preflight
python3 -B "$O" --plan "$PLAN" --authorize
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$PLAN" --execute
echo 'SCOPED_BACKPORT_DRIFT_FOUR_UNIT_POLICY=VERIFIED; NATIVE_BREAKER_REVALIDATION_STILL_REQUIRED'
""")
        launcher.chmod(0o500)
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    print("SCOPED_BACKPORT_DRIFT_IMMUTABLE_PACKET=BUILT",flush=True)
    print("SOURCE_SHA="+candidate,flush=True)
    print("SCOPE_SHA256="+plan["scope_sha256"],flush=True)
    print("POLICY_BASE_SHA256="+plan["baseline_policy_sha256"],flush=True)
    print("POLICY_TARGET_SHA256="+plan["candidate_policy_sha256"],flush=True)
    print("NO_PRODUCTION_MUTATION=true",flush=True)

if __name__=="__main__":
    try:build()
    except BaseException as exc:
        print("SCOPED_BACKPORT_DRIFT_BUILDER_DENIED="+type(exc).__name__+":"+str(exc)[:170],file=sys.stderr)
        raise SystemExit(2)
