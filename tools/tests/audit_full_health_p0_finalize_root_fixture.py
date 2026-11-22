#!/usr/bin/env python3
"""Disposable Root finalization fixture, no host mounts, no network, no native actions."""
import importlib.util
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace

SRC=Path("/test-source/tools")
def load(filename,name):
    spec=importlib.util.spec_from_file_location(name,SRC/filename)
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

f=load("audit_full_health_p0_finalize.py","native_finalizer")
original=load("audit_full_health_p0_recovery.py","native_original")

def need(test,msg):
    if not test:raise AssertionError(msg)

def build(root, *,changed=False):
    receipt=root/"receipt";receipt.parent.mkdir(mode=0o700,exist_ok=True)
    temporary=root/"93-audit-full-health-p0-recovery.conf"
    temporary.write_bytes(b"FOREIGN" if changed else b"EXACT-REVIEWED-93")
    temporary.chmod(0o644)
    full=root/"full.json";full.write_text('{"status":"pass"}');full.chmod(0o600)
    release=root/"release";release.mkdir(mode=0o700)
    control=release/"production-control-state.json"
    control.write_text(json.dumps({"circuit_breaker":{"state":"open"}}))
    control.chmod(0o600)
    events=[]
    f.RECEIPT=receipt
    f.call=lambda argv,*args,**kw:events.append(list(argv))
    def verify_base(r,claim):
        need(not temporary.exists(),"95_OLD_OVERRIDE_STILL_PRESENT")
        events.append(["existing-native-92-checked"])
    f.ensure_native_original=verify_base
    def actual_native(approved):
        need(not temporary.exists(),"BREAKER_BEFORE_CLEANUP_DENIED")
        data=json.loads(control.read_bytes())
        data["circuit_breaker"]={"state":"closed",
          "reason":"authoritative_health_revalidated"}
        control.write_text(json.dumps(data))
        events.append(["existing-native-breaker-three-drift-proofs"])
        return ["a","b","c"]
    r=SimpleNamespace(
       safe_root_parent=original.safe_root_parent,root_write=original.root_write,
       root_read=original.root_read,DROPIN=temporary,FULL=full,RELEASE=release,
       verify_full_after=lambda *_:{"status":"pass"},
       after_full_native_revalidation=actual_native)
    scope={"action":f.ACTION,
           "exact_temporary_dropin_sha256":sha256(b"EXACT-REVIEWED-93").hexdigest(),
           "full_integrity_proof_sha256":sha256(full.read_bytes()).hexdigest()}
    return r,scope,events,temporary,receipt

def run():
    need(os.geteuid()==0 and sys.flags.isolated==1,"ISOLATED_ROOT_ONLY")
    with tempfile.TemporaryDirectory(prefix="audit-full-health-finalize-",dir="/tmp") as td:
        root=Path(td);root.chmod(0o700)
        r,sc,ev,temporary,receipt=build(root/"success")
        claim=f.claim_one_use(r,"a"*40,sc,f.OWNER)
        record=receipt/"attempt.json"
        need(record.is_file() and record.stat().st_uid==0
             and stat.S_IMODE(record.stat().st_mode)==0o400,
             "ROOT_OWNER_CLAIM_NOT_IMMUTABLE")
        need(claim["independently_verified_entra_owner"] is True,
             "EXACT_OWNER_CONFIRMATION_NOT_RECORDER")
        try:f.claim_one_use(r,"a"*40,sc,f.OWNER)
        except f.Denied:pass
        else:raise AssertionError("ONE_USE_CLAIM_REPLAY_ALLOWED")
        f.finalize(r,claim,"2026-11-22T11:35:56+00:00")
        need(not temporary.exists(),"REVIEWED_TEMPORARY_OVERRIDE_NOT_REMOVED")
        need(ev==[
            ["/usr/bin/systemctl","daemon-reload"],
            ["/usr/bin/systemctl","reset-failed",f.FULL_UNIT],
            ["existing-native-92-checked"],
            ["existing-native-breaker-three-drift-proofs"]],
             "SCOPE_EXPANDED_TO_UNAPPROVED_SYSTEMD_ACTION")
        accepted=receipt/"result.json"
        data=json.loads(accepted.read_bytes())
        need(data["status"]=="verified"
             and data["native_breaker_closed"] is True
             and data["full_integrity_verified"] is True
             and data["database_modified"] is False
             and data["archive_migration"] is False
             and accepted.stat().st_uid==0
             and stat.S_IMODE(accepted.stat().st_mode)==0o400,
             "ACCEPTANCE_PROOF_MISSING")
        r,sc,ev,temporary,receipt=build(root/"foreign",changed=True)
        claim=f.claim_one_use(r,"b"*40,sc,f.OWNER)
        try:f.finalize(r,claim,"2026-11-22T11:35:56+00:00")
        except f.Denied:pass
        else:raise AssertionError("FOREIGN_ROOT_OVERRIDE_WAS_ACCEPTED")
        need(temporary.read_bytes()==b"FOREIGN" and not ev,
             "FOREIGN_ROOT_BYTES_CHANGED")
        denied=json.loads((receipt/"result.json").read_bytes())
        need(denied["status"]=="failed"
             and denied["native_breaker_closed"] is False
             and denied["full_integrity_verified"] is True,
             "FOREIGN_OVERRIDE_FABRICATED_BREAKER")
        temporary.unlink()
        temporary.symlink_to(root/"success/full.json")
        try:f.finalize(r,claim,"2026-11-22T11:35:56+00:00")
        except (f.Denied,FileExistsError):pass
        else:raise AssertionError("SYMLINK_PROOF_BYPASS")
        need((root/"success/full.json").exists(),"SYMLINK_TARGET_CHANGED")
        print(json.dumps({"isolated_root":True,"no_host_mounts":True,
          "root_immutable_one_use_claim":True,
          "exact_temporary_override_removed":True,
          "foreign_and_symlink_refused":True,
          "genuine_native_breaker_required":True,
          "database_writes":False,"provider_calls":0,"status":"PASS"},
          sort_keys=True))

if __name__=="__main__":run()
