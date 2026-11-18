#!/usr/bin/env python3
"""One exact authenticated AOT Stage E generic canary acceptance + cleanup.

Source-only until GitHub protected CI has approved and the immutable Git blobs
are staged. Root actions require a fresh exact authenticated Owner proof and
the original release/freeze/host gates. No PMv3 unit or provider change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

ACTION="pmv4-e-oneowner-providerfree-native-canary-and-cleanup-v1"
CANDIDATE="d85faad76881439953527d391c314df0f5d2967a"
IMAGE="sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd"
IMAGE_SOURCE="75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
MANIFEST_SHA="92472001a64ecdd3d9c53d321b544aa7d10bdcf27f5dd2ad8b72b97bca6d2924"
SCOPE_SHA="b9107ef85af95fe20ecd40523006e561c90d06585835d63a9970719bbd03f4c6"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
POLICY_SHA="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
CONTROLLER_SHA="1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7"
ADAPTER_SHA="36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce"
ROOT_ENTRY_SHA="e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324"
SIGNED_OWNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
SOURCE_STAGE=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-canary-"+CANDIDATE)
ARTIFACT_PARENT=Path("/srv/jason/archive/engineering-artifacts")
REPO=Path("/home/al/.local/lib/jason/engineering-source-repo")
ROOT=Path("/var/lib/jason/independent-component-release")
ROOT_BUNDLE=ROOT/"releases"/CANDIDATE
TRUST=Path("/opt/jason/independent-component-release/trusted")
OUTBOX=Path("/var/lib/jason/openclaw/release-manager/independent-component-owner-approvals")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/protected-readback")
SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
PUB=Path("/etc/jason-owner-release/verified-owner-public-key.json")
RECEIPT=ROOT/"control"/("pmv4-e-canary-"+CANDIDATE+"-transaction.json")
BACKUP=ROOT/"control"/("pmv4-e-canary-"+CANDIDATE+"-original-policy.json")
CI=ROOT/"control/protected-ci.json"
BUNDLE_FILES=("manifest.json","scope.json","compose.yaml","config.json")
TRUST_NEW=(
    "tools/pmv4_e_canary_contract.py",
    "tools/pmv4_e_canary_host.py",
    "tools/pmv4_e_canary_release_root.py",
)
RECEIPT_ID="owner-mcp"


class Denied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:raise Denied("PMV4_E_"+reason)


def digest(data:bytes)->str:
    return sha256(data).hexdigest()


def canonical(doc:dict)->bytes:
    return json.dumps(doc,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def stage_dir(build_sha:str)->Path:
    need(isinstance(build_sha,str) and len(build_sha)==40
         and all(k in "0123456789abcdef" for k in build_sha),
         "REVIEWED_BUILD_SHA_INVALID")
    return ARTIFACT_PARENT/("pmv4-e-canary-once-"+build_sha)


def root_script(build_sha:str)->Path:
    return stage_dir(build_sha)/"tools/pmv4_e_canary_oneowner_root.py"


def git_file(sha:str,name:str)->bytes:
    need(name in set(TRUST_NEW)|{
        "tools/pmv4_e_canary_oneowner_root.py",
        "tools/pmv4_e_canary_oneowner_owner.py",
        "tools/pmv4_e_root_receipt_readback.py",
        "tools/pmv4_e_canary_drift_policy.py",
        "tools/pmv4_e_canary_oneowner_local.sh",
    }, "UNAPPROVED_GIT_SOURCE")
    # Root must not trust its ambient Git safe.directory or alter Git
    # configuration. Read the immutable git blob through the repository's
    # unprivileged owner, whose identity owns the review worktree.
    git=["/usr/bin/git","-C",str(REPO),"show",sha+":"+name]
    if os.geteuid()==0:
        git=["/usr/sbin/runuser","-u","al","--",*git]
    else:
        need(os.geteuid()==1000,"UNPRIVILEGED_GIT_READER_NOT_OWNER")
    p=subprocess.run(git,capture_output=True,timeout=25)
    need(p.returncode==0 and 0<len(p.stdout)<200_000,
         "REVIEWED_GIT_BLOB_MISSING")
    return p.stdout


def source_bytes(build_sha:str,relative:str)->bytes:
    root=stage_dir(build_sha)
    need(root.is_dir() and not root.is_symlink(),"REVIEWED_STAGE_MISSING")
    p=root/relative
    x=p.lstat()
    need(stat.S_ISREG(x.st_mode) and not p.is_symlink()
         and x.st_uid==1000 and x.st_nlink==1
         and stat.S_IMODE(x.st_mode)==0o400
         and 0<x.st_size<200_000,"STAGE_FILE_NOT_IMMUTABLE")
    data=p.read_bytes()
    need(len(data)==x.st_size
         and data==git_file(build_sha,relative),
         "STAGED_SOURCE_NOT_REVIEWED_GIT")
    return data


def stage_bytes(name:str)->bytes:
    p=SOURCE_STAGE/name
    x=p.lstat()
    need(stat.S_ISREG(x.st_mode) and not p.is_symlink()
         and x.st_uid==1000 and x.st_nlink==1
         and stat.S_IMODE(x.st_mode)==0o400
         and 0<x.st_size<150_000,
         "SOURCE_PACKET_FILE_UNTRUSTED")
    return p.read_bytes()


def candidate_packet()->tuple[dict,dict,dict[str,bytes]]:
    need(SOURCE_STAGE.is_dir() and not SOURCE_STAGE.is_symlink()
         and SOURCE_STAGE.lstat().st_uid==1000
         and (stat.S_IMODE(SOURCE_STAGE.lstat().st_mode)&0o777)==0o700
         and {p.name for p in SOURCE_STAGE.iterdir()}==
             {"manifest.json","scope.json","compose.yaml",
              "config.json","source-evidence.json"},
         "SOURCE_PACKET_NOT_IMMUTABLE")
    data={name:stage_bytes(name) for name in BUNDLE_FILES}
    manifest=json.loads(data["manifest.json"])
    scope=json.loads(data["scope.json"])
    evidence=json.loads(stage_bytes("source-evidence.json"))
    need(manifest.get("candidate_sha")==CANDIDATE
         and manifest.get("rollback_sha")=="0"*40
         and manifest.get("image_digest")==IMAGE
         and manifest.get("component_id")=="pmv4-e-canary"
         and manifest.get("provider_scope",{}).get("provider")=="none"
         and manifest.get("scope_sha256")==SCOPE_SHA
         and manifest.get("freeze_sha256")==FREEZE_SHA
         and digest(canonical(manifest))==MANIFEST_SHA
         and digest(canonical(scope))==SCOPE_SHA
         and digest(data["compose.yaml"])==manifest.get("compose_sha256")
         and digest(data["config.json"])==manifest.get("config_sha256")
         and evidence.get("candidate_sha")==CANDIDATE
         and evidence.get("scope_sha256")==SCOPE_SHA
         and evidence.get("manifest_sha256")==MANIFEST_SHA
         and evidence.get("root_installed") is False
         and evidence.get("owner_proof_issued") is False
         and evidence.get("production_mutations") is False,
         "CANDIDATE_MANIFEST_OR_SCOPE_NOT_EXACT")
    return manifest,scope,data


def gh_api(endpoint:str,query:str)->dict:
    if os.geteuid()==0:
        cmd=["/usr/sbin/runuser","-u","al","--","/usr/bin/env",
             "HOME=/home/al","XDG_CONFIG_HOME=/home/al/.config",
             "/usr/bin/gh","api","--method","GET",endpoint,
             "--jq",query]
    else:
        need(os.geteuid()==1000,"GITHUB_IDENTITY_MUST_BE_LOCAL_OWNER")
        cmd=["/usr/bin/gh","api","--method","GET",endpoint,"--jq",query]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=70)
    need(p.returncode==0 and len(p.stdout)<750_000,"GITHUB_ATTESTATION_UNAVAILABLE")
    return json.loads(p.stdout)


def verify_ci(sha:str)->dict:
    """Live GitHub protected main + native REQUIRED checks, not noisy totals.

    Nonrequired workflow-routing jobs may be intentionally skipped. Neither
    an arbitrary green status nor an unprotected branch can authorize root.
    """
    from datetime import timedelta
    main=gh_api("repos/al-teamaot-com/jason/branches/main",
                "{sha:.commit.sha,name:.name,protected:.protected}")
    head=main.get("sha")
    need(main.get("name")=="main"
         and main.get("protected") is True
         and isinstance(head,str) and len(head)==40,
         "CURRENT_PROTECTED_MAIN_UNVERIFIED")
    comparison=gh_api(
        "repos/al-teamaot-com/jason/compare/"+sha+"..."+head,
        "{status,merge_base_sha:.merge_base_commit.sha}")
    need(comparison.get("status") in ("ahead","identical")
         and comparison.get("merge_base_sha")==sha,
         "REVIEWED_SOURCE_NOT_PROTECTED_MAIN_ANCESTOR")
    policy=gh_api(
        "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks",
        "{strict,checks}")
    checks=policy.get("checks")
    need(policy.get("strict") is True and isinstance(checks,list)
         and 8<=len(checks)<=60,
         "NATIVE_PROTECTED_REQUIRED_STATUS_POLICY_UNAVAILABLE")
    expected={}
    for record in checks:
        need(isinstance(record,dict)
             and isinstance(record.get("context"),str)
             and isinstance(record.get("app_id"),int)
             and record["app_id"]==15368
             and record["context"] not in expected,
             "PROTECTED_REQUIRED_STATUS_APP_UNTRUSTED")
        expected[record["context"]]=record["app_id"]
    baseline={
        "cap-001","cap-003","cap-007","system-registry",
        "runtime-service","repository-hygiene",
        "conversation-experience","teams-gateway",
    }
    need(baseline.issubset(expected),
         "PROTECTED_REQUIRED_STATUS_BASELINE_MISSING")
    now=datetime.now(timezone.utc)
    oldest=now-(timedelta(hours=24) if sha==head else timedelta(days=7))
    # One trusted check-suite fetch instead of eight independent API calls;
    # the exact required contexts/app IDs are still validated individually.
    checked=gh_api(
        "repos/al-teamaot-com/jason/commits/"+sha+
        "/check-runs?per_page=100",
        "{count:.total_count,rows:[.check_runs[]|"
        "{name:.name,sha:.head_sha,status:.status,"
        "conclusion:.conclusion,app:.app.id,at:.completed_at}]}")
    rows=checked.get("rows")
    need(isinstance(rows,list) and 8<=len(rows)<=100
         and checked.get("count")==len(rows),
         "REQUIRED_CHECK_SUITE_UNAVAILABLE")
    for name,app_id in sorted(expected.items()):
        matching=[r for r in rows if r.get("name")==name]
        need(len(matching)==1,"REQUIRED_CHECK_RUN_MISSING_OR_AMBIGUOUS")
        row=matching[0]
        need(row.get("sha")==sha
             and row.get("app")==app_id
             and row.get("status")=="completed"
             and row.get("conclusion")=="success"
             and isinstance(row.get("at"),str),
             "NATIVE_REQUIRED_CHECK_NOT_SUCCESSFUL")
        at=datetime.fromisoformat(row["at"].replace("Z","+00:00"))
        need(at.tzinfo is not None and oldest<=at<=now,
             "NATIVE_REQUIRED_CHECK_STALE")
    workflow=gh_api(
        "repos/al-teamaot-com/jason/actions/runs?head_sha="+sha+
        "&event=push&per_page=100",
        "{total:.total_count,rows:[.workflow_runs[]|"
        "{name:.name,sha:.head_sha,branch:.head_branch,event:.event,"
        "status:.status,conclusion:.conclusion,at:.updated_at}]}")
    rows=workflow.get("rows")
    need(isinstance(rows,list) and len(rows)<=100
         and workflow.get("total")==len(rows),
         "REQUIRED_PROTECTED_WORKFLOW_RUNS_INVALID")
    required={
        "Validate Jason","SEC-007 Security Regressions",
        "Validate Jason Teams Gateway",
        "Validate Conversation Experience Foundation",
    }
    found=set()
    for item in rows:
        name=item.get("name")
        if name not in required:continue
        need(item.get("sha")==sha and item.get("branch")=="main"
             and item.get("event")=="push"
             and item.get("status")=="completed"
             and item.get("conclusion")=="success"
             and isinstance(item.get("at"),str),
             "REQUIRED_PROTECTED_WORKFLOW_NOT_SUCCESSFUL")
        at=datetime.fromisoformat(item["at"].replace("Z","+00:00"))
        need(at.tzinfo is not None and oldest<=at<=now,
             "REQUIRED_PROTECTED_WORKFLOW_STALE")
        found.add(name)
    need(found==required,"REQUIRED_PROTECTED_WORKFLOW_MISSING")
    return {
        "candidate_sha":sha,
        "protected_main_ancestor":True,
        "required_ci_passed":True,
        "verified_at":now.isoformat(),
        "required_checks":sorted(expected),
        "required_workflows":sorted(required),
        "check_count":len(expected),
        "protected_main":head,
    }


def protected_status()->dict[str,tuple]:
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "LKG_CHANGED")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA,"PRODUCTION_FREEZE_CHANGED")
    control=json.loads((CONTROL/"production-control-state.json").read_bytes())
    drift=json.loads((CONTROL/"production-drift.json").read_bytes())
    need(control.get("circuit_breaker",{}).get("state")=="closed"
         and drift.get("status")=="pass" and drift.get("problems")==[],
         "PRODUCTION_DRIFT_OR_BREAKER_CHANGED")
    protected=("jason-runtime","jason-pmv4-ticket-core",
               "jason-mcp-pilot","jason-pmv4-shadow-gateway",
               "jason-teams-gateway","openbao")
    result={}
    for name in protected:
        x=json.loads(subprocess.check_output(
            ["/usr/bin/docker","inspect",name],text=True,timeout=18))[0]
        state=x.get("State") or {}
        need(state.get("Running") is True and
             (state.get("Health") or {}).get("Status") in
             ("healthy",None),
             "PROTECTED_CONTAINER_NOT_HEALTHY")
        result[name]=(x["Id"],x["Image"],state["StartedAt"])
    need(Path("/var/lib/jason/pmv4-shadow/current").readlink()==Path(
        "releases/9859463e5255ecf7040de21d73e9f4062b46a18e"),
        "A1_SHADOW_RELEASE_CHANGED")
    return result


def exact_modules(build_sha:str)->None:
    root=stage_dir(build_sha)
    items={"tools/pmv4_e_canary_oneowner_root.py",
           "tools/pmv4_e_canary_oneowner_owner.py",
           "tools/pmv4_e_canary_drift_policy.py",
           "tools/pmv4_e_root_receipt_readback.py",
           "tools/pmv4_e_canary_oneowner_local.sh",*TRUST_NEW}
    present={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    need(present==items or present==(items|{"owner-proof.json"}),
         "BUILD_PACKET_FILE_SET_MISMATCH")
    for name in items:
        source_bytes(build_sha,name)
    need(root_script(build_sha).read_bytes()==Path(__file__).read_bytes(),
         "RUNNING_ROOT_CODE_NOT_PINNED")


def verify_installed_generic_controller()->list[dict[str,Any]]:
    """Evidence for each exact preinstalled root file, with no bypass.

    This is diagnostic evidence, not a user-controlled trust source. All
    existing fixed SHA-256, root UID, regular-file and no-write gates remain.
    """
    records=[]
    for relative,expected in (
        ("tools/independent_component_release.py",CONTROLLER_SHA),
        ("tools/independent_component_host_adapter.py",ADAPTER_SHA),
        ("tools/independent_component_release_root.py",ROOT_ENTRY_SHA),
    ):
        p=TRUST/relative
        try:
            meta=p.lstat()
            checks={
                "regular_file":bool(stat.S_ISREG(meta.st_mode)),
                "uid_zero":meta.st_uid==0,
                "not_symlink":not p.is_symlink(),
                "no_write_bits":meta.st_mode&0o222==0,
            }
            # Do not read from a symlink, nonroot or mutable path even for
            # diagnostics. This preserves the original guard's short circuit.
            observed=digest(p.read_bytes()) if all(checks.values()) else None
            checks["exact_sha256"]=observed==expected
            item={
                "path":relative,
                "mode":format(stat.S_IMODE(meta.st_mode),"04o"),
                "uid":meta.st_uid,
                "expected_sha256":expected,
                "actual_sha256":observed,
                "checks":checks,
            }
        except OSError as exc:
            print("PMV4_E_GENERIC_ROOT_FILE_READ_DENIED="+relative,
                  flush=True)
            raise Denied("PMV4_E_INSTALLED_GENERIC_CONTROLLER_UNREADABLE") from exc
        records.append(item)
        # Always print before denying to identify the precise failed field.
        # No trust decision is made from this printed report.
        print("PMV4_E_GENERIC_ROOT_FILE="+json.dumps(item,sort_keys=True),
              flush=True)
        need(all(checks.values()),
             "INSTALLED_GENERIC_CONTROLLER_DRIFT:"+relative)
    return records


def preflight(build_sha:str,*,strict_root:bool)->dict:
    if strict_root:
        need(os.geteuid()==0 and sys.flags.isolated==1,
             "ROOT_ISOLATED_EXECUTION_REQUIRED")
    else:
        need(os.geteuid()==1000,"OWNER_USER_SOURCE_CHECK_REQUIRED")
    exact_modules(build_sha)
    manifest,scope,files=candidate_packet()
    verify_ci(build_sha)
    verify_ci(CANDIDATE)
    need(digest(FREEZE.read_bytes())==FREEZE_SHA,
         "FREEZE_CHANGED")
    if strict_root:
        need(digest(POLICY.read_bytes())==POLICY_SHA,
             "PROTECTED_POLICY_CHANGED")
        need(not ROOT_BUNDLE.exists()
             and not RECEIPT.exists() and not BACKUP.exists()
             and not (OUTBOX/("release-"+CANDIDATE[:16]+".json")).exists(),
             "ONEUSE_ROOT_ALREADY_ATTEMPTED")
        # Existing controller exact trusted installed source; NOT modified.
        verify_installed_generic_controller()
        need(CI.is_file() is False,"COMPONENT_CI_ALREADY_CONFLICTING")
        need(OUTBOX.is_dir(),"CANARY_APPROVAL_OUTBOX_MISSING")
        need(not subprocess.run(["/usr/bin/docker","ps","-aq",
            "--filter","label=com.docker.compose.project=jason-pmv4-e-canary"],
            capture_output=True,text=True,timeout=12).stdout.strip(),
             "CANARY_PROJECT_NOT_EMPTY")
        current=protected_status()
        need(bool(current),"PROTECTED_SERVICES_UNAVAILABLE")
        # Exact C/D/A1 immutable receipts are verified independently
        # before exposing any new production release surface.
        helper_source=source_bytes(build_sha,
                                   "tools/pmv4_e_root_receipt_readback.py")
        import types
        module=types.ModuleType("pmv4_e_receipt")
        # Compile exact SHA-verified source without creating privileged
        # temporary executable files or importing an ambient worktree.
        exec(compile(helper_source,"reviewed-root-receipt","exec"),
             module.__dict__)
        reading=module.inspect()
        need(reading.get("status")=="pre_retirement_root_acceptance_verified",
             "PROTECTED_C_D_A1_NOT_ACCEPTED")
    return {"status":"preflight_pass",
            "action":ACTION,"source_sha":CANDIDATE,
            "build_sha":build_sha,
            "manifest_sha256":MANIFEST_SHA,"scope_sha256":SCOPE_SHA,
            "owner_approval_used":False,"production_mutations":False}


def installed_signer():
    p=TRUST/"implementation/kernel/signed_owner_release.py"
    x=p.lstat()
    need(stat.S_ISREG(x.st_mode) and x.st_uid==0
         and not p.is_symlink() and x.st_mode&0o022==0
         and digest(p.read_bytes())==SIGNED_OWNER_SHA,
         "ROOT_OWNER_VERIFIER_UNTRUSTED")
    spec=importlib.util.spec_from_file_location("exact_e_owner_verifier",p)
    need(spec is not None and spec.loader is not None,
         "ROOT_OWNER_VERIFIER_UNAVAILABLE")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def signed_owner(build_sha:str,manifest:dict)->tuple[dict,str]:
    p=stage_dir(build_sha)/"owner-proof.json"
    x=p.lstat()
    need(stat.S_ISREG(x.st_mode) and not p.is_symlink()
         and x.st_uid==1000 and x.st_nlink==1
         and stat.S_IMODE(x.st_mode)==0o400
         and 0<x.st_size<32768,
         "ONEUSE_OWNER_PROOF_UNTRUSTED")
    wrapper=json.loads(p.read_bytes())
    need(set(wrapper)=={
        "schema_version","action","build_sha","manifest_sha256",
        "scope_sha256","signed_owner_proof"}
         and wrapper["schema_version"]=="1.0"
         and wrapper["action"]==ACTION
         and wrapper["build_sha"]==build_sha
         and wrapper["manifest_sha256"]==MANIFEST_SHA
         and wrapper["scope_sha256"]==SCOPE_SHA,
         "OWNER_EXACT_ACTION_NOT_MATCHED")
    signer=installed_signer()
    public=signer.read_pinned_root_owner_public_key(PUB)
    decision=signer.verify_exact_owner_release(
        wrapper["signed_owner_proof"],
        public_key=public,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_candidate_sha=CANDIDATE,
        expected_rollback_sha="0"*40,
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=MANIFEST_SHA,
        expected_freeze_sha256=FREEZE_SHA,
        at=datetime.now(timezone.utc),
    )
    approval_id=decision.get("approval_id")
    need(isinstance(approval_id,str)
         and approval_id.startswith("owner-mcp-"),
         "SIGNED_OWNER_APPROVAL_ID_INVALID")
    return wrapper["signed_owner_proof"],approval_id


def root_file(path:Path,data:bytes,mode:int,uid:int=0)->None:
    need(not path.exists() and not path.is_symlink()
         and 0<len(data)<300_000,
         "ROOT_ONEUSE_FILE_ALREADY_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),mode)
    try:
        with os.fdopen(fd,"wb") as out:
            if uid:
                os.fchown(out.fileno(),uid,uid)
            out.write(data);out.flush();os.fsync(out.fileno())
        need(digest(path.read_bytes())==digest(data),
             "ROOT_STAGE_FILE_READBACK_CHANGED")
    except BaseException:
        # Preserve uncertain state for exact consumed-proof recovery.
        raise


def root_json(path:Path,data:dict,mode:int=0o600,uid:int=0)->None:
    root_file(path,canonical(data)+b"\n",mode,uid)


def root_replace(path:Path,content:bytes,*,required_old_sha:str)->None:
    old=path.lstat()
    need(stat.S_ISREG(old.st_mode) and not path.is_symlink()
         and old.st_uid==0 and old.st_gid==0 and old.st_nlink==1
         and stat.S_IMODE(old.st_mode)==0o600
         and digest(path.read_bytes())==required_old_sha,
         "ATOMIC_PROTECTED_POLICY_OR_CONTROL_DRIFT")
    temp=path.with_name("."+path.name+".pmv4e-"+CANDIDATE[:12])
    root_file(temp,content,0o600)
    os.replace(temp,path)
    need(digest(path.read_bytes())==digest(content),
         "ROOT_PROTECTED_ATOMIC_READBACK_MISMATCH")


def independent_root_modules(build_sha:str):
    need(os.geteuid()==0,"ROOT_ONLY")
    files={}
    for name in TRUST_NEW:
        files[name]=source_bytes(build_sha,name)
    from hashlib import sha256
    return {k:(v,sha256(v).hexdigest()) for k,v in files.items()}


def stage_root(build_sha:str,manifest:dict,
               signed:dict,approval_id:str,
               protected_before:dict)->dict:
    # Writes only after exact consent and all independent root preflight gates.
    root_sources=independent_root_modules(build_sha)
    ci=verify_ci(CANDIDATE)
    ci["stage_e_canary_action"]=ACTION
    ci["reviewed_root_build_sha"]=build_sha
    root_json(RECEIPT,{
        "schema_version":"1.0","action":ACTION,"source_sha":CANDIDATE,
        "build_sha":build_sha,"scope_sha256":SCOPE_SHA,
        "manifest_sha256":MANIFEST_SHA,"owner_approval_id":approval_id,
        "state":"started","phase":"preinstall",
        "protected_before":protected_before,
        "at":datetime.now(timezone.utc).isoformat(),
    })
    for name,(data,expected) in root_sources.items():
        dest=TRUST/name
        root_file(dest,data,0o444)
        need(digest(dest.read_bytes())==expected
             and dest.lstat().st_uid==0,
             "ROOT_TRUSTED_CANARY_SOURCE_NOT_PINNED")
    ROOT_BUNDLE.mkdir(mode=0o700)
    for name in BUNDLE_FILES:
        root_file(ROOT_BUNDLE/name,stage_bytes(name),0o444)
    root_json(CI,ci,0o444)
    root_json(
        OUTBOX/("release-"+CANDIDATE[:16]+".json"),
        {
            "schema_version":"1.0","component_id":"pmv4-e-canary",
            "image_digest":IMAGE,"release_id":"release-"+CANDIDATE[:16],
            "candidate_sha":CANDIDATE,"organization_id":"aot",
            "source":"authenticated_entra_owner:"+approval_id,
            "signed_owner_proof":signed,
        },
        0o600,uid=1000,
    )
    return ci


def inspect_canary_absent()->bool:
    p=subprocess.run(
        ["/usr/bin/docker","ps","-aq","--filter",
         "label=com.docker.compose.project=jason-pmv4-e-canary"],
        capture_output=True,text=True,timeout=20)
    return p.returncode==0 and not p.stdout.strip()


def remove_exact_orphaned_canary_network()->bool:
    """Remove only the exact empty, private canary network, never a peer."""
    name="jason-pmv4-e-canary-private"
    observed=subprocess.run(
        ["/usr/bin/docker","network","inspect",name],
        capture_output=True,text=True,timeout=20)
    if observed.returncode!=0:
        # Absent is fine; a Docker API failure is not quietly accepted.
        listing=subprocess.run(
            ["/usr/bin/docker","network","ls","--filter",
             "name=^"+name+"$","--format","{{.Name}}"],
            capture_output=True,text=True,timeout=20)
        need(listing.returncode==0 and name not in listing.stdout.splitlines(),
             "EXACT_CANARY_NETWORK_CANNOT_BE_VERIFIED_ABSENT")
        return False
    try:
        rows=json.loads(observed.stdout)
        need(isinstance(rows,list) and len(rows)==1,
             "CANARY_NETWORK_INSPECTION_NOT_EXACT")
        net=rows[0]
        labels=net.get("Labels") or {}
        need(net.get("Name")==name
             and net.get("Driver")=="bridge"
             and net.get("Internal") is True
             and net.get("Attachable") is False
             and not (net.get("Containers") or {})
             and labels.get("com.docker.compose.project")=="jason-pmv4-e-canary",
             "CANARY_NETWORK_HAS_FOREIGN_PEER_OR_POLICY")
    except (KeyError,TypeError,ValueError) as exc:
        raise Denied("PMV4_E_CANARY_NETWORK_NOT_TRUSTED") from exc
    cleanup=subprocess.run(
        ["/usr/bin/docker","network","rm",name],
        capture_output=True,text=True,timeout=20)
    need(cleanup.returncode==0,"EXACT_CANARY_NETWORK_REMOVAL_DENIED")
    need(not subprocess.run(
        ["/usr/bin/docker","network","ls","--filter",
         "name=^"+name+"$","--format","{{.Name}}"],
        capture_output=True,text=True,timeout=20).stdout.strip(),
        "CANARY_PRIVATE_NETWORK_NOT_REMOVED")
    return True


def native_release()->dict:
    p=TRUST/"tools/pmv4_e_canary_release_root.py"
    proc=subprocess.run([
        "/usr/bin/python3","-I","-B",str(p),"--promote",
        "--candidate-sha",CANDIDATE,
    ],capture_output=True,text=True,timeout=185)
    need(proc.returncode==0 and len(proc.stdout)<8000,
         "GENERIC_NATIVE_SIGNED_RELEASE_NOT_ACCEPTED")
    return json.loads(proc.stdout)


def installed_host():
    sys.path.insert(0,str(TRUST))
    from tools.pmv4_e_canary_host import PinnedCanaryHost
    from tools.independent_component_release import (
        trusted_file,ComponentReleaseController,
    )
    h=PinnedCanaryHost(production=True)
    return h


def cleanup(build_sha:str,*,accepted:bool)->None:
    # The actual native generic accepted receipt is kept as immutable evidence.
    # Rollback removes only the exact isolated canary and its one allowlist entry.
    manifest=json.loads((ROOT_BUNDLE/"manifest.json").read_bytes())
    host=installed_host()
    with host.host_transaction():
        with host.freeze_transaction(FREEZE_SHA):
            current=host.observe("jason-pmv4-e-canary")
            if current is not None:
                need(current==CANDIDATE,
                     "CANNOT_REMOVE_FOREIGN_COMPONENT")
                host.restore(None,manifest)
            need(inspect_canary_absent(),
                 "CANARY_STILL_PRESENT_AFTER_ROLLBACK")
    remove_exact_orphaned_canary_network()
    pointer=ROOT/"active/pmv4-e-canary.json"
    if pointer.exists() or pointer.is_symlink():
        x=pointer.lstat()
        need(stat.S_ISREG(x.st_mode) and not pointer.is_symlink()
             and x.st_uid==0 and x.st_nlink==1
             and json.loads(pointer.read_bytes())=={
                 "component_id":"pmv4-e-canary",
                 "candidate_sha":CANDIDATE,
                 "manifest_sha256":MANIFEST_SHA,
             }, "ACTIVE_POINTER_NOT_OUR_CANARY")
        pointer.unlink()
    # An exact rollback must restore policy bytes, not an approximate JSON.
    backup=json.loads(BACKUP.read_bytes())
    original=bytes.fromhex(backup["original_policy_hex"])
    added=bytes.fromhex(backup["allowed_policy_hex"])
    need(digest(original)==POLICY_SHA
         and not (ROOT/"active/pmv4-e-canary.json").exists(),
         "POLICY_ROLLBACK_SOURCE_OR_ACTIVE_COMPONENT_INVALID")
    policybytes=POLICY.read_bytes()
    need(policybytes==added or policybytes==original,
         "PROTECTED_POLICY_CHANGED_DURING_CANARY")
    if policybytes==added:
        root_replace(POLICY,original,required_old_sha=digest(added))
    need(digest(POLICY.read_bytes())==POLICY_SHA,
         "ROOT_POLICY_NOT_RESTORED")
    # Keep native signed approval, receipt and staging for audit/replay denial.
    ci_data=json.loads(CI.read_bytes())
    need(ci_data.get("candidate_sha")==CANDIDATE
         and ci_data.get("reviewed_root_build_sha")==build_sha,
         "CANARY_ROOT_CI_CHANGED")
    CI.unlink()
    need(inspect_canary_absent(),
         "CANARY_REAPPEARED_DURING_POLICY_ROLLBACK")


def execute(build_sha:str)->dict:
    preflight(build_sha,strict_root=True)
    manifest,scope,data=candidate_packet()
    signed,approval_id=signed_owner(build_sha,manifest)
    before=protected_status()
    # One-use receipt precedes all trusted-root staging and policy writes.
    # No implicit reauthorization of an interrupted execution.
    ci=stage_root(build_sha,manifest,signed,approval_id,before)
    try:
        raw=POLICY.read_bytes()
        policy_module=source_bytes(
            build_sha,"tools/pmv4_e_canary_drift_policy.py")
        import types
        mod=types.ModuleType("pmv4_e_canary_policy")
        # Source was SHA-bound against exact protected Git file above.
        # Isolate to root-controlled installed trusted package for imports.
        sys.path.insert(0,str(TRUST))
        exec(compile(policy_module,str(root_script(build_sha))+"::policy","exec"),
             mod.__dict__)
        updated=mod.candidate(
            root_policy_bytes=raw,expected_before_sha256=POLICY_SHA)
        need(updated["production_mutations"] is False
             and updated["breaker_overridden"] is False
             and updated["watchdog_disabled"] is False,
             "CANARY_POLICY_PLAN_NOT_EXACT")
        root_json(BACKUP,{
            "schema_version":"1.0","source_sha":CANDIDATE,
            "build_sha":build_sha,"original_policy_hex":raw.hex(),
            "allowed_policy_hex":updated["new_policy_bytes"].hex(),
            "owner_approval_id":approval_id,
        })
        root_replace(POLICY,updated["new_policy_bytes"],
                     required_old_sha=POLICY_SHA)
        result=native_release()
        need(result.get("status")==
             "providerfree_native_generic_controller_accepted"
             and result.get("source_sha")==CANDIDATE
             and result.get("component_id")=="pmv4-e-canary"
             and result.get("provider_writes")==0
             and result.get("protected_service_restarts")==0
             and result.get("retirement_authorized") is False,
             "CANARY_ACCEPTANCE_NOT_EXACT")
        # Validate native signed journal before removing the canary.
        from tools.independent_component_release import trusted_file
        receipts=list((ROOT/"receipts").glob("owner-"+approval_id+".json"))
        need(len(receipts)==1
             and json.loads(trusted_file(receipts[0],production=True,
                                         allow_owner_write=True)).get("state")
                =="accepted",
             "NATIVE_ACCEPTED_RECEIPT_NOT_VERIFIED")
        cleanup(build_sha,accepted=True)
        after=protected_status()
        need(before==after,"PROTECTED_SERVICES_CHANGED_DURING_CANARY")
        evidence={
            "schema_version":"1.0","action":ACTION,
            "source_sha":CANDIDATE,"build_sha":build_sha,
            "approval_id":approval_id,
            "scope_sha256":SCOPE_SHA,
            "manifest_sha256":MANIFEST_SHA,
            "state":"accepted_and_removed",
            "native_generic_acceptance_verified":True,
            "isolated_canary_rollback_verified":True,
            "protected_before_equals_after":True,
            "protected_policy_sha256":POLICY_SHA,
            "provider_calls":0,
            "production_freeze_unchanged":True,
            "pmv3_units_modified":False,
            "retirement_authorized":False,
            "finished_at":datetime.now(timezone.utc).isoformat(),
        }
        # Separate immutable terminal result; original attempt ledger remains.
        root_json(ROOT/"control"/("pmv4-e-canary-"+CANDIDATE+"-accepted.json"),
                  evidence)
        return evidence
    except BaseException:
        # Native generic release itself performs bounded rollback on failed
        # activation. A failed cleanup retains exact owner proof + receipt.
        # The recover action is intentionally cleanup-only, never promotion.
        try:
            if BACKUP.exists():
                cleanup(build_sha,accepted=False)
        except BaseException:
            pass
        raise


def recover(build_sha:str)->dict:
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "ROOT_ISOLATED_EXECUTION_REQUIRED")
    exact_modules(build_sha)
    manifest,_,_=candidate_packet()
    signed,approval_id=signed_owner(build_sha,manifest)
    original=json.loads(RECEIPT.read_bytes())
    need(original.get("approval_id")==approval_id
         or original.get("owner_approval_id")==approval_id,
         "RECOVERY_MUST_USE_ORIGINAL_APPROVAL")
    need(original.get("action")==ACTION
         and original.get("source_sha")==CANDIDATE
         and BACKUP.is_file(),
         "RECOVERY_NOT_AN_ORIGINAL_CANARY_TRANSACTION")
    cleanup(build_sha,accepted=False)
    need(digest(POLICY.read_bytes())==POLICY_SHA,
         "RECOVERY_ROOT_POLICY_NOT_RESTORED")
    return {
        "status":"same_approved_canary_removed_root_policy_restored",
        "source_sha":CANDIDATE,
        "approval_id":approval_id,
        "new_owner_approvals":0,
        "provider_writes":0,
        "retirement_authorized":False,
    }


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-source",action="store_true")
    group.add_argument("--root-preflight",action="store_true")
    group.add_argument("--execute",action="store_true")
    group.add_argument("--recover",action="store_true")
    parser.add_argument("--build-sha",required=True)
    args=parser.parse_args(argv)
    if args.check_source:
        result=preflight(args.build_sha,strict_root=False)
    elif args.root_preflight:
        result=preflight(args.build_sha,strict_root=True)
    elif args.execute:
        result=execute(args.build_sha)
    else:
        result=recover(args.build_sha)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    try:
        main()
    except (Denied,OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print("PMV4_E_ROOT_DENIED:"+type(exc).__name__
              +( ":"+str(exc)[:140] if isinstance(exc,Denied) else ""),
              file=sys.stderr)
        raise SystemExit(2)
