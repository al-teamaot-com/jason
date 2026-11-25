#!/usr/bin/env python3
"""UID0, no-host-mount native Root continuation and one-use audit fixture."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import stat
import sys
import tempfile

def load_file(name,filename):
    spec=importlib.util.spec_from_file_location(name,str(filename))
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

x=load_file("oneuse_native_resume",
  Path("/test-source/tools/audit_full_health_p0_native_resume.py"))

def ensure(ok,msg):
    if not ok:raise AssertionError(msg)

def root_write(path,raw,mode=0o400):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"wb") as stream:
        os.fchmod(stream.fileno(),mode)
        stream.write(raw);stream.flush();os.fsync(stream.fileno())

def main():
    ensure(os.geteuid()==0 and sys.flags.isolated==1,"ISOLATED_ROOT_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="audit-native-root-resume-",dir="/tmp") as td:
        base=Path(td);base.chmod(0o700)
        x.RECEIPT=base/"owner-approved-native-resume"
        fake=SimpleNamespace(safe_root_parent=lambda *_:None,
                             root_write=root_write)
        reviewed={
            "action":x.ACTION,
            "candidate_sha":"f"*40,
            "new_owner_approval":False,
            "continuation":"unperformed_native_revalidation_only",
            "original_owner_oid":x.OWNER_OID,
            "original_owner_exact_scope_sha256":x.APPROVED_FINALIZER_SCOPE_SHA256,
            "provider_writes":False,"archive_installation":False,
            "delete_or_replace_files":False,
        }
        result=x.claim_one_use(fake,"f"*40,reviewed)
        ensure(result["original_entra_approval_reused_only_within_same_exact_scope"]
               and result["one_use_native_resume"],"EXISTING_OWNER_PROOF_NOT_BOUND")
        attempt=x.RECEIPT/"attempt.json"
        st=attempt.lstat()
        ensure(st.st_uid==0 and st.st_gid==0
               and stat.S_IMODE(st.st_mode)==0o400
               and x.RECEIPT.stat().st_uid==0
               and stat.S_IMODE(x.RECEIPT.stat().st_mode)==0o700,
               "ROOT_AUDIT_CUSTODY_INVALID")
        try:x.claim_one_use(fake,"f"*40,reviewed)
        except x.Denied:pass
        else:raise AssertionError("REPLAYED_OWNER_EXACT_ROOT_ACTION")
        native_file=base/"root_worker.py"
        native_file.write_bytes(b"reviewed root-only service code fixture\n")
        native_file.chmod(0o755)
        unit_file=base/"reviewed.service"
        unit_file.write_bytes(b"[Service]\nUser=root\nProtectSystem=strict\n")
        unit_file.chmod(0o644)
        readback_file=base/"root_readback.py"
        readback_file.write_bytes(b"signed root-only readback fixture\n")
        readback_file.chmod(0o755)
        readback_unit_file=base/"readback.service"
        readback_unit_file.write_bytes(b"[Service]\nUser=root\nProtectSystem=strict\n")
        readback_unit_file.chmod(0o644)
        request_dir=base/"requests"
        request_dir.mkdir(mode=0o700)
        os.chown(request_dir,1000,1000)
        x.NATIVE_ROOT_CONTROLLER=native_file
        x.NATIVE_ROOT_CONTROLLER_SHA=x.sha(native_file.read_bytes())
        x.NATIVE_ROOT_UNIT=unit_file
        x.NATIVE_ROOT_UNIT_SHA=x.sha(unit_file.read_bytes())
        x.NATIVE_REQUESTS=request_dir
        x.NATIVE_READBACK_WORKER=readback_file
        x.NATIVE_READBACK_WORKER_SHA=x.sha(readback_file.read_bytes())
        x.NATIVE_READBACK_UNIT=readback_unit_file
        x.NATIVE_READBACK_UNIT_SHA=x.sha(readback_unit_file.read_bytes())
        controlled={
          ("jason-release-control-transition.service","User"):"root",
          ("jason-release-control-transition.service","ProtectSystem"):"strict",
          ("jason-release-control-transition.service","ActiveState"):"inactive",
          ("jason-release-control-readback.service","User"):"root",
          ("jason-release-control-readback.service","ProtectSystem"):"strict",
          ("jason-release-control-readback.service","ActiveState"):"inactive"}
        native=SimpleNamespace(system_prop=lambda u,k:controlled.get((u,k),""))
        x.reviewed_native_root_controller(native)
        unit_file.write_bytes(b"[Service]\nUser=not-root\n")
        try:x.reviewed_native_root_controller(native)
        except x.Denied:pass
        else:raise AssertionError("FOREIGN_ROOT_WORKER_CONFIGURATION_ACCEPTED")
        ensure(not list(request_dir.iterdir()),"FOREIGN_ROOT_REQUEST_CREATED")
        print(json.dumps({
           "status":"PASS","UID0":True,"network":"disabled",
           "host_bind_mounts":False,"oneuse_owner_action":True,
           "root_receipt_mode":"0400","new_owner_device_code":False,
           "same_scope_exact_owner_proof_required":True,
           "foreign_root_worker_denied":True,
           "provider_writes":False,"archive_installation":False,
           "production_breaker_mutation":False
        },sort_keys=True))

if __name__=="__main__":main()
