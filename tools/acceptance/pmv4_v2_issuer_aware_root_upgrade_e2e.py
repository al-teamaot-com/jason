#!/usr/bin/env python3
"""Real UID0 exact two-file root upgrader end-to-end; all writes Docker tmpfs.

Requires two isolated invocations: success and failing read-only self-check.
Never mounts production root or grants Owner authority.
"""
import importlib.util
from hashlib import sha256
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import io
import tarfile
import subprocess
import shutil
import stat
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from implementation.kernel import signed_owner_release as verifier
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

mode=sys.argv[1]
assert mode in ("success","fail-check","inject-after-first-swap","inject-mid-temp-write")
assert os.geteuid()==0
lab=Path("/tmp/v2-root-upgrader-e2e")
lab.mkdir(mode=0o700)
script=lab/"reviewed-root-updater.py"
shutil.copyfile(REPO / "tools/owner_v2_issuer_aware_root_updater.py", script)
script.chmod(0o400)
spec=importlib.util.spec_from_file_location("isolated_owner_root_upgrader",script)
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
r.ROOT_RUNNER=script
# Rebuild this exact candidate package, no downloaded tar or private source.
reviewed = (REPO / "config/pmv4-stage-a0/issuer-aware-v2-root-upgrade-manifest-review.json").read_bytes()
manifest_obj = json.loads(reviewed)
assert sha256(reviewed).hexdigest() == r.MANIFEST_SHA
items = {}
for row in manifest_obj["exact_replacements"]:
    original = subprocess.check_output([
        "git", "-c", "safe.directory=" + str(REPO), "-C", str(REPO),
        "show", r.ROLLBACK + ":" + row["git_path"],
    ], timeout=15)
    updated = (REPO / row["git_path"]).read_bytes()
    assert sha256(original).hexdigest() == row["old_sha256"]
    assert sha256(updated).hexdigest() == row["new_sha256"]
    items[row["archive_old"]] = (original, int(row["mode"], 8))
    items[row["archive_new"]] = (updated, int(row["mode"], 8))
items["_metadata/owner-exact-root-replacement.json"] = (reviewed, 0o400)
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w:", format=tarfile.USTAR_FORMAT) as tar:
    for name, (data, mode_value) in items.items():
        info = tarfile.TarInfo(name)
        info.type = tarfile.REGTYPE
        info.mode = mode_value
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
assert sha256(buffer.getvalue()).hexdigest() == r.PACKAGE_SHA
r.PACKAGE = lab / "reviewed-exact-two-file-package.tar"
r.MANIFEST = lab / "reviewed-exact-two-file-manifest.json"
r.PACKAGE.write_bytes(buffer.getvalue())
r.MANIFEST.write_bytes(reviewed)
os.chown(r.PACKAGE, 1000, 1000)
os.chown(r.MANIFEST, 1000, 1000)
r.PACKAGE.chmod(0o600)
r.MANIFEST.chmod(0o640)
Path("/etc/jason-owner-release").mkdir(mode=0o755, exist_ok=True)

# Audit outputs remain at the fixed root-only /etc/jason-owner-release paths,
# which are writable *inside the Docker container only* via an isolated tmpfs.
r.LOCK=lab/"production-release-transaction.lock"
r.LOCK.write_bytes(b"")
os.chown(r.LOCK,1000,1000)
r.LOCK.chmod(0o664)
r.LEDGER=Path("/etc/jason-owner-release/owner-full-integrity-v2-repair-ledger")
r.ROOT_VERIFIER=REPO / "implementation/kernel/signed_owner_release.py"
manifest,files=r.read_manifest_package()
assert len(manifest["exact_replacements"])==2 and len(files)==4
print("EXACT_BUNDLE_TWO_FILES_OLD_NEW=PASS",flush=True)

# Create simulated originally installed trusted root files under private
# Docker tmpfs, never the actual host's /usr/local or /etc.
for row in manifest["exact_replacements"]:
    path=Path(row["root_target"])
    path.parent.mkdir(parents=True,exist_ok=True)
    path.parent.chmod(0o755)
    path.write_bytes(files[(row["root_target"],"archive_old")])
    path.chmod(int(row["mode"],8))
    r.verify_root_file(row,"old")
print("INITIAL_UID0_TRUST_OLD_HASH_MODES=PASS",flush=True)

r.LEDGER.mkdir(mode=0o700)
r.LEDGER.chmod(0o700)
key=Ed25519PrivateKey.generate()
verifier.read_pinned_root_owner_public_key=lambda *args,**kwargs:key.public_key()
r.load_verifier=lambda:verifier

def sign(candidate,rollback,scope,manifest_hash,at,number):
    return verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+number*32,
        release_id="release-"+candidate[:16],
        candidate_sha=candidate,rollback_sha=rollback,
        scope_sha256=scope,manifest_sha256=manifest_hash,
        freeze_sha256=r.FREEZE_SHA,
        verified_tenant_id=verifier.TID,
        verified_owner_oid=verifier.OWNER_OID,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[verifier.OWNER_OID],
        verified_organization_id="aot",confirmed_decision="approve",
        at=at,private_key=key,
    )

historic=sign(r.ORIGINAL_BOOTSTRAP_SHA,r.LKG,r.ORIGINAL_BOOTSTRAP_SCOPE,
              r.ORIGINAL_BOOTSTRAP_MANIFEST_SHA,
              datetime.now(timezone.utc)-timedelta(minutes=32),"a")
past={
    "schema_version":"1.0","action":r.ORIGINAL_BOOTSTRAP,
    "source_sha":r.ORIGINAL_BOOTSTRAP_SHA,
    "scope_sha256":r.ORIGINAL_BOOTSTRAP_SCOPE,
    "status":"claimed_before_root_trust_installation","owner_proof":historic,
}
receipt={
    "schema_version":"1.0","action":r.ORIGINAL_BOOTSTRAP,
    "source_sha":r.ORIGINAL_BOOTSTRAP_SHA,
    "scope_sha256":r.ORIGINAL_BOOTSTRAP_SCOPE,
    "status":"verified","ledger_directory":str(r.LEDGER),
    "approved_files":[str(r.TRUSTED_CODE),str(r.TRUSTED_POLICY)],
    "production_services_changed":False,
    "full_sqlite_scan_ran":False,
    "root_breaker_modified":False,
}
for name,doc in (
    (r.ORIGINAL_BOOTSTRAP+".attempt.json",past),
    (r.ORIGINAL_BOOTSTRAP+".result.json",receipt),
):
    file=r.LEDGER/name
    file.write_bytes(r.canonical(doc)+b"\n")
    file.chmod(0o600)
baseline=r.verify_historical_bootstrap(verifier)
assert len(baseline)==2
print("ORIGINAL_BOOTSTRAP_OWNER_PROOF_HISTORICAL_ONLY=PASS",flush=True)

owner_dir=lab/"al-approved"
owner_dir.mkdir(mode=0o700)
approved=sign(r.MERGE,r.ROLLBACK,r.SCOPE,r.MANIFEST_SHA,
              datetime.now(timezone.utc),"b")
envelope={
    "schema_version":"1.0","exact_action":r.ACTION,
    "source_sha":r.MERGE,"rollback_sha":r.ROLLBACK,
    "scope_sha256":r.SCOPE,"manifest_sha256":r.MANIFEST_SHA,
    "package_sha256":r.PACKAGE_SHA,
    "status":"OWNER_APPROVED_NOT_APPLIED",
    "signed_owner_proof":approved,
}
userfile=owner_dir/"signed-one-time-proof.json"
userfile.write_bytes(r.canonical(envelope)+b"\n")
os.chown(userfile,1000,1000)
userfile.chmod(0o600)
os.chown(owner_dir,1000,1000)
owner_dir.chmod(0o2770)
r.OWNER_DECISION=userfile
assert r.signed_owner_decision(verifier)["scope_sha256"]==r.SCOPE
print("SIGNED_FRESH_UID1000_EXACT_SCOPE_ROOT_VERIFIED=PASS",flush=True)

runtime={"jason-runtime":"simulated-fixed-runtime-id",
         "jason-mcp-pilot":"simulated-fixed-mcp-id"}
r.runtime_state=lambda:dict(runtime)
calls=[]
def mocked_root_selfcheck(argv,**kw):
    assert argv==["/usr/bin/python3","-I",
                  str(r.TRUSTED_CODE),"--check-only"]
    calls.append(tuple(argv))
    if mode=="success":
        return SimpleNamespace(returncode=0,
                               stdout="EXACT_V2_ROOT_HEALTH_PREFLIGHT=PASS\n",
                               stderr="")
    return SimpleNamespace(returncode=2,stdout="",stderr="simulated read-only failure")
r.subprocess.run=mocked_root_selfcheck
if mode=="inject-mid-temp-write":
    original_write=r.os.write
    target_blob=files[(manifest["exact_replacements"][0]["root_target"],"archive_new")]
    injected=[0]
    def fail_during_temp_write(fd,data):
        if injected[0]==0 and data==target_blob:
            injected[0]+=1
            original_write(fd,data[:max(1,len(data)//2)])
            raise OSError("SYNTHETIC_ROOT_TEMP_WRITE_INTERRUPTED")
        return original_write(fd,data)
    r.os.write=fail_during_temp_write
if mode=="inject-after-first-swap":
    original_replace=r.os.replace
    swapped=[0]
    def fail_after_real_inode_swap(source,dest):
        original_replace(source,dest)
        swapped[0]+=1
        if swapped[0]==1:
            raise OSError("SYNTHETIC_DISK_FAILURE_AFTER_ATOMIC_SWAP")
    r.os.replace=fail_after_real_inode_swap
try:
    result=r.install()
except (r.RootUpdateDenied,OSError) as error:
    if mode=="inject-mid-temp-write":
        assert isinstance(error,OSError)
        assert str(error)=="SYNTHETIC_ROOT_TEMP_WRITE_INTERRUPTED"
        assert injected[0]==1
        for row in manifest["exact_replacements"]:
            r.verify_root_file(row,"old")
            assert list(Path(row["root_target"]).parent.glob(".owner-v2-exact-replace-*"))==[]
        print("MID_TEMP_WRITE_FAILURE_REMOVES_OWN_TEMP_AND_RETAINS_OLD_ROOT=PASS",flush=True)
    elif mode=="inject-after-first-swap":
        assert isinstance(error,OSError)
        assert str(error)=="SYNTHETIC_DISK_FAILURE_AFTER_ATOMIC_SWAP"
        assert swapped[0]>=1
        for row in manifest["exact_replacements"]:
            r.verify_root_file(row,"old")
        print("FAULT_AFTER_FIRST_ATOMIC_SWAP_RESTORES_BOTH_ORIGINALS=PASS",flush=True)
    elif mode=="fail-check":
        assert str(error)=="NEW_TRUSTED_ROOT_HELPER_READ_ONLY_ACCEPTANCE_FAILED"
        assert len(calls)==1
        outcome=json.loads(r.AUDIT_RESULT.read_bytes())
        assert outcome["status"]=="failed"
        assert outcome["rollback_status"]=="original_two_root_files_verified"
        for row in manifest["exact_replacements"]:
            r.verify_root_file(row,"old")
        print("EXACT_FAILED_READONLY_CHECK_RETURNS_TO_ORIGINAL_FILES=PASS",flush=True)
    else:
        raise
else:
    assert mode=="success" and result==0
    assert len(calls)==1
    outcome=json.loads(r.AUDIT_RESULT.read_bytes())
    assert outcome["status"]=="verified"
    for row in manifest["exact_replacements"]:
        r.verify_root_file(row,"new")
    print("EXACT_SUCCESS_TWO_ROOT_REPLACEMENTS=PASS",flush=True)
assert r.verify_historical_bootstrap(verifier)==baseline
print("ROOT_BOOTSTRAP_LEDGER_UNCHANGED=PASS",flush=True)
assert r.AUDIT_ATTEMPT.exists() and r.AUDIT_RESULT.exists()
print("ONE_SHOT_CLAIM_BEFORE_MUTATION_AND_RESULT=PASS",flush=True)
print("REAL_PRODUCTION_MOUNTS_AND_CREDENTIALS_USED=ZERO",flush=True)
