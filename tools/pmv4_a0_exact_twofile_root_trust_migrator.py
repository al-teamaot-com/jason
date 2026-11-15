#!/usr/bin/env python3
"""One-use exact two-file PMv4 A0 trust migration. SOURCE ONLY until signed release.

Root path is a private root:root 0400 /run installer, never this checkout.
Two existing root-owned files only; signed Owner exact manifest; original bytes
kept as rollback. No runtime, service, release pointer, breaker or provider writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from typing import Any

CANDIDATE = "8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION = "pmv4-a0-ci-policy-root-trust-twofile-migration-v1"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
STAGE = Path("/run/jason-pmv4-a0-trust-twofile-8c20")
ROOT = STAGE / "installer.py"
ARCHIVE = Path("/srv/jason/archive")
PACKAGE = ARCHIVE / ("pmv4-a0-root-trust-twofile-migration-" + CANDIDATE + ".tar")
MANIFEST = ARCHIVE / ("pmv4-a0-root-trust-twofile-migration-" + CANDIDATE + "-SIGNED-REVIEW.json")
PROOF = ARCHIVE / ("pmv4-a0-root-trust-twofile-OWNER-PROOF-" + CANDIDATE + ".json")
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
VERIFIER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
PUBLIC = Path("/etc/jason-owner-release/verified-owner-public-key.json")
RELEASE = Path("/var/lib/jason/openclaw/release-manager")
LOCK = RELEASE / "production-transaction.lock"
FREEZE = RELEASE / "production-deployment-freeze"
HOLD = RELEASE / "auto-promotion-incident-hold"
CONTROL = RELEASE / "production-control-state.json"
DRIFT = RELEASE / "production-drift.json"
JOURNAL = Path("/etc/jason-owner-release/pmv4-a0-ci-trust-twofile-8c20")
TARGETS = (
    (Path("/usr/local/lib/jason/pmv4_shadow_ci.py"), 0o444),
    (Path("/etc/jason-owner-release/pmv4-stage-a0-sparse-root-stage.json"), 0o400),
)
OLD = ("57a3fb97d95752cfb61e7956e1140a04dc09fb3d07433d41ea42f827de366139",
       "302563784c2a685b1228cf836e5756dbcf4484a3091572d8c6218301b54db710")
NEW = ("f89d714a900a241e202f7842b6bfe06e1ac0f89d15086816cb0642f266c0a4eb",
       "a83a5679714ec5225f10f7b763202d9cdacc257922fb46b7f40ffafa17dc567d")
PACKAGE_SHA = "be49db761f381b8d570773c50d9bcdd5e3248135684094461dc2596aacdab402"
SOURCE_SCOPE = "00bbf9884a1f724886be50d100a6aec2f3dfece6ec18177ca39d18768c6248e1"


class TrustMigrationDenied(PermissionError):
    pass


def need(value: bool, why: str) -> None:
    if not value:
        raise TrustMigrationDenied(why)


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def secure_read(path: Path, *, owner: int, mode: int, limit: int = 200000) -> bytes:
    need(not path.is_symlink(), "ROOT_TRUST_SYMLINK")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        m = os.fstat(fd)
        need(stat.S_ISREG(m.st_mode) and m.st_uid == owner and m.st_nlink == 1
             and stat.S_IMODE(m.st_mode) == mode and m.st_size <= limit,
             "ROOT_TRUST_SOURCE_OWNERSHIP_MODE_OR_SIZE")
        raw = os.read(fd, limit + 1)
        need(len(raw) == m.st_size, "ROOT_TRUST_SHORT_READ")
        return raw
    finally:
        os.close(fd)


def trust_entry() -> None:
    need(os.geteuid() == 0 and sys.flags.isolated == 1 and
         Path(__file__).absolute() == ROOT and not ROOT.is_symlink(),
         "ROOT_TRUST_INSTALLED_ISOLATED_ROOT_REQUIRED")
    m = STAGE.lstat()
    need(stat.S_ISDIR(m.st_mode) and m.st_uid == 0 and m.st_gid == 0
         and stat.S_IMODE(m.st_mode) == 0o700, "ROOT_TRUST_PRIVATE_STAGE")
    secure_read(ROOT, owner=0, mode=0o400)


def source_packet() -> tuple[dict[str, Any], dict[tuple[int,str],bytes]]:
    raw_manifest = secure_read(MANIFEST, owner=1000, mode=0o600, limit=20000)
    raw_archive = secure_read(PACKAGE, owner=1000, mode=0o600, limit=2000000)
    need(digest(raw_archive) == PACKAGE_SHA, "ROOT_TRUST_PACKAGE_DRIFT")
    p = json.loads(raw_manifest)
    fields = {"schema_version","action","candidate_sha","production_lkg","freeze_sha256",
              "hold_sha256","source_scope_sha256","package_sha256",
              "root_executor_sha256","original_root_hashes","replacement_root_hashes",
              "root_targets","scope_sha256","one_use","standing_authority",
              "no_services_changed","no_breaker_or_drift_mutation"}
    need(isinstance(p,dict) and set(p)==fields and p["schema_version"]=="1.0"
         and p["action"]==ACTION and p["candidate_sha"]==CANDIDATE
         and p["production_lkg"]==LKG and p["freeze_sha256"]==FREEZE_SHA
         and p["hold_sha256"]==HOLD_SHA and p["source_scope_sha256"]==SOURCE_SCOPE
         and p["package_sha256"]==PACKAGE_SHA
         and p["original_root_hashes"]==list(OLD)
         and p["replacement_root_hashes"]==list(NEW)
         and p["root_targets"]==[{"path":str(path),"mode":format(mode,"04o"),
                                  "uid":0,"gid":0} for path,mode in TARGETS]
         and p["one_use"] is True and p["standing_authority"] is False
         and p["no_services_changed"] is True
         and p["no_breaker_or_drift_mutation"] is True
         and p["root_executor_sha256"]==digest(secure_read(ROOT,owner=0,mode=0o400))
         and p["scope_sha256"]==digest(canonical({k:v for k,v in p.items()
                                                   if k!="scope_sha256"})),
         "ROOT_TRUST_REVIEWED_MANIFEST_CHANGED")
    expected = {("old",i):"rollback/"+str(path).lstrip("/")
                for i,(path,_) in enumerate(TARGETS)}
    expected.update({("new",i):"replacement/"+str(path).lstrip("/")
                     for i,(path,_) in enumerate(TARGETS)})
    allowed = set(expected.values())
    contents: dict[tuple[int,str],bytes] = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw_archive),mode="r:") as tf:
        for m in tf:
            need(m.name in allowed and m.name not in seen and m.isfile()
                 and m.uid==0 and m.gid==0 and m.mtime==0
                 and not m.issym() and not m.islnk() and not m.isdev(),
                 "ROOT_TRUST_PACKAGE_MEMBERS_CHANGED")
            seen.add(m.name)
            key=next(k for k,v in expected.items() if v==m.name)
            stage,i=key
            raw=tf.extractfile(m).read()
            need(m.mode==TARGETS[i][1]
                 and digest(raw)==(OLD[i] if stage=="old" else NEW[i]),
                 "ROOT_TRUST_PACKAGE_MEMBER_HASH_OR_MODE")
            contents[(i,stage)]=raw
    need(seen==allowed, "ROOT_TRUST_PACKAGE_INCOMPLETE")
    return p,contents


def old_baseline() -> None:
    for i,(path,mode) in enumerate(TARGETS):
        need(digest(secure_read(path,owner=0,mode=mode))==OLD[i],
             "ROOT_TRUST_OLD_FILE_DRIFT")
        m=path.parent.lstat()
        need(stat.S_ISDIR(m.st_mode) and m.st_uid==0
             and not (m.st_mode & 0o022) and not path.parent.is_symlink(),
             "ROOT_TRUST_TARGET_PARENT_UNTRUSTED")
    parent=JOURNAL.parent.lstat()
    need(stat.S_ISDIR(parent.st_mode)
         and (parent.st_uid,parent.st_gid)==(0,0)
         and not JOURNAL.parent.is_symlink()
         and not (parent.st_mode & 0o022),
         "ROOT_TRUST_AUDIT_PARENT_UNTRUSTED")
    need(not JOURNAL.exists() and not JOURNAL.is_symlink(),
         "ROOT_TRUST_ACTION_ALREADY_CLAIMED")


def invariant() -> dict[str,str]:
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "ROOT_TRUST_PRODUCTION_RELEASE_CHANGED")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA and
         digest(HOLD.read_bytes())==HOLD_SHA,"ROOT_TRUST_FREEZE_OR_HOLD_DRIFT")
    control=json.loads(CONTROL.read_bytes())
    drift=json.loads(DRIFT.read_bytes())
    need(control.get("circuit_breaker",{}).get("state")=="closed"
         and drift.get("status")=="pass" and drift.get("problems")==[],
         "ROOT_TRUST_BREAKER_OR_DRIFT_NOT_PASS")
    updated=drift.get("observed_at")
    need(isinstance(updated,str), "ROOT_TRUST_DRIFT_DATE_MISSING")
    dt=datetime.fromisoformat(updated.replace("Z","+00:00"))
    now=datetime.now(timezone.utc)
    need(dt.tzinfo is not None and -10 <= (now-dt).total_seconds() <= 180,
         "ROOT_TRUST_STALE_DRIFT")
    current=subprocess.check_output(
        ["/usr/sbin/runuser","-u","al","--","/usr/bin/gh","api",
         "repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"],
        text=True,timeout=20).strip()
    need(current==CANDIDATE, "ROOT_TRUST_PROTECTED_MAIN_CHANGED")
    return {"lkg":LKG,"freeze":FREEZE_SHA,"hold":HOLD_SHA,
            "main":current,"drift_at":updated}


def exact_owner_proof(p: dict[str,Any]) -> dict[str,str]:
    raw=secure_read(PROOF,owner=1000,mode=0o600,limit=20000)
    proof=json.loads(raw)
    need(isinstance(proof,dict) and set(proof)==
         {"schema_version","action","source_sha","scope_sha256",
          "manifest_sha256","signed_owner_proof"}
         and proof["schema_version"]=="1.0" and proof["action"]==ACTION
         and proof["source_sha"]==CANDIDATE
         and proof["scope_sha256"]==p["scope_sha256"]
         and proof["manifest_sha256"]==digest(canonical(p)),
         "ROOT_TRUST_OWNER_ENVELOPE_DRIFT")
    need(digest(VERIFIER.read_bytes())==VERIFIER_SHA,
         "ROOT_TRUST_VERIFIER_DRIFT")
    spec=importlib.util.spec_from_file_location("a0_trust_existing_owner",VERIFIER)
    need(spec is not None and spec.loader is not None,
         "ROOT_TRUST_VERIFIER_UNAVAILABLE")
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    evidence=obj.verify_exact_owner_release(
        proof["signed_owner_proof"],
        public_key=obj.read_pinned_root_owner_public_key(PUBLIC,require_root_owned=True),
        at=datetime.now(timezone.utc),
        expected_candidate_sha=CANDIDATE,expected_rollback_sha=LKG,
        expected_release_id="release-"+CANDIDATE[:16],
        expected_scope_sha256=p["scope_sha256"],
        expected_manifest_sha256=digest(canonical(p)),
        expected_freeze_sha256=FREEZE_SHA)
    need(evidence["one_release_only"] is True and
         evidence["standing_authority"] is False and
         evidence["approval_id"].startswith("owner-mcp-"),
         "ROOT_TRUST_OWNER_AUTH_NOT_ONE_SHOT")
    return {"approval_id":evidence["approval_id"],
            "signed_proof_sha256":digest(canonical(proof["signed_owner_proof"]))}


def release_lock():
    fd=os.open(LOCK,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    m=os.fstat(fd)
    need(stat.S_ISREG(m.st_mode) and m.st_uid==1000 and m.st_nlink==1
         and not m.st_mode & 0o002, "ROOT_TRUST_RELEASE_LOCK_UNTRUSTED")
    try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise TrustMigrationDenied("ROOT_TRUST_RELEASE_BUSY")
    return fd


def audit(path:Path,obj:dict[str,Any]) -> None:
    b=canonical(obj)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchown(fd,0,0)
        need(os.write(fd,b)==len(b),"ROOT_TRUST_AUDIT_WRITE_INCOMPLETE")
        os.fsync(fd)
    finally:os.close(fd)


def replace_exact(path:Path,old:bytes,new:bytes,mode:int) -> None:
    # Never interpret archive-provided paths. Two compiled targets only.
    need(digest(secure_read(path,owner=0,mode=mode))==digest(old),
         "ROOT_TRUST_CONCURRENT_FILE_CHANGE")
    temp=path.parent/(path.name+".a0-8c20-tmp")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        os.fchown(fd,0,0);os.fchmod(fd,mode)
        need(os.write(fd,new)==len(new),"ROOT_TRUST_TEMP_WRITE_INCOMPLETE")
        os.fsync(fd)
        need(digest(secure_read(temp,owner=0,mode=mode))==digest(new),
             "ROOT_TRUST_TEMP_DIGEST")
        os.replace(temp,path)
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    finally:
        os.close(fd)
        if temp.exists() and not temp.is_symlink():temp.unlink()


def rollback_exact(contents:dict[tuple[int,str],bytes]) -> None:
    for i in reversed(range(len(TARGETS))):
        path,mode=TARGETS[i]
        observed=digest(secure_read(path,owner=0,mode=mode))
        if observed==OLD[i]:continue
        need(observed==NEW[i],"ROOT_TRUST_ROLLBACK_FOREIGN_INODE_OR_BYTES")
        replace_exact(path,contents[(i,"new")],contents[(i,"old")],mode)
    old_baseline_for_recovery()


def old_baseline_for_recovery():
    for i,(path,mode) in enumerate(TARGETS):
        need(digest(secure_read(path,owner=0,mode=mode))==OLD[i],
             "ROOT_TRUST_ROLLBACK_READBACK_FAILED")


def run(mode:str) -> None:
    trust_entry()
    p,contents=source_packet()
    before=invariant()
    if mode=="--preflight":
        old_baseline()
        print("A0_TRUST_TWOFILE_ROOT_PREFLIGHT=PASS")
        print("OWNER_APPROVAL_USED=false; ROOT_WRITES=false")
        return
    lock=release_lock()
    try:
        if mode=="--postflight":
            need(JOURNAL.is_dir() and (JOURNAL/"attempt.json").is_file()
                 and (JOURNAL/"result.json").is_file(),
                 "ROOT_TRUST_POSTFLIGHT_AUDIT_MISSING")
            receipt=json.loads((JOURNAL/"result.json").read_bytes())
            need(receipt.get("status")=="success"
                 and receipt.get("candidate_sha")==CANDIDATE
                 and receipt.get("new_root_hashes")==list(NEW),
                 "ROOT_TRUST_POSTFLIGHT_RECEIPT_DRIFT")
            for i,(path,modebits) in enumerate(TARGETS):
                need(digest(secure_read(path,owner=0,mode=modebits))==NEW[i],
                     "ROOT_TRUST_POSTFLIGHT_HASH_DRIFT")
            need(invariant()==before, "ROOT_TRUST_POSTFLIGHT_PRODUCTION_DRIFT")
            print("A0_ROOT_TRUST_TWOFILE_POSTFLIGHT=PASS")
        elif mode=="--execute":
            old_baseline()
            owner=exact_owner_proof(p)
            need(invariant()==before, "ROOT_TRUST_SOURCE_CHANGED_BEFORE_WRITE")
            need(not JOURNAL.exists() and not JOURNAL.is_symlink(),
                 "ROOT_TRUST_ALREADY_AUDITED")
            JOURNAL.mkdir(mode=0o700)
            os.chown(JOURNAL,0,0)
            os.chmod(JOURNAL,0o700)
            audit(JOURNAL/"attempt.json",{"action":ACTION,
                  "candidate_sha":CANDIDATE,"scope_sha256":p["scope_sha256"],
                  "status":"exact_owner_claimed", **owner})
            try:
                for i,(path,modebits) in enumerate(TARGETS):
                    replace_exact(path,contents[(i,"old")],
                                  contents[(i,"new")],modebits)
                for i,(path,modebits) in enumerate(TARGETS):
                    need(digest(secure_read(path,owner=0,mode=modebits))==NEW[i],
                         "ROOT_TRUST_POSTFLIGHT_HASH_DRIFT")
                need(invariant()==before,
                     "ROOT_TRUST_PRODUCTION_STATE_CHANGED")
            except BaseException:
                rollback_exact(contents)
                audit(JOURNAL/"result.json",{"action":ACTION,
                      "status":"rolled_back_old_exact_bytes"})
                raise
            audit(JOURNAL/"result.json",{"action":ACTION,
                  "status":"success","candidate_sha":CANDIDATE,
                  "new_root_hashes":list(NEW)})
            print("A0_ROOT_TRUST_TWOFILE_MIGRATION=VERIFIED")
            print("PRODUCTION_RESTARTS=false; FREEZE_HOLD_CHANGED=false")
        elif mode=="--recover":
            need(JOURNAL.is_dir() and (JOURNAL/"attempt.json").is_file(),
                 "ROOT_TRUST_NO_ORIGINAL_AUDIT")
            need(not (JOURNAL/"recovery.json").exists(),
                 "ROOT_TRUST_RECOVERY_ALREADY_RECORDED")
            attempt=json.loads((JOURNAL/"attempt.json").read_bytes())
            need(attempt.get("action")==ACTION and
                 attempt.get("candidate_sha")==CANDIDATE and
                 attempt.get("scope_sha256")==p["scope_sha256"],
                 "ROOT_TRUST_RECOVERY_CLAIM_DRIFT")
            result_path=JOURNAL/"result.json"
            if result_path.exists():
                previous=json.loads(result_path.read_bytes())
                need(previous.get("action")==ACTION and previous.get("status") in
                     ("success","rolled_back_old_exact_bytes"),
                     "ROOT_TRUST_RECOVERY_FINAL_STATUS_DRIFT")
                if previous["status"]=="rolled_back_old_exact_bytes":
                    old_baseline_for_recovery()
                    print("A0_ROOT_TRUST_ALREADY_ROLLED_BACK=VERIFIED")
                    return
            rollback_exact(contents)
            audit(JOURNAL/("recovery.json" if result_path.exists() else "result.json"),
                  {"action":ACTION,"status":"rolled_back_old_exact_bytes"})
            print("A0_ROOT_TRUST_RECOVERY_TO_EXACT_OLD_BYTES=VERIFIED")
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)


def main()->int:
    if len(sys.argv)!=2 or sys.argv[1] not in ("--preflight","--execute","--recover","--postflight"):
        print("DENIED: exact mode required",file=sys.stderr);return 2
    try:run(sys.argv[1]);return 0
    except (TrustMigrationDenied,OSError,ValueError,subprocess.SubprocessError) as exc:
        print("A0_ROOT_TRUST=DENIED "+type(exc).__name__+":"+str(exc)[:150],
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
