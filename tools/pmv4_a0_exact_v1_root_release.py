#!/usr/bin/env python3
"""ONE reviewed PMv4 A0 release: original v1 Owner signature, exact 3 effects.

Not a generic root action, shell or release executor. Code executes only after
being installed as immutable root:root 0400 in the exact private /run stage.
Owner's one Entra exact-action signature binds the WHOLE scope+root code hash.
No user-controlled path/command or reusable production authority.

The single existing PMv3 native release lock covers bootstrap, source closure,
native A0 installation, postflight, audit, and reverse rollback. Never release
the native lock between steps. Root production freeze and promotion hold are
unchanged. Real root execution requires separately governed Owner exact proof.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Mapping

CANDIDATE = "7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
REVIEW = "f5f525e33e4cad46827018e23ea7ae8f72603459dcd740bfbf63f9a176cfa52a"
NATIVE_SCOPE = "6786baad0fc9d07aca6ba80dedad5c25bcfa7fb3e50fdde7c4d36ad067285eac"
NATIVE_MANIFEST = "addba768d1ab92d9507d466fdd3980b93ea2041f42901f5d6e5a2cde81dcb025"
SOURCE_MISSING_SHA = "ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db"
STEPS = (
    ("pmv4.stage-a0.root-source-helper.bootstrap",
     "root-source-closure-helper",
     "e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb",
     "25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"),
    ("pmv4.stage-a0.immutable-root-source-onefile",
     "exact-one-missing-root-blob",
     "089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381",
     SOURCE_MISSING_SHA),
    ("pmv4.stage-a0.native-empty-baseline-install",
     "independent-stage-a0-native",
     NATIVE_SCOPE, NATIVE_MANIFEST),
)
RELEASE = Path("/var/lib/jason/openclaw/release-manager")
LOCK = RELEASE / "production-transaction.lock"
FREEZE = RELEASE / "production-deployment-freeze"
HOLD = RELEASE / "auto-promotion-incident-hold"
JOURNAL = RELEASE / "protected-transitions/pmv4-a0-exact-one-release-v1-7b42.jsonl"
STAGE = Path("/run/jason-pmv4-a0-atomic-v1-7b42")
THIS = STAGE / "installer.py"
BOOT = STAGE / "bootstrap.py"
POLICY = STAGE / "policy.json"
PROOF = Path("/srv/jason/archive/pmv4-a0-atomic-v1-OWNER-PROOF-7b42.json")
SOURCE = Path("/opt/jason/releases") / CANDIDATE
MISSING_FILE = SOURCE / "tools/pmv4_host_install_contract.py"
ROOT_HELPER = Path("/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py")
ROOT_HELPER_POLICY = Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json")
ROOT_LEDGER = Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure-ledger")
SPARSE_STAGE = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_root_stage.py")
SPARSE_SHA = "b3880288e24a44de2c461c474dd2bf86d44b8b57ad0c5ba1720d1c5aedecf606"
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
VERIFIER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
ROOT_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
BOOT_SHA = "3790bf79d4a302fe572055c3936ba28b8935ea9e1dc1a833b6b8acc9ed62878b"
ROOT_HELPER_SHA = "1006edb6613f3ff976fadf64c25d8e6096dfef6b2296e4583ba51ee81ee4c4f6"
ROOT_HELPER_POLICY_SHA = "7cd1ef65c9bcf8c6442a191348ac187c05c421ed8576998b61b7427d08a5da32"
SOURCE_ROOT = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_source.py")
ROOT_CI = Path("/usr/local/lib/jason/pmv4_shadow_ci.py")
LIVE_GIT = Path("/home/al/.local/lib/jason/engineering-source-repo")


class AtomicRootDenied(PermissionError):
    pass


def need(condition: bool, code: str) -> None:
    if not condition:
        raise AtomicRootDenied(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canon(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def root_file(path: Path, *, expected: str | None = None,
              mode: int | None = None, maximum: int = 200000) -> bytes:
    need(not path.is_symlink(), "A0_ATOMIC_ROOT_SYMLINK")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        m = os.fstat(fd)
        need(stat.S_ISREG(m.st_mode) and m.st_uid == 0
             and m.st_nlink == 1 and m.st_size <= maximum,
             "A0_ATOMIC_UNTRUSTED_ROOT_MODULE")
        if mode is not None:
            need(stat.S_IMODE(m.st_mode) == mode, "A0_ATOMIC_MODE_CHANGED")
        if expected is not None:
            need(sha(os.read(fd, maximum + 1)) == expected,
                 "A0_ATOMIC_HASH_CHANGED")
            os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, maximum + 1)
        need(len(raw) == m.st_size, "A0_ATOMIC_ROOT_SHORT_READ")
        return raw
    finally:
        os.close(fd)


def load_trusted(path: Path, name: str, expected: str):
    root_file(path, expected=expected)
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None,
         "A0_ATOMIC_ROOT_MODULE_LOAD_DENIED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reviewed_policy(*, require_root: bool) -> dict[str, Any]:
    if require_root:
        raw = root_file(POLICY, mode=0o400, maximum=12000)
    else:
        raw = POLICY.read_bytes()
    p = json.loads(raw)
    need(isinstance(p, dict) and set(p) == {
        "schema_version", "action", "production_apply_supported",
        "root_executor_sha256", "root_bootstrap_sha256",
        "helper_sha256", "helper_policy_sha256", "reviewed_contract_sha256",
        "candidate_sha", "lkg_sha", "freeze_sha256", "hold_sha256",
        "runtime_image_sha256", "mcp_image_sha256",
        "ordered_actions", "one_use", "standing_authority",
    }, "A0_ATOMIC_POLICY_FIELDS_INVALID")
    need(p["schema_version"] == "1.0"
         and p["action"] == "pmv4-a0-exact-three-action-one-release-v1"
         and p["production_apply_supported"] is False
         and p["candidate_sha"] == CANDIDATE
         and p["lkg_sha"] == LKG
         and p["freeze_sha256"] == FREEZE_SHA
         and p["hold_sha256"] == HOLD_SHA
         and p["runtime_image_sha256"] == RUNTIME_IMAGE
         and p["mcp_image_sha256"] == MCP_IMAGE
         and p["reviewed_contract_sha256"] == REVIEW
         and p["root_bootstrap_sha256"] == BOOT_SHA
         and p["helper_sha256"] == ROOT_HELPER_SHA
         and p["helper_policy_sha256"] == ROOT_HELPER_POLICY_SHA
         and p["one_use"] is True
         and p["standing_authority"] is False,
         "A0_ATOMIC_POLICY_SCOPE_CHANGED")
    need(isinstance(p["root_executor_sha256"], str)
         and len(p["root_executor_sha256"]) == 64
         and all(x in "0123456789abcdef" for x in p["root_executor_sha256"]),
         "A0_ATOMIC_ROOT_SELF_DIGEST_INVALID")
    need(len(p["ordered_actions"]) == 3 and all(
        row == {"capability": x[0], "component": x[1],
                "scope_sha256": x[2], "artifact_sha256": x[3],
                "rollback_sha": "0"*40, "risk": 3}
        for row,x in zip(p["ordered_actions"], STEPS)),
        "A0_ATOMIC_EXTRA_OR_CHANGED_STEP")
    if not require_root:
        need(sha(Path(__file__).read_bytes())==p["root_executor_sha256"],
             "A0_ATOMIC_SOURCE_ROOT_CODE_CHANGED")
    if require_root:
        need(sha(root_file(THIS, mode=0o400, maximum=130000)) ==
             p["root_executor_sha256"], "A0_ATOMIC_ROOT_CODE_NOT_REVIEWED")
        root_file(BOOT, expected=BOOT_SHA, mode=0o400)
        root_file(VERIFIER, expected=VERIFIER_SHA)
        root_file(SPARSE_STAGE, expected=SPARSE_SHA)
    return p


def full_release_scopes(p: Mapping[str, Any]) -> dict[str, Any]:
    """Same strict original v1 canonical source/signature material as issuer."""
    manifest = {
        "schema_version":"1.0",
        "service":"pmv4-stage-a0-exact-three-action-one-release",
        "source_sha":CANDIDATE, "production_lkg":LKG,
        "rollback_sha":LKG, "freeze_sha256":FREEZE_SHA,
        "promotion_hold_sha256":HOLD_SHA,
        "reviewed_contract_sha256":REVIEW,
        "root_executor_sha256":p["root_executor_sha256"],
        "exact_ordered_actions":list(p["ordered_actions"]),
        "owner_consents":1,
        "root_lock_shared_by_all_actions":True,
        "require_root_only_empty_baseline":True,
        "require_reverse_verified_rollback":True,
        "production_runtime_or_mcp_replacement":False,
        "production_freeze_or_hold_mutation":False,
        "provider_or_ticket_mutation":False,
        "standing_authority":False,
        "one_release_only":True,
    }
    scope = {
        "schema_version":"1.0",
        "service":manifest["service"],
        "source_sha":CANDIDATE,
        "rollback_sha":LKG,
        "reviewed_contract_sha256":REVIEW,
        "root_executor_sha256":p["root_executor_sha256"],
        "exact_ordered_actions":list(p["ordered_actions"]),
        "one_release_only":True,
    }
    return {"manifest": manifest, "scope_sha256":sha(canon(scope)),
            "manifest_sha256":sha(canon(manifest))}


def trusted_entry() -> dict[str, Any]:
    need(os.geteuid() == 0 and sys.flags.isolated == 1
         and Path(__file__).absolute() == THIS,
         "A0_ATOMIC_TRUSTED_LOCAL_ROOT_REQUIRED")
    m = STAGE.lstat()
    need(stat.S_ISDIR(m.st_mode) and m.st_uid == 0 and m.st_gid == 0
         and stat.S_IMODE(m.st_mode) == 0o700 and not STAGE.is_symlink(),
         "A0_ATOMIC_PRIVATE_ROOT_STAGE_INVALID")
    p = reviewed_policy(require_root=True)
    return p


def read_one_user_proof() -> dict[str,Any]:
    # NEVER read arbitrary user-controlled symlink as root: the OWNER proof
    # is UID1000 0600, single-link regular and bounded BEFORE reading bytes.
    fd=os.open(PROOF,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        m=os.fstat(fd)
        need(stat.S_ISREG(m.st_mode) and m.st_uid==1000
             and m.st_nlink==1 and stat.S_IMODE(m.st_mode)==0o600
             and 0 < m.st_size <= 15000,
             "A0_ATOMIC_OWNER_PROOF_FILE_UNTRUSTED")
        raw=os.read(fd,15001)
        need(len(raw)==m.st_size,"A0_ATOMIC_OWNER_PROOF_SHORT_OR_CHANGED")
    finally: os.close(fd)
    parsed=json.loads(raw)
    need(isinstance(parsed,dict),"A0_ATOMIC_OWNER_PROOF_NOT_OBJECT")
    return parsed


def verify_proof(p: Mapping[str, Any], *, at: datetime):
    verifier=load_trusted(VERIFIER,"a0_original_root_owner_verifier",VERIFIER_SHA)
    row=read_one_user_proof()
    need(set(row) == {"schema_version","action","source_sha",
                      "scope_sha256","manifest_sha256","signed_owner_proof"}
         and row["schema_version"]=="1.0"
         and row["action"]=="pmv4-a0-exact-three-action-one-release-v1"
         and row["source_sha"]==CANDIDATE,
         "A0_ATOMIC_OWNER_PROOF_ENVELOPE_CHANGED")
    scopes=full_release_scopes(p)
    need(row["scope_sha256"]==scopes["scope_sha256"]
         and row["manifest_sha256"]==scopes["manifest_sha256"],
         "A0_ATOMIC_SIGNED_WHOLE_SCOPE_DRIFT")
    verified=verifier.verify_exact_owner_release(
        row["signed_owner_proof"],
        public_key=verifier.read_pinned_root_owner_public_key(
            ROOT_PIN,require_root_owned=True,
        ), at=at,
        expected_candidate_sha=CANDIDATE,
        expected_rollback_sha=LKG,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_scope_sha256=scopes["scope_sha256"],
        expected_manifest_sha256=scopes["manifest_sha256"],
        expected_freeze_sha256=FREEZE_SHA,
    )
    need(verified["one_release_only"] is True
         and verified["standing_authority"] is False
         and verified["approval_id"].startswith("owner-mcp-"),
         "A0_ATOMIC_OWNER_APPROVAL_NOT_ONE_SHOT")
    return {"approval_id":verified["approval_id"],
            "proof_sha256":sha(canon(row["signed_owner_proof"])),
            "full_manifest_sha256":scopes["manifest_sha256"]}


@contextmanager
def root_release_lock():
    fd=os.open(LOCK,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        m=os.fstat(fd)
        need(stat.S_ISREG(m.st_mode) and m.st_uid==1000 and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==0o664,
             "A0_ATOMIC_EXISTING_NATIVE_LOCK_DRIFT")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AtomicRootDenied("A0_ATOMIC_EXISTING_RELEASE_BUSY") from exc
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def fsync_parent(path: Path) -> None:
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|
               getattr(os,"O_NOFOLLOW",0))
    try: os.fsync(fd)
    finally: os.close(fd)


def audit_rows() -> list[dict[str,Any]]:
    if not JOURNAL.exists() and not JOURNAL.is_symlink():
        return []
    raw=root_file(JOURNAL,mode=0o600,maximum=128000)
    need(bool(raw) and raw.endswith(b"\n"),"A0_ATOMIC_AUDIT_TORN")
    rows=[]
    previous="0"*64
    for ln in raw.splitlines():
        try: x=json.loads(ln)
        except (ValueError,TypeError) as exc:
            raise AtomicRootDenied("A0_ATOMIC_AUDIT_CORRUPT") from exc
        need(isinstance(x,dict) and set(x)=={
            "version","seq","step","action","owner_approval_id",
            "signed_release_sha256","detail_sha256","prev_sha256","hash",
        } and x["version"]==1 and type(x["seq"]) is int
             and x["seq"]==len(rows)+1 and x["prev_sha256"]==previous
             and x["hash"]==sha(canon({k:v for k,v in x.items() if k!="hash"})),
             "A0_ATOMIC_AUDIT_CHAIN_DRIFT")
        rows.append(x)
        previous=x["hash"]
    need(rows[0]["action"]=="begin" and rows[0]["step"]==-1,
         "A0_ATOMIC_AUDIT_BEGIN_INVALID")
    for x in rows:
        need(x["owner_approval_id"]==rows[0]["owner_approval_id"]
             and x["signed_release_sha256"]==rows[0]["signed_release_sha256"],
             "A0_ATOMIC_AUDIT_OWNER_SCOPE_DRIFT")
    validate_sequence(rows)
    return rows


def validate_sequence(rows: list[dict[str,Any]]) -> None:
    done=set()
    pending=None
    reverting=False
    rolled=set()
    terminal=False
    for index,row in enumerate(rows):
        action,step=row["action"],row["step"]
        if index==0:
            need(action=="begin" and step==-1,"A0_ATOMIC_BEGIN_CHANGED")
            continue
        need(not terminal,"A0_ATOMIC_EVENT_AFTER_COMPLETION")
        if action=="intent":
            need(not reverting and pending is None
                 and type(step) is int and step==len(done) and step<3,
                 "A0_ATOMIC_INTENT_OUT_OF_ORDER")
            pending=step
        elif action=="installed":
            need(not reverting and pending==step,
                 "A0_ATOMIC_INSTALL_WITHOUT_INTENT")
            done.add(step)
            pending=None
        elif action=="committed":
            need(not reverting and step==-1 and pending is None
                 and done=={0,1,2},
                 "A0_ATOMIC_PARTIAL_COMMIT_DENIED")
            terminal=True
        elif action=="rollback_begin":
            need(not reverting and step==-1,
                 "A0_ATOMIC_INVALID_REVERSE_START")
            reverting=True
        elif action=="rollback_verified":
            need(reverting and type(step) is int
                 and step in (done|({pending} if pending is not None else set()))
                 and step not in rolled
                 and all(j>step for j in rolled),
                 "A0_ATOMIC_ROLLBACK_ORDER_OR_REPLAY")
            rolled.add(step)
            if step in done:
                done.remove(step)
            else:
                pending=None
        elif action=="rolled_back":
            need(reverting and step==-1 and not done and pending is None,
                 "A0_ATOMIC_ROLLBACK_NOT_EMPTY")
            terminal=True
        elif action=="requires_review":
            need(reverting and step==-1,
                 "A0_ATOMIC_INVALID_REVIEW_EVENT")
            terminal=True
        else:
            raise AtomicRootDenied("A0_ATOMIC_UNKNOWN_AUDIT_EVENT")


def audit_append(action: str,step: int,evidence: Mapping[str,Any],
                 proof: Mapping[str,str]) -> None:
    rows=audit_rows()
    if not rows:
        need(action=="begin" and step==-1,
             "A0_ATOMIC_AUDIT_REQUIRES_BEGIN")
    else:
        need(rows[-1]["action"] not in {"committed","rolled_back","requires_review"},
             "A0_ATOMIC_ALREADY_FINAL")
    row={
        "version":1,"seq":len(rows)+1,"step":step,"action":action,
        "owner_approval_id":proof["approval_id"],
        "signed_release_sha256":proof["proof_sha256"],
        "detail_sha256":sha(canon(dict(evidence))),
        "prev_sha256":rows[-1]["hash"] if rows else "0"*64,
    }
    row["hash"]=sha(canon(row))
    # Verify a legal transition BEFORE persistent append. Otherwise a
    # malformed half-finished commit could poison an otherwise recoverable
    # native journal and force an unnecessary new Owner decision.
    validate_sequence(rows+[row])
    flags=os.O_WRONLY|os.O_APPEND|getattr(os,"O_NOFOLLOW",0)
    if not rows:
        flags|=os.O_CREAT|os.O_EXCL
    fd=os.open(JOURNAL,flags,0o600)
    try:
        m=os.fstat(fd)
        need(stat.S_ISREG(m.st_mode) and m.st_uid==0
             and m.st_nlink==1 and stat.S_IMODE(m.st_mode)==0o600,
             "A0_ATOMIC_AUDIT_WRITE_TAMPERED")
        raw=canon(row)+b"\n"
        need(os.write(fd,raw)==len(raw),"A0_ATOMIC_AUDIT_SHORT_WRITE")
        os.fsync(fd)
    finally: os.close(fd)
    fsync_parent(JOURNAL.parent)
    audit_rows()


def verify_full_integrity() -> None:
    # Systemd independently attests completion; the JSON alone is not a root
    # authorization, and a short read-only unit check never restarts services.
    unit=subprocess.check_output([
        "/usr/bin/systemctl","show",
        "jason-openclaw-authority-full-integrity.service",
        "-p","Result","-p","ActiveState",
    ],text=True,timeout=8)
    need("Result=success" in unit and "ActiveState=inactive" in unit,
         "A0_ATOMIC_SYSTEMD_FULL_INTEGRITY_NOT_COMPLETE")
    base=Path("/var/lib/jason/openclaw")
    full_path=base/"operational-full-health.json"
    fast_path=base/"operational-health.json"
    now=datetime.now(timezone.utc).timestamp()
    need(0 <= now-full_path.stat().st_mtime <= 86400
         and 0 <= now-fast_path.stat().st_mtime <= 600,
         "A0_ATOMIC_INTEGRITY_OR_FAST_HEALTH_STALE")
    full=json.loads(full_path.read_bytes())
    fast=json.loads(fast_path.read_bytes())
    need(full.get("status")==fast.get("status")=="pass"
         and full.get("failures")==fast.get("failures")==[]
         and full.get("snapshot_source_exit_code")==0
         and fast.get("full_proof_status")=="pass"
         and isinstance(fast.get("full_proof_age_seconds"),(int,float))
         and 0<=fast["full_proof_age_seconds"]<=86400
         and all(full.get("files",{}).get(x,{}).get("integrity")=="ok"
                 for x in ("authority","orchestration_audit","replay","security_audit"))
         and all(full.get("backup_restore_proof",{}).get(k)=="ok"
                 for k in ("backup_integrity","restore_integrity")),
         "A0_ATOMIC_AUTHORITY_HEALTH_NOT_PROVEN")


def read_root_preflight() -> dict[str,Any]:
    # Only fixed preexisting root-owned helpers and immutable exact-source data.
    verify_full_integrity()
    p=reviewed_policy(require_root=True)
    stage=load_trusted(SPARSE_STAGE,"a0_atomic_existing_sparse_root",SPARSE_SHA)
    sparse_policy=stage.trusted_policy()
    need(sparse_policy["candidate_sha"]==CANDIDATE
         and sparse_policy["lkg_sha"]==LKG
         and sparse_policy["freeze_sha256"]==FREEZE_SHA
         and sparse_policy["promotion_hold_sha256"]==HOLD_SHA
         and sparse_policy["runtime_image_sha256"]==RUNTIME_IMAGE
         and sparse_policy["mcp_image_sha256"]==MCP_IMAGE,
         "A0_ATOMIC_SPARSE_TRUST_POLICY_DRIFT")
    bootstrap=load_trusted(BOOT,"a0_atomic_reviewed_root_bootstrap",BOOT_SHA)
    bootstrap.validate_plan()
    baseline=bootstrap.readback()
    need(stage.protected_preflight(sparse_policy)["runtime_id"]==baseline["runtime_id"],
         "A0_ATOMIC_PROTECTED_PRECHECK_CHANGED")
    ci=stage._load_trusted(ROOT_CI,"a0_atomic_existing_root_ci")
    need(stage.protected_ci_as_operator(ci,CANDIDATE),
         "A0_ATOMIC_PROTECTED_MAIN_CI_DENIED")
    bootstrap.require_empty()
    source=stage._load_trusted(SOURCE_ROOT,"a0_atomic_existing_sparse_source")
    blob=source.git_object(stage.REPO)
    original=source.source_manifest(CANDIDATE,blob,
        freeze_sha256=FREEZE_SHA,current_lkg=LKG)
    need(original.get("scope_sha256")==
         "09e35bf812c3bedd61991af669ea9a80b0a0ff5948b1d1a6edb1d70c3332c27f"
         and len(original["files"])==13,
         "A0_ATOMIC_ORIGINAL_THIRTEEN_SOURCE_SCOPE_CHANGED")
    stage.verify_staged_source(SOURCE,original)
    need(not MISSING_FILE.exists() and not MISSING_FILE.is_symlink(),
         "A0_ATOMIC_SOURCE_ALREADY_CLOSED")
    for target in (
        Path("/var/lib/jason/pmv4-shadow"),
        Path("/usr/local/lib/jason/pmv4-trusted"),
        Path("/etc/jason/pmv4-shadow"),
    ):
        need(not target.exists() and not target.is_symlink(),
             "A0_ATOMIC_NATIVE_TARGET_NOT_EMPTY")
    parent=JOURNAL.parent.lstat()
    need(stat.S_ISDIR(parent.st_mode) and parent.st_uid==0
         and not JOURNAL.parent.is_symlink()
         and not (parent.st_mode&0o022),
         "A0_ATOMIC_AUDIT_PARENT_UNTRUSTED")
    need(not JOURNAL.exists() and not JOURNAL.is_symlink(),
         "A0_ATOMIC_ALREADY_CLAIMED")
    need(sha(FREEZE.read_bytes())==FREEZE_SHA
         and sha(HOLD.read_bytes())==HOLD_SHA,
         "A0_ATOMIC_FROZEN_CONTROL_DRIFT")
    return {"policy":p,"stage":stage,"bootstrap":bootstrap,
            "sparse":sparse_policy,"source":source,"baseline":baseline,
            "original":original}


def close_source(ctx: Mapping[str,Any]) -> dict[str,Any]:
    stage=ctx["stage"]
    closure=load_trusted(ROOT_HELPER,
                         "a0_atomic_reviewed_root_source_closure",
                         ROOT_HELPER_SHA)
    policy=closure.trusted_policy(stage)
    need(sha(root_file(ROOT_HELPER_POLICY,mode=0o400))==
         ROOT_HELPER_POLICY_SHA,"A0_ATOMIC_CLOSURE_POLICY_CHANGED")
    prior,after,missing=closure.exact_source_scopes(
        ctx["source"],stage,policy)
    closure.verify_prior(stage,SOURCE,prior)
    need(sha(missing)==SOURCE_MISSING_SHA,"A0_ATOMIC_SOURCE_BLOB_CHANGED")
    def verify_while_created_inode_open():
        stage.verify_staged_source(SOURCE,after)
        protected=stage.protected_preflight(ctx["sparse"])
        need(protected["runtime_id"]==ctx["baseline"]["runtime_id"]
             and protected["mcp_id"]==ctx["baseline"]["mcp_id"],
             "A0_ATOMIC_POST_SOURCE_PRODUCTION_DRIFT")
    closure._write_one_exact(MISSING_FILE,missing,
                             after_write=verify_while_created_inode_open)
    return {"prior":prior,"after":after,"missing_sha256":SOURCE_MISSING_SHA}


def load_native_exact_source(ctx: Mapping[str,Any],
                             after: Mapping[str,Any]):
    ctx["stage"].verify_staged_source(SOURCE,after)
    need(SOURCE.is_dir() and SOURCE.stat().st_uid==0,
         "A0_ATOMIC_NATIVE_SOURCE_NOT_ROOT_PINNED")
    # Source data become executable ONLY after all fourteen files have been
    # independently matched against protected main and fixed 0444 root pins.
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "A0_ATOMIC_NATIVE_IMPORT_ROOT_REQUIRED")
    sys.path.insert(0,str(SOURCE))
    from tools import pmv4_stage_a_packet as packet
    from tools import pmv4_stage_a_admission as admission
    from tools import pmv4_stage_a_native_install as native
    packet.verify_immutable_host_release_source(SOURCE,CANDIDATE)
    scope=packet.build_scope(SOURCE,CANDIDATE)
    need(scope["scope_sha256"]==NATIVE_SCOPE
         and scope["rollback_sha"]=="0"*40,
         "A0_ATOMIC_NATIVE_SCOPE_CHANGED")
    manifest=admission.exact_stage_a_manifest(scope,FREEZE_SHA)
    need(sha(canon(manifest))==NATIVE_MANIFEST,
         "A0_ATOMIC_NATIVE_MANIFEST_CHANGED")
    return packet,native,scope,manifest


def native_install_under_outer_lock(
    packet:Any,native:Any,scope:Mapping[str,Any],manifest:Mapping[str,Any],
    proof:Mapping[str,str],
):
    # The outer root_release_lock is already HELD for all three effects.
    # Do not call existing native.install(), whose independent per-stage v1
    # proof would need another human approval and separate flock.
    engine=native.NativeStageAInstaller(
        production=True,owner_metadata=True,
        root_health=native.production_root_health_readback,
    )
    engine._trusted_journal_parent()
    engine._assert_parents()
    pre=native.production_root_health_readback()
    need(pre["stage_a_empty_baseline_verified"] is True
         and pre["root_only_target_parent_verification_needed"] is False,
         "A0_ATOMIC_NATIVE_ROOT_BASELINE_NOT_EMPTY")
    journal=engine._journal(CANDIDATE)
    need(not journal.exists() and not journal.is_symlink(),
         "A0_ATOMIC_NATIVE_JOURNAL_ALREADY_CLAIMED")
    binding={
        "source_sha":CANDIDATE,"scope_sha256":NATIVE_SCOPE,
        "owner_approval_id":proof["approval_id"],
        "manifest_sha256":NATIVE_MANIFEST,
        "freeze_sha256":FREEZE_SHA,
        "signed_proof_sha256":proof["proof_sha256"],
    }
    engine._append(journal,"prepared",binding)
    engine._create(SOURCE,scope,journal,binding,None)
    engine._verify_objects(scope,partial=False)
    engine._assert_new_lock(scope)
    need(sha(FREEZE.read_bytes())==FREEZE_SHA
         and sha(HOLD.read_bytes())==HOLD_SHA,
         "A0_ATOMIC_FROZEN_CONTROLS_CHANGED_AFTER_NATIVE")
    # Preserve the ORIGINAL native release fitness checks rather than
    # calling its install() with a different per-stage human signature.
    # One root-verified complete-release proof must not waive ticket scanner
    # freshness, runtime health, MCP service, or protected root breaker.
    guard=packet.IndependentHostGuard()
    need(guard.protected_release_status().get("ready") is True,
         "A0_ATOMIC_POSTINSTALL_ROOT_BREAKER_NOT_READY")
    core=guard.core_health_evidence()
    need(all(core.get(k) is True for k in (
        "runtime_healthy","mcp_running","worker_scan_fresh")),
         "A0_ATOMIC_POSTINSTALL_TICKET_CORE_DEGRADED")
    engine._append(journal,"verified_installed",binding)
    if engine._new_fd is not None:
        os.close(engine._new_fd)
        engine._new_fd=None
    return engine,journal,binding


def cleanup_native_under_outer_lock(packet,engine,scope,journal,binding):
    # Existing native recover_empty body, but WITHOUT taking its inner
    # advisory flock; outer release lock is continuously held.
    rows=engine._events(journal)
    need(rows and rows[0]["event"]=="prepared"
         and rows[-1]["event"]!="rolled_back"
         and all(x["scope_sha256"]==NATIVE_SCOPE
                 and x["source_sha"]==CANDIDATE
                 and x["owner_approval_id"]==binding["owner_approval_id"]
                 and x["signed_proof_sha256"]==binding["signed_proof_sha256"]
                 for x in rows),
         "A0_ATOMIC_NATIVE_ROLLBACK_RECEIPT_DRIFT")
    engine._verify_objects(scope,partial=True)
    engine._append(journal,"rollback_intent",binding)
    for r in scope["symlinks"]:
        path=engine._map(r["path"])
        if path.is_symlink():
            need(os.readlink(path)==r["target"],"A0_ATOMIC_FOREIGN_SYMLINK")
            path.unlink()
    for r in scope["files"]:
        path=engine._map(r["path"])
        if path.is_file():
            need(sha(path.read_bytes())==r["sha256"] and not path.is_symlink(),
                 "A0_ATOMIC_FOREIGN_NATIVE_FILE")
            path.unlink()
    for r in reversed(scope["directories"]):
        path=engine._map(r["path"])
        if path.is_dir():
            path.rmdir()
    need(all(not engine._map(p).exists() and not engine._map(p).is_symlink()
             for p in (packet.HOST_CODE,packet.ROOT,packet.ETC)),
         "A0_ATOMIC_NATIVE_ROLLBACK_NOT_EMPTY")
    engine._append(journal,"rolled_back",binding)
    if engine._new_fd is not None:
        os.close(engine._new_fd)
        engine._new_fd=None


def recover_native_if_present(ctx:Mapping[str,Any], proof:Mapping[str,str]):
    # No second lock or second approval. Parse only the independently trusted
    # source we just verified during the original exact release.
    if not MISSING_FILE.exists():
        for path in (
            Path("/var/lib/jason/pmv4-shadow"),
            Path("/usr/local/lib/jason/pmv4-trusted"),
            Path("/etc/jason/pmv4-shadow"),
        ):
            need(not path.exists() and not path.is_symlink(),
                 "A0_ATOMIC_NATIVE_DATA_WITHOUT_TRUSTED_SOURCE")
        return
    closure=load_trusted(ROOT_HELPER,"a0_atomic_recovery_closure",ROOT_HELPER_SHA)
    policy=closure.trusted_policy(ctx["stage"])
    prior,after,_=closure.exact_source_scopes(
        ctx["source"],ctx["stage"],policy)
    ctx["stage"].verify_staged_source(SOURCE,after)
    packet,native,scope,manifest=load_native_exact_source(ctx,after)
    engine=native.NativeStageAInstaller(
        production=True,owner_metadata=True,
        root_health=native.production_root_health_readback)
    journal=engine._journal(CANDIDATE)
    paths=(
        Path("/var/lib/jason/pmv4-shadow"),
        Path("/usr/local/lib/jason/pmv4-trusted"),
        Path("/etc/jason/pmv4-shadow"),
    )
    if not journal.exists():
        need(not journal.is_symlink()
             and all(not p.exists() and not p.is_symlink() for p in paths),
             "A0_ATOMIC_FOREIGN_NATIVE_NO_AUDIT")
        return
    binding={
        "source_sha":CANDIDATE,"scope_sha256":NATIVE_SCOPE,
        "owner_approval_id":proof["approval_id"],
        "manifest_sha256":NATIVE_MANIFEST,
        "freeze_sha256":FREEZE_SHA,
        "signed_proof_sha256":proof["proof_sha256"],
    }
    cleanup_native_under_outer_lock(packet,engine,scope,journal,binding)


def recover_source_if_present(ctx:Mapping[str,Any]):
    if not MISSING_FILE.exists() and not MISSING_FILE.is_symlink():
        ctx["stage"].verify_staged_source(SOURCE,ctx["original"])
        return
    closure=load_trusted(ROOT_HELPER,"a0_atomic_recovery_closure",ROOT_HELPER_SHA)
    policy=closure.trusted_policy(ctx["stage"])
    prior,after,_=closure.exact_source_scopes(
        ctx["source"],ctx["stage"],policy)
    # exact_source_scopes does not require missing file absent, just
    # reconstructs the independently pinned prior and full after manifests.
    ctx["stage"].verify_staged_source(SOURCE,after)
    m=MISSING_FILE.lstat()
    need(not MISSING_FILE.is_symlink() and stat.S_ISREG(m.st_mode)
         and (m.st_uid,m.st_gid)==(0,0) and m.st_nlink==1
         and stat.S_IMODE(m.st_mode)==0o444
         and sha(MISSING_FILE.read_bytes())==SOURCE_MISSING_SHA,
         "A0_ATOMIC_SOURCE_FOREIGN_REPLACEMENT")
    MISSING_FILE.unlink()
    fsync_parent(MISSING_FILE.parent)
    ctx["stage"].verify_staged_source(SOURCE,prior)


def recover_bootstrap_if_present(ctx:Mapping[str,Any]):
    boot=ctx["bootstrap"]
    blobs={dest:None for dest in boot.FILES}
    present=[Path(x) for x in boot.FILES if Path(x).exists()
             or Path(x).is_symlink()]
    if not present and not ROOT_LEDGER.exists() and not ROOT_LEDGER.is_symlink():
        return
    need(len(present)==len(boot.FILES)
         and ROOT_LEDGER.exists() and not ROOT_LEDGER.is_symlink(),
         "A0_ATOMIC_BOOTSTRAP_PARTIAL_OR_FOREIGN")
    _,source_blobs=boot.validate_plan()
    boot.verify_targets(source_blobs)
    for path in sorted((Path(x) for x in source_blobs),reverse=True):
        need(not path.is_symlink()
             and sha(path.read_bytes())==sha(source_blobs[str(path)]),
             "A0_ATOMIC_BOOTSTRAP_FILE_CHANGED")
        path.unlink()
        fsync_parent(path.parent)
    ROOT_LEDGER.rmdir()
    fsync_parent(ROOT_LEDGER.parent)
    for path in (ROOT_HELPER,ROOT_HELPER_POLICY,ROOT_LEDGER):
        need(not path.exists() and not path.is_symlink(),
             "A0_ATOMIC_BOOTSTRAP_ROLLBACK_INCOMPLETE")


def build_recovery_context() -> dict[str,Any]:
    p=reviewed_policy(require_root=True)
    boot=load_trusted(BOOT,"a0_atomic_recovery_boot",BOOT_SHA)
    boot.validate_plan()
    initial=boot.readback()
    stage=load_trusted(SPARSE_STAGE,"a0_atomic_recovery_stage",SPARSE_SHA)
    sparse=stage.trusted_policy()
    protected=stage.protected_preflight(sparse)
    need(protected["runtime_id"]==initial["runtime_id"]
         and protected["mcp_id"]==initial["mcp_id"],
         "A0_ATOMIC_RECOVERY_PRODUCTION_DRIFT")
    source=stage._load_trusted(SOURCE_ROOT,"a0_atomic_recovery_sparse_source")
    blob=source.git_object(stage.REPO)
    original=source.source_manifest(
        CANDIDATE,blob,freeze_sha256=FREEZE_SHA,current_lkg=LKG)
    need(original.get("scope_sha256")==
         "09e35bf812c3bedd61991af669ea9a80b0a0ff5948b1d1a6edb1d70c3332c27f"
         and len(original["files"])==13,
         "A0_ATOMIC_RECOVERY_SOURCE_CHANGED")
    return {"policy":p,"bootstrap":boot,"baseline":initial,
            "stage":stage,"sparse":sparse,"source":source,"original":original}


def revert_all(ctx:Mapping[str,Any],proof:Mapping[str,str],
               rows:list[dict[str,Any]]|None=None):
    rows=rows if rows is not None else audit_rows()
    need(bool(rows) and rows[0]["owner_approval_id"]==proof["approval_id"]
         and rows[0]["signed_release_sha256"]==proof["proof_sha256"],
         "A0_ATOMIC_RECOVERY_WRONG_OWNER")
    actions={r["step"] for r in rows if r["action"]=="intent"}
    rolled={r["step"] for r in rows if r["action"]=="rollback_verified"}
    need(actions <= {0,1,2}, "A0_ATOMIC_RECOVERY_UNKNOWN_ACTION")
    if not any(r["action"]=="rollback_begin" for r in rows):
        audit_append("rollback_begin",-1,{"exact_reverse":True},proof)
    try:
        for index in (2,1,0):
            if index not in actions or index in rolled:
                continue
            if index==2:
                recover_native_if_present(ctx,proof)
            elif index==1:
                recover_source_if_present(ctx)
            elif index==0:
                recover_bootstrap_if_present(ctx)
            audit_append("rollback_verified",index,
                         {"step":index,"absent_verified":True},proof)
    except BaseException as exc:
        audit_append("requires_review",-1,
                     {"cause":type(exc).__name__},proof)
        raise AtomicRootDenied("A0_ATOMIC_FOREIGN_OR_UNVERIFIED_ROLLBACK") from exc
    audit_append("rolled_back",-1,{"original_empty_baselines":True},proof)
    return {"status":"exact_original_root_absence_restored",
            "original_owner_approval_id":proof["approval_id"]}


def execute() -> None:
    p=trusted_entry()
    with root_release_lock():
        ctx=read_root_preflight()
        proof=verify_proof(p,at=datetime.now(timezone.utc))
        audit_append("begin",-1,{"three_exact_actions":True},proof)
        try:
            audit_append("intent",0,{"scope_sha256":STEPS[0][2]},proof)
            _,blobs=ctx["bootstrap"].validate_plan()
            ctx["bootstrap"].publish(blobs,ctx["baseline"])
            ctx["bootstrap"].verify_targets(blobs)
            audit_append("installed",0,{"helper":ROOT_HELPER_SHA},proof)

            audit_append("intent",1,{"scope_sha256":STEPS[1][2]},proof)
            closed=close_source(ctx)
            audit_append("installed",1,{"file":SOURCE_MISSING_SHA},proof)

            audit_append("intent",2,{"scope_sha256":STEPS[2][2]},proof)
            packet,native,scope,manifest=load_native_exact_source(
                ctx,closed["after"])
            engine,journal,binding=native_install_under_outer_lock(
                packet,native,scope,manifest,proof)
            engine._verify_objects(scope,partial=False)
            audit_append("installed",2,{
                "native_journal_sha256":engine._events(journal)[-1]["hash"],
            },proof)
            # Health after native cannot use the *empty* target baseline gate;
            # verify protected runtime/MCP identities and full scoped objects.
            need(ctx["bootstrap"].readback()==ctx["baseline"],
                 "A0_ATOMIC_FINAL_PRODUCTION_PROTECTION_CHANGED")
            need(ctx["stage"].protected_preflight(ctx["sparse"])["runtime_id"]==
                 ctx["baseline"]["runtime_id"],
                 "A0_ATOMIC_POSTFLIGHT_RUNTIME_CHANGED")
            audit_append("committed",-1,{
                "all_three_postflights":True,
                "candidate_sha":CANDIDATE,
                "full_manifest_sha256":proof["full_manifest_sha256"],
            },proof)
        except BaseException:
            revert_all(build_recovery_context(),proof)
            raise
        print("A0_ONE_OWNER_EXACT_ATOMIC_ROOT_RELEASE=VERIFIED")
        print("THREE_ACTIONS_COMMITTED=true")
        print("TICKET_RUNTIME_OR_MCP_CHANGED=false")
        print("PRODUCTION_FREEZE_AND_HOLD_CHANGED=false")


def recover() -> None:
    p=trusted_entry()
    with root_release_lock():
        rows=audit_rows()
        if rows and rows[-1]["action"]=="rolled_back":
            print("A0_ONE_OWNER_RECOVERY=ALREADY_VERIFIED_EMPTY_NO_REPEAT")
            print("NEW_OWNER_APPROVAL_REQUIRED=false")
            return
        need(bool(rows) and rows[-1]["action"] not in {
            "committed","requires_review"},
            "A0_ATOMIC_NO_RECOVERABLE_TRANSACTION")
        # A previously authenticated Owner release is an immutable source
        # for *rollback only*, even if its 15-minute execution TTL elapsed.
        # This cannot cause a forward action or mint new approval.
        owner=read_one_user_proof()["signed_owner_proof"]["payload"]
        issued=datetime.fromisoformat(owner["issued_at"])
        proof=verify_proof(p,at=issued+timedelta(seconds=1))
        need(rows[0]["owner_approval_id"]==proof["approval_id"]
             and rows[0]["signed_release_sha256"]==proof["proof_sha256"],
             "A0_ATOMIC_RECOVERY_DIFFERENT_PROOF")
        result=revert_all(build_recovery_context(),proof,rows=rows)
        print("A0_ONE_OWNER_RECOVERY="+result["status"])
        print("NEW_OWNER_APPROVAL_REQUIRED=false")


def postflight() -> None:
    p=trusted_entry()
    with root_release_lock():
        rows=audit_rows()
        need(rows and rows[-1]["action"]=="committed",
             "A0_ATOMIC_RELEASE_NOT_COMMITTED")
        proof=verify_proof(p,at=datetime.now(timezone.utc))
        need(rows[0]["owner_approval_id"]==proof["approval_id"]
             and rows[0]["signed_release_sha256"]==proof["proof_sha256"],
             "A0_ATOMIC_FINAL_PROOF_MISMATCH")
        bootstrap=load_trusted(BOOT,"a0_atomic_post_bootstrap",BOOT_SHA)
        _,blobs=bootstrap.validate_plan()
        bootstrap.verify_targets(blobs)
        stage=load_trusted(SPARSE_STAGE,"a0_atomic_post_stage",SPARSE_SHA)
        sparse=stage.trusted_policy()
        closure=load_trusted(ROOT_HELPER,"a0_atomic_post_source",ROOT_HELPER_SHA)
        policy=closure.trusted_policy(stage)
        source=stage._load_trusted(SOURCE_ROOT,"a0_atomic_post_source_manifest")
        _,after,_=closure.exact_source_scopes(source,stage,policy)
        stage.verify_staged_source(SOURCE,after)
        ctx={"stage":stage,"sparse":sparse,"source":source}
        packet,native,scope,manifest=load_native_exact_source(ctx,after)
        engine=native.NativeStageAInstaller(production=True,owner_metadata=True,
            root_health=native.production_root_health_readback)
        engine._verify_objects(scope,partial=False)
        bound=engine._events(engine._journal(CANDIDATE))
        need(bound and bound[-1]["event"]=="verified_installed"
             and bound[-1]["owner_approval_id"]==proof["approval_id"]
             and bound[-1]["signed_proof_sha256"]==proof["proof_sha256"],
             "A0_ATOMIC_NATIVE_COMPLETE_AUDIT_DRIFT")
        bootstrap.readback()
        stage.protected_preflight(sparse)
        guard=packet.IndependentHostGuard()
        need(guard.protected_release_status().get("ready") is True
             and all(guard.core_health_evidence().get(k) is True
                     for k in ("runtime_healthy","mcp_running","worker_scan_fresh")),
             "A0_ATOMIC_FINAL_TICKET_WORKER_NOT_READY")
        verify_full_integrity()
        print("A0_ATOMIC_FULL_POSTFLIGHT=PASS")
        print("ONE_SIGNED_OWNER_RELEASE=VERIFIED")
        print("GLOBAL_PRODUCTION_FREEZE_AND_PROMOTION_HOLD=UNCHANGED")


def main() -> int:
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight",action="store_true")
    modes.add_argument("--execute",action="store_true")
    modes.add_argument("--recover",action="store_true")
    modes.add_argument("--postflight",action="store_true")
    args=parser.parse_args()
    try:
        trusted_entry()
        if args.preflight:
            with root_release_lock():
                read_root_preflight()
            print("EXACT_A0_ATOMIC_ROOT_PREFLIGHT=PASS")
            print("ROOT_WRITES_TO_PRODUCTION=false; OWNER_APPROVAL_ISSUED=false")
        elif args.execute:
            execute()
        elif args.recover:
            recover()
        else:
            postflight()
        return 0
    except (PermissionError,OSError,ValueError,KeyError,
            subprocess.SubprocessError) as exc:
        print("A0_ATOMIC_ROOT=DENIED "+type(exc).__name__+
              ":"+str(exc)[:160],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
