#!/usr/bin/env python3
"""Signed, one-use root installer for independent controller, without MCP swap.

Source-only until GitHub-protected merge and a SHA-pinned isolated sudo launch.
No financial scheduler activation, provider writes or existing service restarts.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ACTION = "install-independent-component-controller-no-mcp-swap-20261117"
PREVIOUS_SCOPE = "ba13f1cf455b84ace182aaea16ba4c2112d0c98009bc2ed2bfe6387b2d70ed93"
SOURCE_CONTROLLER = "675b99e73c33c228a8531c2797eb3db53c399ad8"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
FREEZE_HASH = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
CONTROL_STATE = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
DRIFT_STATE = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
TRUST = Path("/opt/jason/independent-component-release/trusted")
ROOT = TRUST.parent
STATE = Path("/var/lib/jason/independent-component-release")
PROFILE = Path("/etc/jason/independent-component-release/host-profiles.json")
LEDGER = Path("/etc/jason-owner-release/independent-component-control-install-ledger")
OWNER_LIB = Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_LIB_HASH = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OWNER_KEY = Path("/etc/jason-owner-release/verified-owner-public-key.json")
SOURCE_FILE = "root-installer.py"
PINNED = {
    "implementation/kernel/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "implementation/kernel/signed_owner_release.py": "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3",
    "tools/independent_component_host_adapter.py": "36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce",
    "tools/independent_component_release.py": "1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7",
    "tools/independent_component_release_root.py": "e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324",
    "tools/pmv4_host_release_guard.py": "223cc0dca981461cb93782afad5804efa0740a06b3dd51becf20bbc856371bfc",
    "host-profile.json": "f457aedc36572b6ff3d01b57a9f9a7e19f14fc45d1fda24e4f9d5caf6489fa3c",
}
PROTECTED = ("jason-runtime", "jason-mcp-pilot", "jason-pmv4-shadow-gateway",
             "jason-teams-gateway", "openbao")
LEGACY_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
OWNER_OUTBOX = Path("/var/lib/jason/openclaw/release-manager")
FIN_STATE = Path("/var/lib/jason/financial-statements")
STAGE_ROOT = Path("/home/al/.local/share/jason")
STAGE_UID = 1000

class Denied(PermissionError):
    pass

def need(cond, reason):
    if not cond:
        raise Denied(reason)

def digest(raw):
    return sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def load_stage(directory, *, with_proof):
    need(directory.parent == STAGE_ROOT
         and re.fullmatch(r"component-controller-install-[0-9a-f]{12}", directory.name)
         and directory.is_dir() and not directory.is_symlink(),
         "INSTALL_STAGE_NOT_APPROVED")
    s = directory.lstat()
    need(s.st_uid == STAGE_UID and stat.S_IMODE(s.st_mode) == 0o700,
         "INSTALL_STAGE_UNTRUSTED")
    names = {"manifest.json", SOURCE_FILE, *PINNED}
    if with_proof: names.add("owner-proof.json")
    elif (directory / "owner-proof.json").exists(): names.add("owner-proof.json")
    children = list(directory.rglob("*"))
    for child in children:
        if child.is_dir():
            meta = child.lstat()
            need(not child.is_symlink() and meta.st_uid == STAGE_UID
                 and stat.S_IMODE(meta.st_mode) == 0o700,
                 "INSTALL_STAGE_DIRECTORY_UNTRUSTED")
    need({x.relative_to(directory).as_posix() for x in children if x.is_file()} == names,
         "INSTALL_STAGE_EXTRA_FILES")
    blobs = {}
    for name in names:
        p = directory / name
        s = p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(s.st_mode) and s.st_nlink == 1
             and s.st_uid == STAGE_UID and stat.S_IMODE(s.st_mode) == 0o400
             and s.st_size <= 150000, "INSTALL_STAGE_FILE_UNTRUSTED")
        blobs[name] = p.read_bytes()
    manifest = json.loads(blobs["manifest.json"])
    need(set(manifest) == {"action","schema_version","source_sha","rollback_sha",
         "controller_sha","prior_authorization_scope_sha256","freeze_sha256",
         "mcp_baseline_image","new_mcp_image_deployed","financial_scheduler_started",
         "one_use","root_source_sha256","files_sha256","scope_sha256"}
         and manifest["action"] == ACTION and manifest["schema_version"] == "1.0"
         and re.fullmatch("[a-f0-9]{40}", manifest["source_sha"])
         and manifest["rollback_sha"] == LKG
         and manifest["controller_sha"] == SOURCE_CONTROLLER
         and manifest["prior_authorization_scope_sha256"] == PREVIOUS_SCOPE
         and manifest["freeze_sha256"] == FREEZE_HASH
         and manifest["mcp_baseline_image"] == MCP_IMAGE
         and manifest["new_mcp_image_deployed"] is False
         and manifest["financial_scheduler_started"] is False
         and manifest["one_use"] is True, "INSTALL_SCOPE_DENIED")
    unsigned = dict(manifest)
    unsigned.pop("scope_sha256")
    need(manifest["scope_sha256"] == digest(canonical(unsigned)),
         "INSTALL_SCOPE_HASH_MISMATCH")
    hashes = manifest["files_sha256"]
    need(isinstance(hashes, dict) and set(hashes) == set(PINNED)
         and all(hashes[k] == PINNED[k] == digest(blobs[k]) for k in PINNED)
         and manifest["root_source_sha256"] == digest(blobs[SOURCE_FILE]),
         "INSTALL_UNREVIEWED_SOURCE")
    return manifest, blobs

def verify_owner(directory, manifest):
    m = OWNER_LIB.lstat()
    need(m.st_uid == 0 and not OWNER_LIB.is_symlink()
         and stat.S_ISREG(m.st_mode) and not (m.st_mode & 0o022)
         and digest(OWNER_LIB.read_bytes()) == OWNER_LIB_HASH,
         "INSTALL_OWNER_VERIFIER_NOT_PINNED")
    spec = importlib.util.spec_from_file_location("pinned_owner_installer", OWNER_LIB)
    need(spec is not None and spec.loader is not None, "INSTALL_SIGNER_MISSING")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    public = mod.read_pinned_root_owner_public_key(OWNER_KEY, require_root_owned=True)
    signed = json.loads((directory / "owner-proof.json").read_bytes())
    need(set(signed) == {"schema_version","action","manifest_sha256","signed_owner_proof"}
         and signed["schema_version"] == "1.0" and signed["action"] == ACTION
         and signed["manifest_sha256"] == digest(canonical(manifest)),
         "INSTALL_OWNER_NOT_EXACT")
    proof = mod.verify_exact_owner_release(
        signed["signed_owner_proof"], public_key=public,
        expected_candidate_sha=manifest["source_sha"], expected_rollback_sha=LKG,
        expected_release_id="release-"+manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=digest(canonical(manifest)),
        expected_freeze_sha256=FREEZE_HASH, at=datetime.now(timezone.utc))
    return str(proof["approval_id"])

def capture_protected():
    need(Path("/opt/jason/current").resolve(strict=True).name == LKG,
         "INSTALL_RELEASE_POINTER_CHANGED")
    need(digest(FREEZE.read_bytes()) == FREEZE_HASH,
         "INSTALL_FROZEN_STATE_CHANGED")
    c = json.loads(CONTROL_STATE.read_bytes())
    d = json.loads(DRIFT_STATE.read_bytes())
    need(c.get("circuit_breaker",{}).get("state") == "closed"
         and d.get("status") == "pass" and d.get("problems") == [],
         "INSTALL_PROTECTED_BREAKER_OPEN")
    observed={}
    for name in PROTECTED:
        row = json.loads(subprocess.check_output(
            ["docker","inspect",name], text=True, timeout=15))[0]
        need(row["State"]["Running"], "INSTALL_PROTECTED_SERVICE_DOWN")
        observed[name]=(row["Id"],row["Image"],row["State"]["StartedAt"])
    need(observed["jason-mcp-pilot"][1] == MCP_IMAGE,
         "INSTALL_MCP_LKG_DRIFT")
    need(not any(p.exists() or p.is_symlink() for p in
             (ROOT,PROFILE.parent,STATE,LEDGER,FIN_STATE,
              OWNER_OUTBOX/"independent-component-offers",
              OWNER_OUTBOX/"independent-component-owner-approvals")),
         "INSTALL_ALREADY_PRESENT_OR_PARTIAL")
    return observed

def locks():
    handles=[]
    for path,uid in ((LEGACY_LOCK,1000),(PMV4_LOCK,0)):
        need(path.is_file() and not path.is_symlink(), "INSTALL_RELEASE_LOCK_MISSING")
        fd=os.open(path, os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        s=os.fstat(fd)
        need(s.st_uid==uid and stat.S_ISREG(s.st_mode)
             and not (s.st_mode & 0o002), "INSTALL_RELEASE_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        handles.append(fd)
    return handles

def mkdir(path, uid, mode, created):
    need(not path.exists() and not path.is_symlink(),
         "INSTALL_TARGET_PREEXISTS")
    path.mkdir(mode=mode)
    created.append(path)
    os.chown(path,uid,uid if uid==1000 else 0)
    os.chmod(path,mode)

def put(path, blob, mode, created):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),mode)
    with os.fdopen(fd,"wb") as out:
        out.write(blob)
        out.flush()
        os.fsync(out.fileno())
    created.append(path)
    need(digest(path.read_bytes()) == digest(blob),
         "INSTALL_DESTINATION_READBACK_CHANGED")

def install(blobs, created):
    mkdir(ROOT,0,0o755,created)
    mkdir(TRUST,0,0o755,created)
    for name in ("implementation","tools","implementation/kernel"):
        mkdir(TRUST/name,0,0o755,created)
    for name in PINNED:
        if name=="host-profile.json":continue
        put(TRUST/name,blobs[name],0o444,created)
    mkdir(PROFILE.parent,0,0o755,created)
    put(PROFILE,blobs["host-profile.json"],0o444,created)
    mkdir(STATE,0,0o700,created)
    for name in ("releases","receipts","control","active"):
        mkdir(STATE/name,0,0o700,created)
    put(STATE/"control/component-release.lock",b"component-release-control-v1\n",0o600,created)
    mkdir(FIN_STATE,1000,0o700,created)
    for name in ("independent-component-offers",
                 "independent-component-owner-approvals"):
        mkdir(OWNER_OUTBOX/name,1000,0o700,created)

def rollback(created):
    for p in reversed(created):
        if p.is_dir():p.rmdir()
        else:p.unlink()

def record(name, value):
    payload=json.dumps(value,sort_keys=True,indent=2).encode()+b"\n"
    fd=os.open(LEDGER/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())

def execute(directory):
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "INSTALL_ISOLATED_ROOT_REQUIRED")
    manifest,blobs=load_stage(directory,with_proof=True)
    need(digest(Path(__file__).read_bytes()) == manifest["root_source_sha256"],
         "INSTALL_EXECUTED_SOURCE_HASH_DRIFT")
    owner_id=verify_owner(directory,manifest)
    baseline=capture_protected()
    held=[]
    created=[]
    try:
        held=locks()
        capture_protected()
        mkdir(LEDGER,0,0o700,created)
        receipt={"action":ACTION,"scope_sha256":manifest["scope_sha256"],
                 "source_sha":manifest["source_sha"],"owner_approval_id":owner_id,
                 "state":"started","mcp_swapped":False,
                 "financial_scheduler_started":False,
                 "at":datetime.now(timezone.utc).isoformat()}
        record("attempt.json",receipt)
        install(blobs,created)
        after=capture_running()
        need(after==baseline and digest(FREEZE.read_bytes())==FREEZE_HASH,
             "INSTALL_PROTECTED_BASELINE_DRIFT")
        receipt["state"]="installed_disabled_verified"
        receipt["finished_at"]=datetime.now(timezone.utc).isoformat()
        record("result.json",receipt)
    except BaseException:
        receipt = locals().get("receipt", {"action":ACTION,"state":"failed"})
        if LEDGER.exists() and (LEDGER/"attempt.json").exists():
            try:
                rollback([p for p in created if p != LEDGER])
                receipt["rollback"]="verified"
            except BaseException:
                receipt["rollback"]="incomplete_fail_closed"
            receipt["state"]="failed"
            receipt["finished_at"]=datetime.now(timezone.utc).isoformat()
            record("result.json",receipt)
        raise
    finally:
        for fd in reversed(held):os.close(fd)
    print("INDEPENDENT_COMPONENT_ROOT_CONTROL=INSTALLED_DISABLED_VERIFIED")
    print("MCP_AND_PROTECTED_SERVICES_UNCHANGED=True")
    print("FINANCIAL_SCHEDULER_NOT_STARTED=True")
    print("FREEZE_UNCHANGED=True")

def capture_running():
    found={}
    for name in PROTECTED:
        x=json.loads(subprocess.check_output(["docker","inspect",name],
                                             text=True,timeout=15))[0]
        need(x["State"]["Running"],"INSTALL_PROTECTED_SERVICE_DOWN")
        found[name]=(x["Id"],x["Image"],x["State"]["StartedAt"])
    return found

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--packet",type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only",action="store_true")
    group.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if args.check_only:
        load_stage(args.packet,with_proof=False)
        print("INSTALL_SOURCE_BUNDLE_PREFLIGHT=PASS")
        print("ROOT_MUTATION=False")
    else: execute(args.packet)

if __name__=="__main__":
    try:main()
    except (Denied,OSError,ValueError) as exc:
        print("INDEPENDENT_INSTALL_DENIED:"+str(exc)[:150],file=sys.stderr)
        raise SystemExit(2)
