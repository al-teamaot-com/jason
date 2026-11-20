#!/usr/bin/env python3
"""Stage E root bootstrap *adapter*, not a second release engine.

A host administrator must first install and verify this COMPLETE source bundle
at /usr/local/lib/jason/pmv4-e-bootstrap/trusted with root:root 0444 files
and 0555 directories, plus fixed 0700 root journals, through an existing
authorized bootstrap boundary. Source checkouts are never root authority.

The original signed bootstrap phase validates one short-lived authenticated
Entra Owner approval, original source/CI, frozen state and host locks, then
allows ONLY immutable inert source/root-manifest installation. The already
installed signed native release ledger separately rechecks the SAME proof
before six-unit actions. No Docker, provider, restart, reboot or unfreeze.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types

TRUST=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted")
ENTRY=TRUST/"tools/pmv4_e_root_bootstrap_once.py"
NATIVE=Path("/opt/jason/independent-component-release/trusted")
SOURCE_REVIEW=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
RELEASES=Path("/opt/jason/releases")
NATIVE_RECORDS=Path("/var/lib/jason/independent-component-release/releases")
NATIVE_RECEIPTS=Path("/var/lib/jason/independent-component-release/receipts")
BOOTSTRAP_JOURNAL=Path("/var/lib/jason/independent-component-release/stage-e-bootstrap")
FINAL_ENTRY=Path("/opt/jason/pmv4-e-trusted/tools/pmv4_e_native_root_entry.py")
SHA40=re.compile(r"^[0-9a-f]{40}$")
PINNED_NATIVE={
    "tools/independent_component_release.py":"1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7",
    "tools/independent_component_host_adapter.py":"36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce",
    "tools/independent_component_release_root.py":"e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324",
    "implementation/kernel/signed_owner_release.py":"f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3",
}


class StageERootBootstrapDenied(PermissionError):
    pass


def need(ok:bool,code:str)->None:
    if not ok:
        raise StageERootBootstrapDenied("PMV4_E_ROOT_BOOTSTRAP_"+code)


def checked_root_dir(path:Path,*,mode:int|None=None)->None:
    try:
        m=path.lstat()
        need(not path.is_symlink() and stat.S_ISDIR(m.st_mode)
             and m.st_uid==m.st_gid==0 and m.st_mode&0o022==0
             and (mode is None or stat.S_IMODE(m.st_mode)==mode),
             "TRUSTED_ROOT_DIRECTORY_CHANGED")
    except OSError as exc:
        raise StageERootBootstrapDenied(
            "PMV4_E_ROOT_BOOTSTRAP_DIRECTORY_UNAVAILABLE") from exc


def checked_root_file(path:Path,expected:str|None=None)->bytes:
    try:
        m=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(m.st_mode)
             and m.st_uid==m.st_gid==0 and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==0o444
             and 0<m.st_size<1000000,
             "ROOT_FILE_NOT_PINNED")
        data=path.read_bytes()
        need(len(data)==m.st_size and
             (expected is None or sha256(data).hexdigest()==expected),
             "ROOT_FILE_BYTES_CHANGED")
        return data
    except OSError as exc:
        raise StageERootBootstrapDenied(
            "PMV4_E_ROOT_BOOTSTRAP_FILE_UNAVAILABLE") from exc


def bind_original_native()->None:
    """Refuse mutable Python imports; original generic native is first."""
    need(os.geteuid()==0 and Path(__file__)==ENTRY
         and Path(__file__).resolve()==ENTRY,
         "CANONICAL_UID0_BOOTSTRAP_INSTALL_REQUIRED")
    checked_root_file(ENTRY)
    for root in (TRUST,NATIVE):
        checked_root_dir(root)
        checked_root_dir(root/"tools")
        checked_root_dir(root/"implementation")
        checked_root_dir(root/"implementation/kernel")
    for name,digest in PINNED_NATIVE.items():
        checked_root_file(NATIVE/name,digest)
    need(not any(
        name=="tools" or name.startswith("tools.")
        or name=="implementation" or name.startswith("implementation.")
        for name in sys.modules),
        "AMBIENT_UNTRUSTED_MODULE_ALREADY_LOADED")
    for name in ("tools","implementation","implementation.kernel"):
        original=NATIVE.joinpath(*name.split("."))
        staged=TRUST.joinpath(*name.split("."))
        pkg=types.ModuleType(name)
        pkg.__package__=name
        pkg.__path__=[str(original),str(staged)]
        pkg.__spec__=None
        sys.modules[name]=pkg
        if "." in name:
            parent=sys.modules[name.rsplit(".",1)[0]]
            setattr(parent,name.rsplit(".",1)[1],pkg)


def candidate_arg(value:str)->str:
    need(type(value) is str and SHA40.fullmatch(value) is not None,
         "EXACT_CANDIDATE_SHA_REQUIRED")
    return value


def read_offer(candidate:str,packet,*,owner_request=None):
    folder=ARTIFACTS/("pmv4-e-source-only-"+candidate)
    m=folder.lstat()
    need(not folder.is_symlink() and stat.S_ISDIR(m.st_mode)
         and m.st_uid==m.st_gid==1000
         and stat.S_IMODE(m.st_mode)==0o700,
         "OWNER_REVIEWED_ARTIFACT_NOT_PRIVATE")
    out={}
    files=("manifest.json","source-scope.json")
    if owner_request is None:
        files+=("owner-proof.json",)
    for name in files:
        p=folder/name
        try:
            x=p.lstat()
        except FileNotFoundError as exc:
            reason=("OWNER_PROOF_MISSING" if name=="owner-proof.json"
                    else "OWNER_REVIEW_FILE_MISSING:"+name)
            raise StageERootBootstrapDenied(
                "PMV4_E_ROOT_BOOTSTRAP_"+reason) from exc
        need(not p.is_symlink() and stat.S_ISREG(x.st_mode)
             and x.st_uid==x.st_gid==1000
             and x.st_nlink==1 and stat.S_IMODE(x.st_mode)==0o400
             and 0<x.st_size<1000000,
             "OWNER_REVIEW_FILE_IDENTITY_DRIFT")
        try:out[name]=json.loads(p.read_bytes())
        except (ValueError,TypeError,UnicodeDecodeError) as exc:
            raise StageERootBootstrapDenied(
                "PMV4_E_ROOT_BOOTSTRAP_OWNER_RECORD_INVALID") from exc
        need(type(out[name]) is dict,"OWNER_RECORD_NOT_OBJECT")
    if owner_request is not None:
        need(type(owner_request) is dict
             and owner_request.get("candidate_sha")==candidate,
             "FORWARDED_OWNER_REQUEST_CANDIDATE_MISMATCH")
        out["owner-proof.json"]=owner_request
    need(out["manifest.json"].get("candidate_sha")==candidate,
         "OWNER_RELEASE_MANIFEST_CHANGED")
    return out


def safe_release_records(candidate:str,reviewed:dict,packet)->None:
    """Seal only the EXACT two root-native manifest files, not a release."""
    checked_root_dir(NATIVE_RECORDS)
    dest=NATIVE_RECORDS/candidate
    temp=NATIVE_RECORDS/("."+candidate+".pmv4-e-prestage")
    need(not dest.exists() and not dest.is_symlink()
         and not temp.exists() and not temp.is_symlink(),
         "NATIVE_RELEASE_RECORD_ALREADY_PRESENT")
    temp.mkdir(mode=0o700)
    for filename,key in (("manifest.json","manifest"),
                         ("source-scope.json","source_scope")):
        p=temp/filename
        data=packet.canonical(reviewed[key])
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
                   getattr(os,"O_NOFOLLOW",0),0o444)
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        # The independently installed Stage E attestor and final native
        # entry both require root-owned 0444 release records; a 0400
        # bootstrap artifact would pass the writer but fail preflight.
        p.chmod(0o444)
        identity=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(identity.st_mode)
             and identity.st_nlink==1
             and stat.S_IMODE(identity.st_mode)==0o444,
             "NATIVE_MANIFEST_IDENTITY_OR_MODE_CHANGED")
        need(p.read_bytes()==data,
             "NATIVE_MANIFEST_DURABLE_READBACK_CHANGED")
    temp.chmod(0o555)
    os.replace(temp,dest)
    fd=os.open(NATIVE_RECORDS,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    need({p.name for p in dest.iterdir()}==
         {"manifest.json","source-scope.json"},
         "NATIVE_RELEASE_RECORD_INVENTORY_DRIFT")


def native_promotion(candidate:str,*,packet,request:dict,
                     forwarded:bool,runner=None)->dict:
    """Pass the same proof to the independently verifying native ledger."""
    command=[
        "/usr/bin/python3","-I","-B",str(FINAL_ENTRY),
        "--candidate-sha",candidate,"--promote",
    ]
    native_input=None
    if forwarded:
        command.append("--owner-request-stdin")
        native_input=packet.canonical(request).decode("utf-8")
    runner=runner or subprocess.run
    result=runner(
        command,cwd="/",env={"PATH":"/usr/bin:/bin"},check=False,
        input=native_input,capture_output=True,text=True,timeout=480)
    need(result.returncode==0,
         "ORIGINAL_SIGNED_NATIVE_PROMOTION_FAILED_SEE_ROOT_JOURNAL")
    try:
        payload=json.loads(result.stdout)
        expected_approval=request["signed_owner_proof"]["payload"]["approval_id"]
        expected_rollback=request["rollback_sha"]
    except (KeyError,ValueError,TypeError) as exc:
        raise StageERootBootstrapDenied(
            "PMV4_E_ROOT_BOOTSTRAP_NATIVE_RESULT_NOT_JSON_OR_BOUND") from exc
    need(type(payload) is dict
         and payload.get("status")=="native_stage_e_six_unit_accepted"
         and payload.get("candidate_sha")==candidate
         and payload.get("rollback_sha")==expected_rollback
         and payload.get("approval_id")==expected_approval
         and payload.get("protected_services_changed") is False,
         "ORIGINAL_NATIVE_ACCEPTANCE_NOT_VERIFIED")
    return payload


def require_matching_recovery_request(request:dict,record:dict)->None:
    """Only the previously journaled exact proof can select inert recovery."""
    need(type(request) is dict and type(record) is dict
         and type(request.get("signed_owner_proof")) is dict
         and request["signed_owner_proof"]==record.get("signed_owner_proof")
         and all(request.get(key)==record.get(key) for key in (
             "candidate_sha","rollback_sha","scope_sha256",
             "manifest_sha256","freeze_sha256")),
         "RECOVERY_REQUEST_DOES_NOT_MATCH_STARTED_PROOF")


def run_once(candidate:str,*,stage_only:bool,recover_inert:bool=False,
             owner_request_stream=None)->dict:
    bind_original_native()
    from tools import pmv4_e_signed_bootstrap_phase as signed
    from tools import pmv4_e_immutable_source_stage as immutable
    from tools import pmv4_e_root_trust_stage as trust
    from tools import pmv4_e_native_release_contract as contract
    from tools import pmv4_e_exact_release_packet as packet
    from tools import pmv4_e_root_cutover_preflight as rootflight
    from tools import pmv4_e_source_scope_guard as scope_guard
    from tools.independent_component_host_adapter import IndependentComponentHost

    need(packet.ROOT==TRUST and
         "tools/pmv4_e_root_bootstrap_once.py" in packet.REVIEWED_PATHS,
         "BOOTSTRAP_INSTALLED_SOURCE_NOT_REVIEWED")
    for directory in (NATIVE_RECORDS,NATIVE_RECEIPTS,
                      BOOTSTRAP_JOURNAL,RELEASES):
        checked_root_dir(directory)
    # A forwarded request is untrusted until the original root signed phase
    # verifies it under the host and freeze locks, exactly as for the file.
    forwarded=(packet.read_owner_request_stream(owner_request_stream)
               if owner_request_stream is not None else None)
    # The original root verifier, not a user/GitHub branch or this helper,
    # authoritatively chooses the source, Owner and live CI evidence.
    offer=read_offer(candidate,packet,owner_request=forwarded)
    reviewed=contract.draft(
        candidate_sha=candidate,
        rollback_sha=offer["manifest.json"]["rollback_sha"],
        source_root=TRUST)
    need(reviewed["manifest"]==offer["manifest.json"]
         and reviewed["source_scope"]==offer["source-scope.json"],
         "OWNER_ARTIFACT_NOT_EXACT_REVIEWED_SOURCE")
    request=offer["owner-proof.json"]
    core=IndependentComponentHost(production=True)
    state={"host":False,"freeze":False}
    def marker_absent():
        p=rootflight.MARKER
        return not (p.exists() or p.is_symlink())
    def all_legacy():
        return all(rootflight._active(n,user=True)
                   for n in rootflight.OLD_USER) and all(
                   rootflight._active(n,user=False)
                   for n in rootflight.OLD_ROOT)
    def replacements_inert():
        return not any(rootflight._active(n,user=True)
                       for n in rootflight.NEW_USER) and not any(
                       rootflight._active(n,user=False)
                       for n in rootflight.NEW_ROOT)
    def source_and_ci(sha):
        if core.source_and_ci(sha) is not True:
            return False
        witness=scope_guard.verify_under_lock(
            candidate=sha,rollback=reviewed["manifest"]["rollback_sha"],
            manual_sha256=reviewed["source_scope"]["exact_replacement_files_sha256"][
                "tools/manual_release_scope.py"],
            host_lock_held=state["host"],freeze_lock_held=state["freeze"],
            production=True)
        return witness.get("status")=="protected_stage_e_source_scope_verified_under_lock"
    phase=signed.SignedInertBootstrap(
        source_root=TRUST,
        host_lock_held=lambda:state["host"],
        freeze_lock_held=lambda:state["freeze"],
        legacy_active=all_legacy,
        replacements_inert=replacements_inert,
        marker_absent=marker_absent,
        source_ci_verified=source_and_ci,
        production=True)
    hashes=reviewed["source_scope"]["exact_replacement_files_sha256"]
    source=immutable.ImmutableRootSourceStage(
        exact_owner_verified=lambda:phase.signed_started(
            candidate_sha=candidate,
            scope_sha256=reviewed["manifest"]["source_scope_sha256"],
            approval_id=request["signed_owner_proof"]["payload"]["approval_id"]),
        original_host_locked=lambda:state["host"],
        original_freeze_locked=lambda:state["freeze"],
        marker_absent=marker_absent,
        replacement_inert=replacements_inert,
        production=True)
    root=trust.RootTrustStager(
        source=RELEASES/candidate,
        native_signed_started=lambda:phase.signed_started(
            candidate_sha=candidate,
            scope_sha256=reviewed["manifest"]["source_scope_sha256"],
            approval_id=request["signed_owner_proof"]["payload"]["approval_id"]),
        native_host_locked=lambda:state["host"],
        native_freeze_locked=lambda:state["freeze"],
        native_marker_absent=marker_absent,
        native_replacements_inert=replacements_inert,
        production=True)
    # Deny any release artifact conflicts BEFORE consuming the one-use
    # approval. Native receipt state is independently inspected on recovery.
    if not recover_inert:
        need(not (RELEASES/candidate).exists()
             and not (RELEASES/candidate).is_symlink()
             and not (trust.TARGET).exists()
             and not (trust.TARGET).is_symlink()
             and not (NATIVE_RECORDS/candidate).exists()
             and not (NATIVE_RECORDS/candidate).is_symlink(),
             "ONE_USE_STAGE_TARGET_ALREADY_PRESENT")
    with core.host_transaction():
        state["host"]=True
        try:
            with core.freeze_transaction(reviewed["manifest"]["freeze_sha256"]):
                state["freeze"]=True
                try:
                    if recover_inert:
                        approval_id=request["signed_owner_proof"]["payload"]["approval_id"]
                        need(phase.signed_started(
                            candidate_sha=candidate,
                            scope_sha256=reviewed["manifest"]["source_scope_sha256"],
                            approval_id=approval_id),
                             "RECOVERY_ORIGINAL_SIGNED_BOOTSTRAP_MISSING")
                        recovery_record=signed.root_record(
                            BOOTSTRAP_JOURNAL/("owner-"+approval_id+".json"),
                            production=True)
                        require_matching_recovery_request(request,recovery_record)
                        for item in NATIVE_RECEIPTS.iterdir():
                            row=signed.root_record(item,production=True)
                            need(row.get("candidate_sha")!=candidate,
                                 "NATIVE_RELEASE_HAS_STARTED_MUST_USE_LEDGER_RECOVERY")
                        if trust.TARGET.exists() or trust.TARGET.is_symlink():
                            root.recover_inert_stage(hashes)
                        if (NATIVE_RECORDS/candidate).exists() or (
                                NATIVE_RECORDS/candidate).is_symlink():
                            dest=NATIVE_RECORDS/candidate
                            checked_root_dir(dest,mode=0o555)
                            need({p.name for p in dest.iterdir()}==
                                 {"manifest.json","source-scope.json"},
                                 "INERT_RECORD_SET_CHANGED")
                            for name,key in (("manifest.json","manifest"),
                                             ("source-scope.json","source_scope")):
                                need(checked_root_file(dest/name)==
                                     packet.canonical(reviewed[key]),
                                     "INERT_RELEASE_RECORD_BYTES_CHANGED")
                            dest.chmod(0o700)
                            (dest/"manifest.json").unlink()
                            (dest/"source-scope.json").unlink()
                            dest.rmdir()
                        if (RELEASES/candidate).exists() or (
                                RELEASES/candidate).is_symlink():
                            source.recover_inert(
                                candidate=candidate,exact_hashes=hashes)
                        return {
                            "status":"signed_inert_bootstrap_recovered",
                            "candidate_sha":candidate,
                            "legacy_six_unchanged":True,
                            "owner_approval_reusable":False,
                        }
                    # The original signed phase binds exact current source,
                    # protected CI, signer, pre-cutover state and replay.
                    phase.begin(request)
                    stage=source.stage(candidate=candidate,exact_hashes=hashes)
                    root_result=root.stage(source_sha=candidate,exact_hashes=hashes)
                    need(root_result["installed_file_count"]==len(hashes),
                         "ROOT_TRUST_INSTALL_INCOMPLETE")
                    safe_release_records(candidate,reviewed,packet)
                finally:state["freeze"]=False
        finally:state["host"]=False
    output={
        "status":"one_signed_owner_inert_root_stage_verified",
        "candidate_sha":candidate,
        "source_files":stage["source_file_count"],
        "root_files":root_result["installed_file_count"],
        "production_triggers_changed":False,
        "owner_permission_to_modify_units":False,
    }
    if stage_only:
        return output
    # The original native signed ledger reacquires original host+freeze locks,
    # verifies independently installed root/Owner/CI/preflight, then executes
    # its own bounded six-unit transaction and rollback. No other executor.
    payload=native_promotion(
        candidate,packet=packet,request=request,forwarded=forwarded is not None)
    return {
        **output,"status":"native_stage_e_six_unit_accepted",
        "original_native_receipt":payload,
        "root_bootstrap_source_pinned":True,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate-sha",required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage-only",action="store_true")
    mode.add_argument("--stage-and-promote",action="store_true")
    mode.add_argument("--recover-inert",action="store_true")
    parser.add_argument("--owner-request-stdin",action="store_true")
    args=parser.parse_args(argv)
    candidate=candidate_arg(args.candidate_sha)
    result=run_once(
        candidate,stage_only=args.stage_only,
        recover_inert=args.recover_inert,
        owner_request_stream=sys.stdin.buffer if args.owner_request_stdin else None)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (StageERootBootstrapDenied,PermissionError,OSError,ValueError,
            TypeError,subprocess.SubprocessError) as exc:
        print("DENIED:"+type(exc).__name__+
              (":"+str(exc)[:150] if isinstance(exc,PermissionError) else ""),
              file=sys.stderr)
        raise SystemExit(2)
