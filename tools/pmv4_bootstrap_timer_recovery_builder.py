#!/usr/bin/env python3
"""Source-only, protected-CI pinned one-use timer-recovery packet builder."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools import pmv4_bootstrap_timer_recovery_root as root
from tools import pmv4_shadow_ci as ci

SOURCE = Path(__file__).resolve().parents[1]
ARTIFACTS = Path("/srv/jason/archive/engineering-artifacts")
ENTRYPOINT = SOURCE / "tools/pmv4_bootstrap_timer_recovery_root.py"

class BootstrapTimerBuilderDenied(RuntimeError):
    pass

def need(ok, reason):
    if not ok:
        raise BootstrapTimerBuilderDenied(reason)

def sha(raw):
    return sha256(raw).hexdigest()

def canonical(doc):
    return json.dumps(doc,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def launcher(artifact: Path, sha40: str, root_hash: str) -> str:
    stage="/run/jason-pmv4-bootstrap-timer-"+sha40[:12]
    return """#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
MODE="${1:---check-only}"
[[ "$#" -le 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] || exit 2
[[ "$(id -u)" == 1000 ]] || exit 2
A='"""+str(artifact)+"""'
P="$A/root-release-plan.json"
SOURCE="$A/tools/pmv4_bootstrap_timer_recovery_root.py"
STAGE='"""+stage+"""'
printf '%s  %s\\n' '"""+root_hash+"""' "$SOURCE" | sha256sum --check --status
python3 -B - "$P" <<'PY_PLAN'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1])
data=json.loads(p.read_text())
assert data.get("action")=="pmv4-completed-catalog-bootstrap-timer-supersession-v1"
assert data.get("source_sha")=="TP_SOURCE_SHA"
assert data.get("root_sha256")=="TP_ROOT_SHA256"
blob=dict(data)
value=blob.pop("scope_sha256",None)
assert hashlib.sha256(json.dumps(blob,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()==value
print("IMMUTABLE_EXACT_ACTION_SOURCE_PREFLIGHT=PASS",flush=True)
print("EXACT_SCOPE_SHA256="+value,flush=True)
PY_PLAN
if [[ "$MODE" == "--check-only" ]]; then
    echo 'PRODUCTION_MUTATIONS=false; OWNER_APPROVAL=false'
    exit 0
fi
[[ -t 0 && -t 1 ]] || { echo "INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }
[[ ! -L "$STAGE" ]] || { echo "ROOT_STAGE_SYMLINK_DENIED" >&2; exit 2; }
if [[ ! -e "$STAGE" ]]; then
    sudo /usr/bin/install -o root -g root -m 0700 -d "$STAGE"
    sudo /usr/bin/install -o root -g root -m 0400 "$SOURCE" "$STAGE/root.py"
fi
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$P" --check-only
echo "PROTECTED_ROOT_AND_COMPLETED_INSTALL_PREFLIGHT=PASS"
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$P" --execute
echo "BOOTSTRAP_STALE_TIMER_RETIRED_AND_DRIFT_VERIFIED=PASS"
echo 'BREAKERS_REMAIN_NATIVE_AND_NOT_FORCED_CLOSED=true'
""".replace("TP_SOURCE_SHA",sha40).replace("TP_ROOT_SHA256",root_hash)

def build():
    need(os.geteuid()==1000,"LOCAL_UID_1000_REQUIRED")
    sha40=subprocess.check_output(
        ["git","-C",str(SOURCE),"rev-parse","HEAD"],
        text=True,timeout=10).strip()
    need(not subprocess.check_output(
        ["git","-C",str(SOURCE),"status","--porcelain"],
        text=True,timeout=10).strip(),"UNCOMMITTED_SOURCE")
    main=subprocess.check_output(
        ["gh","api","repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
        text=True,timeout=20).strip()
    need(sha40==main and ci.protected_main_ci_verified(sha40),
         "PROTECTED_MAIN_CI_NOT_READY")
    original=json.loads(root.INSTALL_PLAN.read_text())
    need(original.get("source_sha")==root.SOURCE_SHA and
         original.get("rollback_source_sha")==root.HOST_LKG.resolve(strict=True).name,
         "EXACT_COMPLETED_INSTALL_SOURCE_MISMATCH")
    plan={
        "schema_version":"1.0","action":root.ACTION,
        "candidate_sha":sha40,"source_sha":sha40,
        "rollback_sha":original["rollback_source_sha"],
        "root_sha256":sha(ENTRYPOINT.read_bytes()),
        "freeze_sha256":sha(root.FREEZE.read_bytes()),
        "old_timer_unit_sha256":sha(
            (Path("/etc/systemd/system")/root.OLD_TIMER).read_bytes()),
        "scoped_timer_unit_sha256":sha(
            (Path("/etc/systemd/system")/root.SCOPED_TIMER).read_bytes()),
        "owner_consents":1,
        "standing_authority":False,
        "later_stages_authorized":False,
        "no_runtime_or_mcp_restart":True,
        "production_mutations":[
            "disable_completed_bootstrap_recovery_timer",
            "reset_failed_completed_bootstrap_service",
            "restart_watchdog_oneshot",
            "reinstall_exact_timer_if_postflight_fails",
        ],
    }
    need(plan["freeze_sha256"]==original["freeze_sha256"],
         "LIVE_FREEZE_CHANGED")
    plan["scope_sha256"]=sha(canonical(plan))
    packet=ARTIFACTS/("pmv4-bootstrap-timer-"+sha40)
    stage=ARTIFACTS/(".pmv4-bootstrap-timer-"+sha40+".building")
    need(not packet.exists() and not stage.exists(),"PACKET_ALREADY_EXISTS")
    stage.mkdir(mode=0o700)
    try:
        (stage/"tools").mkdir(mode=0o700)
        for path,data,mode in (
            (stage/"root-release-plan.json",canonical(plan),0o400),
            (stage/"tools"/ENTRYPOINT.name,ENTRYPOINT.read_bytes(),0o400),
            (stage/"tools"/"run-exact-bootstrap-recovery.sh",
             launcher(packet,sha40,plan["root_sha256"]).encode(),0o500)
        ):
            path.write_bytes(data)
            path.chmod(mode)
        stage.rename(packet)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
    print("PMV4_BOOTSTRAP_TIMER_IMMUTABLE_PACKET=BUILT")
    print("EXACT_SOURCE_SHA="+sha40)
    print("EXACT_SCOPE_SHA256="+plan["scope_sha256"])
    print("PRODUCTION_MUTATIONS=false; OWNER_PROOF=false")
    return plan

if __name__=="__main__":
    try:build()
    except BaseException as exc:
        print("BOOTSTRAP_TIMER_BUILDER_DENIED="+type(exc).__name__+":"+str(exc)[:150],
              file=sys.stderr)
        raise SystemExit(2)
