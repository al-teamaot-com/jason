#!/usr/bin/env python3
"""Source-only immutable Stage D one-service installation packet."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools import pmv4_d_runbook_read_install_root as root
from tools import pmv4_shadow_ci as ci

REPO=Path(__file__).resolve().parents[1]
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
SOURCE_PATH="tools/pmv4_d_runbook_read_install_root.py"
STAGE_C=ARTIFACTS/("pmv4-c-resume-"+root.STAGE_C_SHA)

class StageDBuilderDenied(RuntimeError):pass

def need(ok,code):
    if not ok:raise StageDBuilderDenied(code)

def sha(blob):return sha256(blob).hexdigest()

def canon(value):return root.canon(value)

def git(*args):
    completed=subprocess.run(["git","-C",str(REPO),*args],
                             capture_output=True,timeout=40)
    need(completed.returncode==0,"PROTECTED_GIT_READ_DENIED")
    return completed.stdout

def reviewed_blob(revision:str, name:str):
    tree=git("ls-tree",revision,"--",name).decode().strip()
    need(tree.startswith("100644 blob ") and tree.endswith("\t"+name),
         "SOURCE_BLOB_NOT_PLAIN_FILE:"+name)
    data=git("show",revision+":"+name)
    need((bool(data) or name.endswith("__init__.py")) and
         len(data)<250_000,"SOURCE_BLOB_TOO_LARGE:"+name)
    compile(data,name,"exec") if name.endswith(".py") else None
    return data

def launcher(path:Path,p)->bytes:
    sha40=p["source_sha"]
    stage="/run/jason-pmv4-d-runbook-"+sha40[:12]
    contents="""#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
MODE="${1:---check-only}"
[[ "$#" -le 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] || exit 2
[[ "$(id -u)" == 1000 ]] || exit 2
A='"""+str(path)+"""'
P="$A/root-release-plan.json"
S="$A/tools/pmv4_d_runbook_read_install_root.py"
STAGE='"""+stage+"""'
printf '%s  %s\\n' 'ROOT_SHA' "$S" | sha256sum --check --status
python3 -B - "$P" <<'PY_READONLY'
from pathlib import Path
import hashlib,json,sys
p=Path(sys.argv[1])
doc=json.loads(p.read_bytes())
assert doc["source_sha"]=="SOURCE_SHA"
assert doc["action"]=="pmv4-d-one-owner-independent-runbook-read-install-v1"
assert doc["root_sha256"]=="ROOT_SHA"
raw=dict(doc);expected=raw.pop("scope_sha256")
assert hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()==expected
print("PMV4_D_IMMUTABLE_UNPRIVILEGED_PREFLIGHT=PASS",flush=True)
print("EXACT_SOURCE_SHA="+doc["source_sha"],flush=True)
print("EXACT_SCOPE_SHA256="+expected,flush=True)
print("PRODUCTION_MUTATIONS=false; OWNER_APPROVAL_USED=false",flush=True)
PY_READONLY
[[ "$MODE" == "--check-only" ]] && exit 0
[[ -t 0 && -t 1 ]] || { echo "LOCAL_INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }
[[ ! -L "$STAGE" ]] || { echo "ROOT_STAGE_SYMLINK_DENIED" >&2; exit 2; }
if [[ ! -e "$STAGE" ]]; then
    sudo /usr/bin/install -o root -g root -m 0700 -d "$STAGE"
    sudo /usr/bin/install -o root -g root -m 0400 "$S" "$STAGE/root.py"
fi
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$P" --check-only
echo "PMV4_D_PROTECTED_ROOT_PREFLIGHT=PASS"
sudo /usr/bin/python3 -I -B "$STAGE/root.py" --plan "$P" --execute
echo "PMV4_D_EXACT_RUNBOOK_SERVICE_INSTALL_AND_READBACK=PASS"
""".replace("SOURCE_SHA",sha40).replace("ROOT_SHA",p["root_sha256"])
    subprocess.run(["bash","-n"],input=contents.encode(),
                   capture_output=True,check=True)
    return contents.encode()

def build():
    need(os.geteuid()==1000,"REQUIRES_LOCAL_AL_UID")
    source=git("rev-parse","HEAD").decode().strip()
    need(not git("status","--porcelain").strip(),"SOURCE_WORKTREE_DIRTY")
    require_main=subprocess.run(["gh","api",
        "repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
        capture_output=True,text=True,timeout=30)
    need(require_main.returncode==0 and require_main.stdout.strip()==source,
         "PROTECTED_MAIN_CHANGED")
    need(ci.protected_main_ci_verified(source),"PROTECTED_MAIN_CHECKS_NOT_PASSED")
    old_policy=STAGE_C/"watchdog-candidate.json"
    old_plan=json.loads((STAGE_C/"root-release-plan.json").read_bytes())
    old=old_policy.read_bytes()
    need(old_plan.get("candidate_sha")==root.STAGE_C_SHA and
         old_plan.get("watchdog_candidate_sha256")==sha(old) and
         old_policy.lstat().st_uid==1000 and
         int(old_policy.stat().st_mode & 0o777)==0o400,
         "STAGE_C_ACCEPTED_POLICY_BASE_MISMATCH")
    new=root.proposed_policy(old)
    need(root.UNIT in json.loads(new)["allowed_system_units"],
         "RUNBOOK_POLICY_ALLOWANCE_NOT_APPLIED")
    freeze=root.FREEZE.read_bytes()
    release=root.LKG.resolve(strict=True).name
    need(len(release)==40 and all(c in "0123456789abcdef" for c in release),
         "PRODUCTION_LKG_NOT_PINNED")
    scripts={name:reviewed_blob(source,name) for name in
             (SOURCE_PATH,)+root.FILES}
    need(scripts[SOURCE_PATH]==(REPO/SOURCE_PATH).read_bytes(),
         "ROOT_SOURCE_WORKTREE_CHANGED")
    plan={
        "schema_version":"1.0","action":root.ACTION,
        "source_sha":source,"candidate_sha":source,
        "root_sha256":sha(scripts[SOURCE_PATH]),
        "files_sha256":{name:sha(scripts[name]) for name in root.FILES},
        "policy_base_sha256":sha(old),"policy_target_sha256":sha(new),
        "freeze_sha256":sha(freeze),"rollback_sha":release,
        "stage_c_source_sha":root.STAGE_C_SHA,
        "stage_c_approval_id":root.STAGE_C_APPROVAL,
        "one_owner_total":1,
        "production_mutations":[
            "install_pinned_readonly_runbook_service",
            "allow_exact_runbook_service_in_native_drift_policy",
            "start_only_runbook_service_and_verify",
            "on_failure_restore_prior_service_and_policy",
        ],
        "runtime_restarts":0,"mcp_restarts":0,
        "ticket_core_restarts":0,"registry_writes":0,
        "later_stage_retirements_authorized":False,
    }
    plan["scope_sha256"]=sha(canon(plan))
    out=ARTIFACTS/("pmv4-d-runbook-read-"+source)
    temp=ARTIFACTS/(".pmv4-d-runbook-read-"+source+".building")
    need(not out.exists() and not temp.exists(),"CANDIDATE_ALREADY_EXISTS")
    temp.mkdir(mode=0o700)
    try:
        files={Path("tools")/Path(SOURCE_PATH).name:scripts[SOURCE_PATH],
               Path("root-release-plan.json"):canon(plan),
               Path("policy-base.json"):old,
               Path("policy-target.json"):new,
               Path("tools")/"pmv4_d_runbook_read_install_local.sh":launcher(out,plan)}
        files.update({Path("files")/name:scripts[name] for name in root.FILES})
        for rel,raw in files.items():
            destination=temp/rel
            destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            mode=0o500 if destination.name.endswith("_local.sh") else 0o400
            fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
            with os.fdopen(fd,"wb") as sink:
                sink.write(raw);sink.flush();os.fsync(sink.fileno())
            destination.chmod(mode)
        temp.rename(out)
    except BaseException:
        # An incomplete private staging directory never becomes executable.
        shutil.rmtree(temp,ignore_errors=True)
        raise
    print("PMV4_D_IMMUTABLE_RELEASE_PACKET=BUILT")
    print("SOURCE_SHA="+source)
    print("SCOPE_SHA256="+plan["scope_sha256"])
    print("NO_PRODUCTION_MUTATION=true; OWNER_APPROVAL_USED=false")
    return plan

if __name__=="__main__":
    try:build()
    except BaseException as exc:
        print("PMV4_D_BUILDER_DENIED="+type(exc).__name__+":"+str(exc)[:140],
              file=sys.stderr,flush=True)
        raise SystemExit(2)
