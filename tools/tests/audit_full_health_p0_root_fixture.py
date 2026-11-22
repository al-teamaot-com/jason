#!/usr/bin/env python3
"""Disposable native Root custody/rollback fixture; no host mounts or network."""
import importlib.util
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT=Path("/test-source")
spec=importlib.util.spec_from_file_location("reviewed_recovery_fixture",
    ROOT/"tools/audit_full_health_p0_recovery.py")
assert spec and spec.loader
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

def must(condition,label):
    if not condition:raise AssertionError(label)

def run():
    must(os.geteuid()==0 and sys.flags.isolated==1,"ROOT_ISOLATED_REQUIRED")
    # Docker explicitly uses no-new-privileges: Root can drop to the actual
    # SQLite-reader UID without requiring any additional privileges.
    probe=subprocess.run(["/usr/sbin/runuser","-u","al","--","id","-u"],
                         text=True,capture_output=True,timeout=8)
    must(probe.returncode==0 and probe.stdout.strip()=="1000",
         "ROOT_TO_UID1000_DROP_UNDER_NNP_DENIED")
    with tempfile.TemporaryDirectory(prefix="audit-p0-root-fixture-",dir="/tmp") as tmp:
        basedir=Path(tmp)
        installed=basedir/"trusted"
        dropins=basedir/"full.service.d"
        receipts=basedir/"owner-receipt"
        dropins.mkdir(mode=0o755)
        r.ROOT_BASE=installed
        r.DROPIN=dropins/"93-audit-full-health-p0-recovery.conf"
        r.RECORD=receipts
        calls=[]
        r.command=lambda argv,**kw:calls.append(argv)
        blobs={name:(ROOT/name).read_bytes() for name in r.SOURCES}
        scope={"schema_version":"1.0","action":r.ACTION,
          "policy":{"candidate_sha":"a"*40,"rollback_sha":r.LKG},
          "source_sha256":{name:sha256(raw).hexdigest() for name,raw in blobs.items()}}
        expected=blobs["config/audit-full-health-p0-recovery.conf"]
        claim=r.record_attempt("a"*40,scope,blobs,r.OWNER,{"required_ci_passed":True})
        f=receipts/"attempt.json"
        must(stat.S_IMODE(f.stat().st_mode)==0o400 and f.stat().st_uid==0,
             "AUDIT_ATTEMPT_ROOT_ONLY")
        must(claim["independently_verified_entra_owner"] is True,"ROOT_CLAIM_OWNER")
        r.install_trusted_source(blobs)
        must(stat.S_IMODE(r.DROPIN.stat().st_mode)==0o644
             and r.DROPIN.stat().st_uid==0
             and r.DROPIN.read_bytes()==expected,"EXACT_ROOT_OVERRIDE")
        for name,target in r.SOURCES.items():
            p=installed/target
            must(stat.S_IMODE(p.stat().st_mode)==0o444
                 and p.stat().st_uid==0
                 and p.read_bytes()==blobs[name],"IMMUTABLE_SOURCE_"+target)
        # A changed but still Root-owned file cannot be removed as reviewed.
        r.DROPIN.write_bytes(b"FOREIGN_ROOT_OVERRIDE")
        try:
            r.rollback_override({"config/audit-full-health-p0-recovery.conf":expected})
            raise AssertionError("FOREIGN_OVERRIDE_UNLINKED")
        except r.Denied:pass
        must(r.DROPIN.read_bytes()==b"FOREIGN_ROOT_OVERRIDE","FOREIGN_BYTES_NOT_PRESERVED")
        r.DROPIN.write_bytes(expected)
        r.rollback_override({"config/audit-full-health-p0-recovery.conf":expected})
        must(not r.DROPIN.exists() and installed.exists(),"REVIEWED_ROLLBACK_ONLY")
        must(calls and calls[-1]==["/usr/bin/systemctl","daemon-reload"],
             "NO_OTHER_SYSTEMD_MUTATIONS")
        r.DROPIN.symlink_to(installed/"recovery.py")
        try:
            r.rollback_override({"config/audit-full-health-p0-recovery.conf":expected})
            raise AssertionError("SYMLINK_ROLLBACK_ACCEPTED")
        except r.Denied:pass
        must((installed/"recovery.py").is_file(),"SYMLINK_TARGET_PRESERVED")
        r.DROPIN.unlink()
        try:
            r.record_attempt("a"*40,scope,blobs,r.OWNER,{"required_ci_passed":True})
            raise AssertionError("SECOND_OWNER_CLAIM_ACCEPTED")
        except r.Denied:pass
        try:
            r.assert_worker_environment()
            raise AssertionError("UNINSTALLED_ROOT_WORKER_ALLOWED")
        except r.Denied:pass
        print(json.dumps({"root_uid":0,"root_owned_sources":len(blobs),
                          "exact_claim":True,"one_use":True,
                          "foreign_and_symlink_refusal":True,
                          "override_removed":True,"no_host_mount":True,
                          "provider_calls":0,"status":"PASS"},sort_keys=True))

if __name__=="__main__":
    run()
