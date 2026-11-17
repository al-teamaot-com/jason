#!/usr/bin/env python3
"""Build one immutable, source-bound PMv4 Stage C release packet.

Preproduction preparation only: no Owner consent, root mutation, service stop,
data move, provider action, or worker activation.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
from typing import Any, Mapping

from tools import pmv4_c_service_manifest as service_contract
from tools import pmv4_c_atomic_root as root_contract
from tools import pmv4_shadow_ci as protected_ci

ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
FREEZE=root_contract.FREEZE
HOLD=root_contract.HOLD
ACTION=root_contract.ACTION
WORKER=root_contract.WORKER

STAGED_FILES=(
    "tools/pmv4_c_sqlite_family_handoff.py",
    "tools/pmv4_c_service_manifest.py",
    "tools/pmv4_ticket_core_exact_projection.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_ci.py",
    "tools/deploy_live_container.py",
    "tools/pmv4_mcp_projection.py",
)
DBS=tuple(
    str(Path("/var/lib/jason/openclaw")/name)
    for name in (
        "autonomy-operational-work.sqlite3",
        "playbook-autonomy.sqlite3",
        "autonomy-targeted-wakes.sqlite3",
        "ticket-split.sqlite3",
        "teams-identity-bindings.sqlite3",
        "orchestration-events.sqlite3",
        "governed-execution.sqlite3",
        "reflection.sqlite3",
        "resolution-memory.sqlite3",
        "model-usage.sqlite3",
    )
)

class BuilderDenied(RuntimeError):
    pass

def need(ok:bool,code:str)->None:
    if not ok: raise BuilderDenied(code)

def canon(value:Mapping[str,Any])->bytes:
    return json.dumps(dict(value),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def sha(raw:bytes)->str:
    return sha256(raw).hexdigest()

def _metadata(path:Path, *, directory:bool=False)->dict[str,int]:
    info=path.lstat()
    need(not path.is_symlink() and
         (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)),
         "C_BUILD_OBJECT_NOT_TRUSTED:"+str(path))
    return {
        "device":info.st_dev,"inode":info.st_ino,
        "uid":info.st_uid,"gid":info.st_gid,
        "mode":stat.S_IMODE(info.st_mode),
    }

def _docker(name:str)->dict[str,Any]:
    rows=json.loads(subprocess.check_output(
        ["/usr/bin/docker","inspect",name],text=True,timeout=20))
    need(isinstance(rows,list) and len(rows)==1 and isinstance(rows[0],dict),
         "C_BUILD_DOCKER_INSPECT_INVALID")
    return rows[0]

def _env(item:Mapping[str,Any])->dict[str,str]:
    out={}
    for row in (item.get("Config") or {}).get("Env") or []:
        need(isinstance(row,str) and "=" in row,"C_BUILD_ENV_INVALID")
        key,value=row.split("=",1);out[key]=value
    return out

def _worktree_source(candidate:str)->Path:
    here=Path(__file__).resolve().parents[1]
    need(subprocess.check_output(
        ["/usr/bin/git","-C",str(here),"rev-parse","HEAD"],
        text=True,timeout=10).strip()==candidate,
        "C_BUILD_WORKTREE_SOURCE_MISMATCH")
    need(not subprocess.check_output(
        ["/usr/bin/git","-C",str(here),"status","--porcelain"],
        text=True,timeout=10).strip(),
        "C_BUILD_WORKTREE_NOT_CLEAN")
    return here

def _candidate_policy(source:Path)->tuple[bytes,bytes]:
    raw=(source/"config/production-desired-state.json").read_bytes()
    base=json.loads(raw)
    need(isinstance(base,dict) and base.get("schema_version")=="1.0",
         "C_BUILD_WATCHDOG_BASE_INVALID")
    allowed=base.get("allowed_running_containers")
    need(isinstance(allowed,list) and WORKER not in allowed
         and "jason-pmv4-shadow-gateway" in allowed,
         "C_BUILD_WATCHDOG_BASE_NOT_STAGE_C_READY")
    candidate=json.loads(json.dumps(base))
    candidate["allowed_running_containers"].append(WORKER)
    rendered=(json.dumps(candidate,indent=2,sort_keys=False)+"\n").encode()
    return raw,rendered

def _latest_scan()->tuple[str,str]:
    db=Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
    uri="file:"+str(db)+"?mode=ro"
    with sqlite3.connect(uri,uri=True,timeout=2) as con:
        row=con.execute(
            "SELECT cycle_id,scanned_at FROM autonomy_ticket_scan_cycle "
            "ORDER BY scanned_at DESC LIMIT 1").fetchone()
    need(row is not None and all(isinstance(x,str) and x for x in row),
         "C_BUILD_SCAN_BASELINE_MISSING")
    return row[0],row[1]

def _launcher(plan:Mapping[str,Any],artifact:Path,
              root_sha:str,owner_sha:str)->str:
    short=plan["candidate_sha"][:12]
    stage="/run/jason-pmv4-c-"+short
    support="\n".join(f'  "{rel}"' for rel in plan["staged_source_files"])
    D="$"
    return f'''#!/usr/bin/env bash
# Exact PMv4 Stage C one-Owner cutover. Generated immutable release artifact.
set -Eeuo pipefail
umask 077
MODE="{D}{{1:-}}"
[[ "{D}#" == 1 && ( "{D}MODE" == "--check-only" || "{D}MODE" == "--execute" ) ]] ||
  {{ echo "PMV4_C_LOCAL=DENIED INVALID_MODE" >&2; exit 2; }}
[[ "{D}(id -u)" == "1000" ]] ||
  {{ echo "PMV4_C_LOCAL=DENIED OWNER_LOCAL_UID_REQUIRED" >&2; exit 2; }}

ART="{artifact}"
PLAN="{D}ART/root-release-plan.json"
OWNER="{D}ART/tools/pmv4_c_atomic_owner.py"
ROOT="{D}ART/tools/pmv4_c_atomic_root.py"
STAGE="{stage}"
STAGED="{D}STAGE/installer.py"
ROOT_SHA="{root_sha}"
OWNER_SHA="{owner_sha}"
SUPPORT=(
{support}
)
hash_check() {{
  printf '%s  %s\\n' "{D}1" "{D}2" | /usr/bin/sha256sum --check --status
}}
hash_check "{D}ROOT_SHA" "{D}ROOT"
hash_check "{D}OWNER_SHA" "{D}OWNER"
cd "{D}ART"
PYTHONPATH="{D}ART/src:." /usr/bin/python3 -B "{D}OWNER" --plan "{D}PLAN" --check-only
[[ ! -e "{D}ART/root-oneowner-proof.json" && ! -L "{D}ART/root-oneowner-proof.json" ]] ||
  {{ echo "PMV4_C_LOCAL=DENIED OWNER_PROOF_ALREADY_EXISTS" >&2; exit 2; }}
[[ ! -e "{D}STAGE" && ! -L "{D}STAGE" ]] ||
  {{ echo "PMV4_C_LOCAL=DENIED ROOT_STAGE_ALREADY_EXISTS" >&2; exit 2; }}
echo "PMV4_C_EXACT_SOURCE_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false"
if [[ "{D}MODE" == "--check-only" ]]; then exit 0; fi
[[ -t 0 && -t 1 ]] ||
  {{ echo "PMV4_C_LOCAL=DENIED INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }}

STAGED_TEMP=0
OWNER_APPROVAL_CREATED=0
cleanup() {{
  if [[ "{D}STAGED_TEMP" == "1" && "{D}OWNER_APPROVAL_CREATED" == "0" ]]; then
    sudo /usr/bin/rm -rf -- "{D}STAGE"
  fi
}}
trap cleanup EXIT

sudo /usr/bin/install -d -o root -g root -m 0700 "{D}STAGE"
sudo /usr/bin/install -d -o root -g root -m 0700 "{D}STAGE/src"
sudo /usr/bin/install -d -o root -g root -m 0700 "{D}STAGE/src/tools"
STAGED_TEMP=1
sudo /usr/bin/install -o root -g root -m 0400 "{D}ROOT" "{D}STAGED"
for rel in "{D}{{SUPPORT[@]}}"; do
  sudo /usr/bin/install -o root -g root -m 0400 "{D}ART/src/{D}rel" "{D}STAGE/src/{D}rel"
done
sudo /usr/bin/python3 -I -B "{D}STAGED" --plan "{D}PLAN" --preflight
echo "PMV4_C_PRIVILEGED_ROOT_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_NOT_YET_USED=true; PRODUCTION_MUTATIONS=false"

PYTHONPATH="{D}ART/src:." /usr/bin/python3 -B "{D}OWNER" --plan "{D}PLAN" --authorize
OWNER_APPROVAL_CREATED=1
sudo /usr/bin/python3 -I -B "{D}STAGED" --plan "{D}PLAN" --execute
sudo /usr/bin/python3 -I -B "{D}STAGED" --plan "{D}PLAN" --postflight
echo "PMV4_C_ONE_OWNER_FULL_RELEASE=VERIFIED_POSTFLIGHT"
echo "PMV4_LATER_PHASES_ARE_NOT_AUTHORIZED"
'''

def build(*,candidate:str,image_digest:str)->Path:
    need(os.geteuid()==1000,"C_BUILD_UID1000_REQUIRED")
    source=_worktree_source(candidate)
    main=subprocess.check_output(
        ["/usr/bin/gh","api","repos/al-teamaot-com/jason/branches/main",
         "--jq",".commit.sha"],text=True,timeout=20).strip()
    need(main==candidate,"C_BUILD_PROTECTED_MAIN_CHANGED")
    need(protected_ci.protected_main_ci_verified(candidate),
         "C_BUILD_PROTECTED_MAIN_CI_NOT_GREEN")
    image=json.loads(subprocess.check_output(
        ["/usr/bin/docker","image","inspect",image_digest],
        text=True,timeout=20))
    need(len(image)==1 and image[0].get("Id")==image_digest,
         "C_BUILD_WORKER_IMAGE_NOT_LOCAL")
    labels=(image[0].get("Config") or {}).get("Labels") or {}
    need(labels=={
        "com.aot.jason.component":"pmv4-ticket-core",
        "com.aot.jason.source_revision":candidate,
        "com.aot.jason.provider-mutation":"governed-only",
        "com.aot.jason.production-core":"false",
        "com.aot.jason.lifecycle":"production-candidate",
    },"C_BUILD_WORKER_IMAGE_LABELS_NOT_EXACT")
    runtime=_docker("jason-runtime");mcp=_docker("jason-mcp-pilot")
    need((runtime.get("State") or {}).get("Running") is True
         and (runtime.get("State") or {}).get("Health",{}).get("Status")=="healthy"
         and (mcp.get("State") or {}).get("Running") is True,
         "C_BUILD_PROTECTED_CONTAINERS_NOT_READY")
    runtime_env=_env(runtime)
    service_manifest=service_contract.build_manifest(
        runtime_env,source_sha=candidate,image_digest=image_digest)
    base_policy,candidate_policy=_candidate_policy(source)
    baseline_cycle,baseline_scanned=_latest_scan()
    artifact=ARTIFACTS/("pmv4-c-"+candidate)
    need(not artifact.exists() and not artifact.is_symlink(),
         "C_BUILD_ARTIFACT_ALREADY_EXISTS")
    (artifact/"tools").mkdir(parents=True,mode=0o700)
    (artifact/"src"/"tools").mkdir(parents=True,mode=0o700)
    for directory in (artifact,artifact/"tools",artifact/"src",artifact/"src"/"tools"):
        os.chmod(directory,0o700)
    root_src=source/"tools/pmv4_c_atomic_root.py"
    owner_src=source/"tools/pmv4_c_atomic_owner.py"
    shutil.copy2(root_src,artifact/"tools/pmv4_c_atomic_root.py")
    shutil.copy2(owner_src,artifact/"tools/pmv4_c_atomic_owner.py")
    os.chmod(artifact/"tools/pmv4_c_atomic_root.py",0o400)
    os.chmod(artifact/"tools/pmv4_c_atomic_owner.py",0o400)
    staged={}
    for rel in STAGED_FILES:
        src=source/rel;dst=artifact/"src"/rel
        shutil.copy2(src,dst);os.chmod(dst,0o400)
        staged[rel]=sha(dst.read_bytes())
    db_identities={raw:_metadata(Path(raw)) for raw in DBS}
    provider_state={
        raw:_metadata(Path(raw),directory=True)
        for raw in service_contract.PROVIDER_STATE
    }
    credential_paths=sorted({
        str(m["Source"]) for m in service_manifest["mounts"]
        if str(m["Destination"]).startswith("/run/jason-secrets/")
    })
    plan={
        "schema_version":"1.0","action":ACTION,
        "candidate_sha":candidate,
        "rollback_sha":Path("/opt/jason/current").resolve(strict=True).name,
        "production_lkg_sha":Path("/opt/jason/current").resolve(strict=True).name,
        "worker_image_digest":image_digest,
        "runtime_container_id":runtime["Id"],
        "mcp_container_id":mcp["Id"],
        "runtime_image_digest":runtime["Image"],
        "mcp_image_digest":mcp["Image"],
        "freeze_sha256":sha(FREEZE.read_bytes()),
        "hold_sha256":sha(HOLD.read_bytes()),
        "watchdog_path":str(root_contract.WATCHDOG),
        "watchdog_base_sha256":sha(base_policy),
        "watchdog_candidate_sha256":sha(candidate_policy),
        "service_manifest_sha256":sha(canon(service_manifest)),
        "root_executor_sha256":sha((artifact/"tools/pmv4_c_atomic_root.py").read_bytes()),
        "owner_issuer_sha256":sha((artifact/"tools/pmv4_c_atomic_owner.py").read_bytes()),
        "staged_source_files":staged,
        "db_identities":db_identities,
        "credential_paths":credential_paths,
        "provider_state_metadata":provider_state,
        "runtime_env_overrides":dict(root_contract.RUNTIME_ENV_OVERRIDES),
        "mcp_env_overrides":dict(root_contract.MCP_ENV_OVERRIDES),
        "service_restarts":["jason-runtime","jason-mcp-pilot"],
        "normal_ticket_processing_after_activation":True,
        "two_scan_acceptance":True,
        "owner_consents":1,"standing_authority":False,
        "later_stages_authorized":False,
        "baseline_scan_cycle_id":baseline_cycle,
        "baseline_scanned_at":baseline_scanned,
    }
    plan["scope_sha256"]=sha(canon(plan))
    (artifact/"service-manifest.json").write_bytes(canon(service_manifest))
    (artifact/"production-desired-state.base.json").write_bytes(base_policy)
    (artifact/"production-desired-state.stage-c.json").write_bytes(candidate_policy)
    (artifact/"root-release-plan.json").write_bytes(canon(plan))
    for f in (artifact/"service-manifest.json",
              artifact/"production-desired-state.base.json",
              artifact/"production-desired-state.stage-c.json",
              artifact/"root-release-plan.json"):
        os.chmod(f,0o400)
    lp=artifact/"tools/pmv4_c_one_owner_local.sh"
    lp.write_text(_launcher(
        plan,artifact,plan["root_executor_sha256"],plan["owner_issuer_sha256"]),
        encoding="utf-8")
    os.chmod(lp,0o500)
    evidence={
        "schema_version":"1.0",
        "status":"preproduction_candidate_not_authorized",
        "source_sha":candidate,"image_digest":image_digest,
        "scope_sha256":plan["scope_sha256"],
        "service_manifest_sha256":plan["service_manifest_sha256"],
        "owner_approval_issued":False,"production_mutations":False,
        "service_restarts_performed":False,"ticket_data_moved":False,
        "external_worker_started":False,
    }
    (artifact/"evidence.json").write_bytes(canon(evidence))
    os.chmod(artifact/"evidence.json",0o400)
    print("PMV4_C_IMMUTABLE_RELEASE_PACKET=BUILT")
    print("SOURCE_SHA="+candidate)
    print("WORKER_IMAGE_DIGEST="+image_digest)
    print("SCOPE_SHA256="+plan["scope_sha256"])
    print("OWNER_APPROVAL_ISSUED=false; PRODUCTION_MUTATIONS=false")
    return artifact

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--source-sha",required=True)
    p.add_argument("--image-digest",required=True)
    args=p.parse_args()
    try:
        build(candidate=args.source_sha,image_digest=args.image_digest)
        return 0
    except BaseException as exc:
        code=str(exc)
        if len(code)>180: code="C_BUILD_INTERNAL_DENIED"
        print("PMV4_C_BUILD=DENIED "+type(exc).__name__+":"+code,
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
