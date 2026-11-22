#!/usr/bin/env python3
"""Exact first AOT financial-statement component promotion under signed Owner proof.

Only executed by independently SHA-pinned isolated root Python. Uses the
already installed independent component controller, not raw Compose authority.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ACTION="owner-first-financial-statements-component-release-20261117"
SOURCE="c205bb4ac163e7d433796f2f4839a90c7cc1f56b"
IMAGE="sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195"
ZERO="0"*40
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
CONTROLLER="675b99e73c33c228a8531c2797eb3db53c399ad8"
MANIFEST_SHA="56d7b12c6ee716e522aac66323fe59258256542ba6e6d104182807e3d7ec638e"
SCOPE_SHA="ee36d69187b2b0aabb6ba19521c48adde71af95d5e8621855b590a5c03755f9c"
STAGE=Path("/home/al/.local/share/jason/independent-component-financial-release-c205bb4ac163")
OWNER_PROOF=Path("/home/al/.local/share/jason/financial-component-owner-c205bb4ac163.json")
STAGE_UID=1000
ROOT=Path("/var/lib/jason/independent-component-release")
ROOT_BUNDLE=ROOT/"releases"/SOURCE
TRUST=Path("/opt/jason/independent-component-release/trusted")
ROOT_ENTRY=TRUST/"tools/independent_component_release_root.py"
OUTBOX=Path("/var/lib/jason/openclaw/release-manager/independent-component-owner-approvals")
CI=ROOT/"control/protected-ci.json"
LEDGER=ROOT/"control/financial-first-release-attempt.json"
RESULT=ROOT/"control/financial-first-release-result.json"
PROTECTED_CONTROL=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
PROTECTED_DRIFT=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
OWNER_PUB=Path("/etc/jason-owner-release/verified-owner-public-key.json")
RELEASE_ROOT_PIN="e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324"
RELEASE_CORE_PIN="1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7"
SIGNED_OWNER_PIN="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FILES=("manifest.json","scope.json","compose.yaml","config.json","boundary.sqlite3")
PROTECTED=("jason-runtime","jason-mcp-pilot","jason-pmv4-shadow-gateway",
           "jason-teams-gateway","openbao")
REQUIRED_CHECKS=frozenset({
 "GitGuardian Security Checks","validate-provider-secret-provisioning",
 "cap-003","system-registry","documentation","validate-kfs-foundation",
 "cap-007","runtime-service","repository-hygiene",
 "governed-security-regressions","cap-001","unit-tests",
 "governed-provider-reads","constant-contact-source",
 "conversation-experience","reflect-001","teams-gateway",
 "autotask-mutation-foundation",
})

class Denied(PermissionError):
    pass

def need(ok, msg):
    if not ok: raise Denied(msg)

def digest(raw):return sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=False).encode()

def exact_stage():
    d=STAGE
    need(not d.is_symlink() and d.is_dir() and d.lstat().st_uid==STAGE_UID
         and stat.S_IMODE(d.lstat().st_mode)==0o700,
         "FINANCIAL_STAGING_ROOT_UNTRUSTED")
    need({p.name for p in d.iterdir()}==set(FILES),"FINANCIAL_STAGING_FILE_SET")
    data={}
    for name in FILES:
        p=d/name
        x=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(x.st_mode)
             and x.st_uid==STAGE_UID and x.st_nlink==1
             and stat.S_IMODE(x.st_mode)==0o400,
             "FINANCIAL_STAGING_FILE_UNTRUSTED")
        data[name]=p.read_bytes()
    manifest=json.loads(data["manifest.json"])
    need(manifest.get("candidate_sha")==SOURCE
         and manifest.get("rollback_sha")==ZERO
         and manifest.get("image_digest")==IMAGE
         and manifest.get("scope_sha256")==SCOPE_SHA
         and manifest.get("freeze_sha256")==FREEZE_SHA
         and manifest.get("component_id")=="financial-statements"
         and digest(canonical(manifest))==MANIFEST_SHA,
         "FINANCIAL_MANIFEST_NOT_REVIEWED")
    need(digest(data["compose.yaml"])==manifest["compose_sha256"]
         and digest(data["config.json"])==manifest["config_sha256"]
         and digest(data["boundary.sqlite3"])==manifest["boundary_sha256"],
         "FINANCIAL_STAGED_SOURCE_DIGEST_DRIFT")
    cfg=json.loads(data["config.json"])
    need(cfg.get("enabled") is True
         and cfg.get("run_hour")==5
         and cfg.get("timezone")=="America/New_York"
         and cfg.get("root_path")=="Bank Checking Accounts Register"
         and cfg.get("tenant_id")==manifest["provider_scope"]["tenant_id"]
         and cfg.get("drive_id")=="b!v9dMj7hyfk-YA8R6vLsjLySnt-Wb3GtArtgpYfH3EVNo8p5rPdImQ5Z7APH0M9tF",
         "FINANCIAL_STAGED_CONFIG_NOT_APPROVED")
    scope=json.loads(data["scope.json"])
    need(digest(canonical(scope))==SCOPE_SHA, "FINANCIAL_SCOPE_DIGEST_CHANGED")
    return manifest, data

def root_module(relative, checksum, name):
    path=TRUST/relative
    info=path.lstat()
    need(info.st_uid==0 and stat.S_ISREG(info.st_mode)
         and not path.is_symlink() and info.st_mode&0o222==0
         and digest(path.read_bytes())==checksum,
         "INSTALLED_TRUSTED_COMPONENT_CODE_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "INSTALLED_COMPONENT_CODE_MISSING")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def validate_with_installed_core(manifest,data):
    entry=ROOT_ENTRY.lstat()
    need(entry.st_uid==0 and stat.S_ISREG(entry.st_mode)
         and not ROOT_ENTRY.is_symlink()
         and entry.st_mode & 0o222==0
         and digest(ROOT_ENTRY.read_bytes())==RELEASE_ROOT_PIN,
         "INSTALLED_ROOT_ENTRYPOINT_NOT_PINNED")
    # Load the pinned core as the installed trusted tools package. No worktrees.
    sys.path.insert(0,str(TRUST))
    from tools import independent_component_release as core
    need(digest(Path(core.__file__).read_bytes())==RELEASE_CORE_PIN
         and Path(core.__file__).resolve()==TRUST/"tools/independent_component_release.py",
         "TRUSTED_CONTROLLER_IMPORT_CHANGED")
    core.validate_manifest(manifest)
    core.validate_scope(manifest,json.loads(data["scope.json"]))
    core.validate_compose(data["compose.yaml"],manifest)
    core.validate_boundary_snapshot(STAGE/"boundary.sqlite3",manifest)

def owner_signature(manifest):
    p=OWNER_PROOF
    x=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(x.st_mode)
         and x.st_uid==STAGE_UID and x.st_nlink==1
         and stat.S_IMODE(x.st_mode)==0o400 and x.st_size<32768,
         "FINANCIAL_OWNER_PROOF_UNTRUSTED")
    wrapper=json.loads(p.read_bytes())
    need(set(wrapper)=={"schema_version","action","manifest_sha256","signed_owner_proof"}
         and wrapper["schema_version"]=="1.0"
         and wrapper["action"]==ACTION
         and wrapper["manifest_sha256"]==MANIFEST_SHA,
         "FINANCIAL_OWNER_ACTION_NOT_EXACT")
    mod=root_module("implementation/kernel/signed_owner_release.py",
                    SIGNED_OWNER_PIN,"component_owner_verifier")
    key=mod.read_pinned_root_owner_public_key(OWNER_PUB)
    decision=mod.verify_exact_owner_release(
        wrapper["signed_owner_proof"],public_key=key,
        expected_release_id="release-"+SOURCE[:16],
        expected_candidate_sha=SOURCE,expected_rollback_sha=ZERO,
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=MANIFEST_SHA,
        expected_freeze_sha256=FREEZE_SHA,
        at=datetime.now(timezone.utc))
    return wrapper["signed_owner_proof"],decision["approval_id"]

def docker_inspect(name):
    value=json.loads(subprocess.check_output(
        ["/usr/bin/docker","inspect",name],timeout=15,text=True))[0]
    return (value["Id"],value["Image"],value["State"]["StartedAt"],
            value["State"]["Running"])

def protected_state():
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "LIVE_PRODUCTION_SHA_CHANGED")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA,"FINANCIAL_FREEZE_CHANGED")
    control=json.loads(PROTECTED_CONTROL.read_bytes())
    drift=json.loads(PROTECTED_DRIFT.read_bytes())
    need(control.get("circuit_breaker",{}).get("state")=="closed"
         and (control.get("last_known_good",{}).get("manifest",{})
              .get("revision"))==LKG,
         "FINANCIAL_BREAKER_OR_LKG_CHANGED")
    need(drift.get("status")=="pass" and drift.get("problems")==[],
         "FINANCIAL_PRODUCTION_DRIFT_CHANGED")
    before={name:docker_inspect(name) for name in PROTECTED}
    need(all(x[3] for x in before.values()),
         "FINANCIAL_PROTECTED_SERVICE_NOT_RUNNING")
    need(before["jason-mcp-pilot"][1]==
         "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477",
         "FINANCIAL_MCP_IMAGE_CHANGED")
    return before

def gh_api(endpoint, projection):
    # Authenticated GitHub via the existing *unprivileged* Owner's gh client.
    # Root never copies a user's OAuth token into a service, release or bundle.
    if os.geteuid()==0:
        cmd=["/usr/sbin/runuser","-u","al","--","/usr/bin/env",
             "HOME=/home/al","XDG_CONFIG_HOME=/home/al/.config",
             "/usr/bin/gh","api","--method","GET",endpoint,"--jq",projection]
    else:
        need(os.geteuid()==1000,"GITHUB_ATTESTOR_UID_NOT_TRUSTED")
        cmd=["/usr/bin/gh","api","--method","GET",endpoint,"--jq",projection]
    value=subprocess.run(cmd,capture_output=True,text=True,
                         check=False,timeout=60)
    need(value.returncode==0 and len(value.stdout)<800000,
         "GITHUB_PROTECTED_SOURCE_ATTESTATION_UNAVAILABLE")
    return json.loads(value.stdout)

def verified_ci():
    comparison=gh_api(
        "repos/al-teamaot-com/jason/compare/"+SOURCE+"...main",
        "{status,merge_base_sha:.merge_base_commit.sha,head:.commits[-1].sha}")
    need(comparison.get("status") in ("ahead","identical")
         and comparison.get("merge_base_sha")==SOURCE,
         "FINANCIAL_SOURCE_NOT_IN_PROTECTED_MAIN")
    result=gh_api(
        "repos/al-teamaot-com/jason/commits/"+SOURCE+"/check-runs?per_page=100",
        "{total_count,checks:[.check_runs[]|{name,status,conclusion}]}")
    checks=result.get("checks")
    need(isinstance(checks,list)
         and result.get("total_count")==len(checks)
         and 20<=len(checks)<=100
         and all(x.get("status")=="completed"
                 and x.get("conclusion")=="success" for x in checks),
         "FINANCIAL_CI_NOT_ALL_PASS")
    present={x.get("name") for x in checks}
    need(REQUIRED_CHECKS.issubset(present),
         "FINANCIAL_REQUIRED_CHECKS_MISSING")
    return {
        "candidate_sha":SOURCE,
        "protected_main_ancestor":True,
        "required_ci_passed":True,
        "verified_at":datetime.now(timezone.utc).isoformat(),
        "check_count":len(checks),
        "required_checks":sorted(REQUIRED_CHECKS),
        "protected_main":comparison.get("head") or SOURCE,
    }

def root_file(path,blob,mode,uid=0):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),mode)
    with os.fdopen(fd,"wb") as out:
        if uid: os.fchown(out.fileno(),uid,uid)
        out.write(blob)
        out.flush()
        os.fsync(out.fileno())
    need(digest(path.read_bytes())==digest(blob),
         "FINANCIAL_ROOT_READBACK_MISMATCH")

def root_json(path,payload,mode,uid=0):
    root_file(path,json.dumps(payload,sort_keys=True,indent=2).encode()+b"\n",
              mode,uid)

def acceptance_status():
    p=Path("/home/al/.local/share/jason/sharepoint-write-provisioning/"
           "read-only-acceptance-c205bb4a-20261117.json")
    x=p.lstat()
    need(x.st_uid==1000 and stat.S_ISREG(x.st_mode)
         and not p.is_symlink() and x.st_size<8192,
         "FINANCIAL_PROVIDER_PREFLIGHT_UNAVAILABLE")
    a=json.loads(p.read_bytes())
    need(a.get("status")=="read_verified"
         and a.get("source_revision")==SOURCE
         and a.get("immutable_image_id")==IMAGE
         and a.get("tenant_id")=="f7054323-d52b-4863-8c2f-1898f0b6077c"
         and a.get("application_id")=="3d362478-a873-4ba2-b8a5-c04e66ef2f32"
         and a.get("root_path")=="Bank Checking Accounts Register"
         and a.get("provider_mutations")==0
         and a.get("children",0)>0,
         "FINANCIAL_PROVIDER_PREFLIGHT_NOT_MATCHED")
    t=datetime.fromisoformat(a["timestamp_utc"])
    need(t.tzinfo is not None
         and 0<=(datetime.now(timezone.utc)-t).total_seconds()<=86400,
         "FINANCIAL_PROVIDER_READBACK_TOO_OLD")

def verify_image():
    x=json.loads(subprocess.check_output([
        "/usr/bin/docker","image","inspect",IMAGE],text=True,timeout=20))[0]
    need(x.get("Id")==IMAGE
         and (x.get("Config",{}).get("Labels",{})
              .get("com.aot.jason.source_revision"))==SOURCE,
         "FINANCIAL_COMPONENT_IMAGE_NOT_PINNED")

def verify_secret_paths():
    for name in ("role-id","secret-id"):
        p=Path("/var/lib/jason/runtime-secrets/openbao/"
               "microsoft-sharepoint-write-approle")/name
        x=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(x.st_mode)
             and x.st_uid==0 and x.st_gid==1000
             and stat.S_IMODE(x.st_mode)==0o640
             and 8<x.st_size<256,
             "DEDICATED_SHAREPOINT_WRITER_APPROLE_MISSING")

def receipt_baseline():
    return {name:docker_inspect(name) for name in PROTECTED}

def run_native(command,*args,timeout=300):
    x=subprocess.run(["/usr/bin/python3","-I",str(ROOT_ENTRY),command,*args],
                     capture_output=True,text=True,timeout=timeout)
    # Don't log arbitrary tool error body, may contain provider metadata.
    need(x.returncode==0,"NATIVE_COMPONENT_RELEASE_DENIED")
    return x.stdout.strip()

def execute():
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "EXACT_PINNED_ROOT_EXECUTION_REQUIRED")
    # Verify all admission conditions before creating production root files.
    m,files=exact_stage()
    validate_with_installed_core(m,files)
    signed,approval_id=owner_signature(m)
    need(not ROOT_BUNDLE.exists() and not ROOT_BUNDLE.is_symlink()
         and not CI.exists() and not CI.is_symlink()
         and not LEDGER.exists() and not LEDGER.is_symlink()
         and not RESULT.exists() and not RESULT.is_symlink()
         and not (OUTBOX/("release-"+SOURCE[:16]+".json")).exists(),
         "FINANCIAL_FIRST_RELEASE_ALREADY_STAGED_OR_ATTEMPTED")
    need(ROOT_BUNDLE.parent.is_dir() and OUTBOX.is_dir(),
         "INDEPENDENT_COMPONENT_CONTROLLER_NOT_READY")
    need(Path("/var/lib/jason/financial-statements").is_dir(),
         "FINANCIAL_COMPONENT_STATE_UNPROVISIONED")
    verify_secret_paths()
    verify_image()
    acceptance_status()
    baseline=protected_state()
    ci=verified_ci()
    # One-use record precedes any staging or production service activation.
    attempt={
        "schema_version":"1.0","action":ACTION,
        "candidate_sha":SOURCE,"component_id":"financial-statements",
        "approval_id":approval_id,"manifest_sha256":MANIFEST_SHA,
        "scope_sha256":SCOPE_SHA,"state":"started",
        "root_stage_ready":False,"component_accepted":False,
        "started_at":datetime.now(timezone.utc).isoformat(),
    }
    root_json(LEDGER,attempt,0o600)
    result=dict(attempt)
    try:
        ROOT_BUNDLE.mkdir(mode=0o700)
        for name in FILES:
            root_file(ROOT_BUNDLE/name,files[name],0o444)
        # Root-controlled CI evidence is generated only from live protected
        # source ancestry and all successful GitHub check runs.
        root_json(CI,ci,0o444)
        approval={
            "schema_version":"1.0",
            "component_id":"financial-statements",
            "image_digest":IMAGE,
            "release_id":"release-"+SOURCE[:16],
            "candidate_sha":SOURCE,
            "approved_by":signed["payload"]["owner_principal"],
            "organization_id":"aot",
            "source":"authenticated_entra_owner:"+approval_id,
            "reason":"exact first 05:00 AOT statements organizer release",
            "signed_owner_proof":signed,
        }
        root_json(OUTBOX/("release-"+SOURCE[:16]+".json"),approval,0o600,1000)
        result["root_stage_ready"]=True
        # The installed controller independently rechecks protected locks,
        # immutable release files, CI freshness, image and Owner signature.
        native_result=run_native("promote","--candidate-sha",SOURCE)
        accepted=json.loads(native_result)
        need(accepted.get("status")=="component_accepted"
             and accepted.get("candidate_sha")==SOURCE
             and accepted.get("component_id")=="financial-statements"
             and accepted.get("protected_services_changed") is False,
             "NATIVE_FINANCIAL_ACCEPTANCE_NOT_VERIFIED")
        # Inspect by project label through the root installed adapter contract.
        running=subprocess.check_output([
            "/usr/bin/docker","ps","--filter",
            "label=com.docker.compose.project=jason-financial-statements",
            "--format","{{.ID}}"],text=True,timeout=15).splitlines()
        need(len(running)==1,"FINANCIAL_ONLY_ONE_SERVICE_NOT_RUNNING")
        inspect=json.loads(subprocess.check_output([
            "/usr/bin/docker","inspect",running[0]],
            text=True,timeout=20))[0]
        need(inspect["State"]["Running"]
             and inspect["Image"]==IMAGE
             and inspect["Config"]["Labels"].get(
             "com.docker.compose.project")=="jason-financial-statements",
             "FINANCIAL_SCHEDULER_CONTAINER_INVALID")
        after=receipt_baseline()
        need(after==baseline and digest(FREEZE.read_bytes())==FREEZE_SHA,
             "PROTECTED_SERVICES_OR_FREEZE_CHANGED")
        active=ROOT/"active/financial-statements.json"
        target=json.loads(active.read_bytes())
        need(target.get("candidate_sha")==SOURCE,
             "FINANCIAL_ACTIVE_POINTER_NOT_ACCEPTED")
        result["component_accepted"]=True
        result["state"]="accepted_pending_05am_readback"
        result["container_image"]=IMAGE
        result["container_id"]=inspect["Id"]
        result["protected_services_unchanged"]=True
        result["finished_at"]=datetime.now(timezone.utc).isoformat()
    except BaseException:
        result["state"]="failed_closed"
        result["finished_at"]=datetime.now(timezone.utc).isoformat()
        raise
    finally:
        root_json(RESULT,result,0o600)
    print("FINANCIAL_COMPONENT_INDEPENDENT_RELEASE=ACCEPTED")
    print("PROTECTED_RUNTIME_MCP_PMV4_UNCHANGED=True")
    print("PRODUCTION_FREEZE_UNCHANGED=True")
    print("SCHEDULE_05AM_EASTERN=CONFIGURED")
    print("REAL_05AM_PROVIDER_RUN=NOT_YET_VERIFIED")

def main():
    import argparse
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight",action="store_true")
    mode.add_argument("--execute",action="store_true")
    args=p.parse_args()
    if args.preflight:
        manifest,files=exact_stage()
        need(manifest.get("candidate_sha")==SOURCE
             and digest(files["config.json"])==manifest["config_sha256"],
             "FINANCIAL_SOURCE_PREFLIGHT_FAIL")
        print("FINANCIAL_SOURCE_BYTES_AND_SCOPE=PASS")
        print("OWNER_SIGNATURE_AND_ROOT_GATES=NOT_EXECUTED")
    else:execute()

if __name__=="__main__":
    try:main()
    except (Denied,OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print("FINANCIAL_ONEUSE_ROOT_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:140] if isinstance(exc,Denied) else ""),
              file=sys.stderr)
        raise SystemExit(2)
