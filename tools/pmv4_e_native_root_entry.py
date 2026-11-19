#!/usr/bin/env python3
"""Final *installed-only* entry for the original signed native Stage E release.

The already-installed generic ComponentReleaseController keeps sole release
authority, Owner Ed25519 signature validation, host/freeze/component locks,
one-use receipt, protected snapshots, and recovery journal. This root-only
entry binds that controller to the exact Stage E native host/systemd adapter.

It cannot bootstrap its own trust root or issue an Owner decision. A separate
governed exact Owner-approved inert bootstrap must FIRST seal the reviewed
Stage E trust tree and root release records. No arbitrary file path, shell,
provider call, restart, freeze override or second release manager is exposed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

ROOT_ENTRY=Path("/opt/jason/pmv4-e-trusted/tools/pmv4_e_native_root_entry.py")
TRUST=ROOT_ENTRY.parent.parent
GENERIC=Path("/opt/jason/independent-component-release/trusted")
NATIVE_ROOT=Path("/var/lib/jason/independent-component-release")
PRODUCTION_RELEASE_ROOT=Path("/opt/jason/releases")
OWNER_ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
SHA40=re.compile(r"^[0-9a-f]{40}$")
PINNED_NATIVE_SHA256={
    "tools/independent_component_release.py":
        "1e6f981344f6bfb87977f2d3f4c5e76875447efd78aba03a8968ba94240bd4c7",
    "tools/independent_component_host_adapter.py":
        "36f667fd53c2410a902772d3fae7cec7b08f89f99d71f71009c5a8f8029dedce",
    "tools/independent_component_release_root.py":
        "e539e66c470469312714c2c10eb52fed293c6638a66d04049f55a4a481fe1324",
    "implementation/kernel/signed_owner_release.py":
        "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3",
}


class StageERootEntryDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:
        raise StageERootEntryDenied("PMV4_E_ROOT_ENTRY_"+reason)


def exact_candidate(sha:str)->str:
    need(type(sha) is str and SHA40.fullmatch(sha) is not None,
         "CANDIDATE_SHA_NOT_EXACT")
    return sha


def trust_file(path:Path,*,uid:int=0,mode:int=0o444,
               maximum:int=1000000)->bytes:
    try:
        stat_result=path.lstat()
        need(not path.is_symlink()
             and stat.S_ISREG(stat_result.st_mode)
             and stat_result.st_nlink==1
             and stat_result.st_uid==uid
             and stat_result.st_gid==uid
             and stat.S_IMODE(stat_result.st_mode)==mode
             and 0<stat_result.st_size<=maximum,
             "REVIEWED_FILE_IDENTITY_NOT_ROOT_PINNED")
        raw=path.read_bytes()
        need(len(raw)==stat_result.st_size,
             "REVIEWED_FILE_CHANGED_DURING_READ")
        return raw
    except StageERootEntryDenied:
        raise
    except OSError as exc:
        raise StageERootEntryDenied(
            "PMV4_E_ROOT_ENTRY_REVIEWED_FILE_UNAVAILABLE") from exc


def trust_root_directory(path:Path,*,mode:int|None=None)->None:
    try:
        v=path.lstat()
        need(not path.is_symlink() and stat.S_ISDIR(v.st_mode)
             and v.st_uid==0 and v.st_gid==0
             and v.st_mode&0o022==0
             and (mode is None or stat.S_IMODE(v.st_mode)==mode),
             "ROOT_DIRECTORY_NOT_PINNED")
    except StageERootEntryDenied:
        raise
    except OSError as exc:
        raise StageERootEntryDenied(
            "PMV4_E_ROOT_ENTRY_ROOT_DIRECTORY_MISSING") from exc


def safe_json(data:bytes)->dict[str,Any]:
    try:
        x=json.loads(data)
        need(type(x) is dict,"RECORD_NOT_JSON_OBJECT")
        return x
    except (ValueError,TypeError,UnicodeDecodeError) as exc:
        raise StageERootEntryDenied("PMV4_E_ROOT_ENTRY_BAD_JSON") from exc


def require_exact_owner_request(request:dict[str,Any],
                                manifest:dict[str,Any])->dict[str,Any]:
    """User-owned proof is untrusted until the *original* ledger verifies it."""
    mandatory={
        "schema_version","request_id","action","candidate_sha",
        "rollback_sha","scope_sha256","manifest_sha256","freeze_sha256",
        "signed_owner_proof",
    }
    candidate=manifest["candidate_sha"]
    expected={
        "schema_version":"1.0",
        "request_id":"release-"+candidate[:16],
        "action":"pmv4_e_stage_exact_signed_inert_root_v1",
        "candidate_sha":candidate,
        "rollback_sha":manifest["rollback_sha"],
        "scope_sha256":manifest["source_scope_sha256"],
        "manifest_sha256":sha256(json.dumps(
            manifest,sort_keys=True,separators=(",",":"),
            ensure_ascii=False,allow_nan=False).encode()).hexdigest(),
        "freeze_sha256":manifest["freeze_sha256"],
    }
    need(type(request) is dict and set(request)==mandatory
         and all(request.get(k)==v for k,v in expected.items())
         and type(request.get("signed_owner_proof")) is dict,
         "OWNER_REQUEST_NOT_EXACT_BOUND_RELEASE")
    proof=request["signed_owner_proof"]
    payload=proof.get("payload")
    need(type(payload) is dict
         and payload.get("release_id")==expected["request_id"]
         and payload.get("candidate_sha")==candidate
         and payload.get("rollback_sha")==expected["rollback_sha"]
         and payload.get("scope_sha256")==expected["scope_sha256"]
         and payload.get("manifest_sha256")==expected["manifest_sha256"]
         and payload.get("freeze_sha256")==expected["freeze_sha256"],
         "OWNER_PROOF_PAYLOAD_NOT_EXACT")
    return proof


def installed_release(candidate:str)->tuple[dict[str,Any],dict[str,Any]]:
    release=NATIVE_ROOT/"releases"/exact_candidate(candidate)
    trust_root_directory(NATIVE_ROOT)
    trust_root_directory(NATIVE_ROOT/"releases")
    trust_root_directory(release,mode=0o555)
    need({p.name for p in release.iterdir()}==
         {"manifest.json","source-scope.json"},
         "NATIVE_RELEASE_RECORD_FILE_SET_CHANGED")
    manifest=safe_json(trust_file(release/"manifest.json"))
    scope=safe_json(trust_file(release/"source-scope.json"))
    need(manifest.get("candidate_sha")==candidate
         and scope.get("candidate_sha")==candidate
         and scope.get("rollback_sha")==manifest.get("rollback_sha")
         and type(scope.get("exact_replacement_files_sha256")) is dict,
         "RELEASE_RECORD_CANDIDATE_NOT_BOUND")
    return manifest,scope


def bind_original_native_packages(scope:dict[str,Any])->None:
    """Fail closed before importing any mutable ambient project package."""
    need(os.geteuid()==0 and Path(__file__)==ROOT_ENTRY
         and Path(__file__).resolve()==ROOT_ENTRY,
         "CANONICAL_PRIVILEGED_ENTRY_REQUIRED")
    trust_file(ROOT_ENTRY)
    trust_root_directory(TRUST,mode=0o555)
    trust_root_directory(TRUST/"tools",mode=0o555)
    trust_root_directory(GENERIC)
    hashes=scope["exact_replacement_files_sha256"]
    need(type(hashes) is dict
         and hashes.get("tools/pmv4_e_native_root_entry.py")==
             sha256(trust_file(ROOT_ENTRY)).hexdigest(),
         "ROOT_ENTRY_NOT_IN_REVIEWED_SOURCE")
    for rel,expected in PINNED_NATIVE_SHA256.items():
        need(hashes.get(rel)==expected
             and sha256(trust_file(GENERIC/rel)).hexdigest()==expected,
             "PREINSTALLED_GENERIC_NATIVE_MODULE_DRIFT")
    relative="tools/pmv4_e_root_import_binding.py"
    pinned=trust_file(TRUST/relative)
    need(hashes.get(relative)==sha256(pinned).hexdigest(),
         "ROOT_BINDER_NOT_SOURCE_PINNED")
    spec=importlib.util.spec_from_file_location(
        "_stage_e_strict_original_native_import_binding",TRUST/relative)
    need(spec is not None and spec.loader is not None,
         "ROOT_BINDER_UNAVAILABLE")
    binder=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binder)
    binder.prepare(
        native_root=GENERIC,stage_root=TRUST,
        approved_hashes={**hashes,**PINNED_NATIVE_SHA256},
        production=True)


def owner_proof_for_promote(manifest:dict[str,Any])->dict[str,Any]:
    candidate=manifest["candidate_sha"]
    folder=OWNER_ARTIFACTS/("pmv4-e-source-only-"+candidate)
    d=folder.lstat()
    need(not folder.is_symlink() and stat.S_ISDIR(d.st_mode)
         and d.st_uid==d.st_gid==1000
         and stat.S_IMODE(d.st_mode)==0o700,
         "CANONICAL_OWNER_ARTIFACT_DIRECTORY_UNTRUSTED")
    owner_request=safe_json(trust_file(
        folder/"owner-proof.json",uid=1000,mode=0o400,maximum=32768))
    return require_exact_owner_request(owner_request,manifest)


def started_proof_for_recovery(candidate:str)->dict[str,Any]|None:
    """No new permission: original native STARTED journal is recovery proof."""
    from tools import pmv4_e_signed_bootstrap_phase as bootstrap
    root=NATIVE_ROOT/"receipts"
    trust_root_directory(root)
    pending=[]
    for item in sorted(root.iterdir()):
        need(item.name.startswith("owner-") and item.suffix==".json",
             "UNKNOWN_NATIVE_RECEIPT_STORE_OBJECT")
        record=bootstrap.root_record(item,production=True)
        if (record.get("state")=="started"
            and record.get("component_id")=="pmv4-e-six-unit-controlplane"):
            pending.append(record)
    need(len(pending)<=1,"MULTIPLE_NATIVE_STARTED_RELEASES")
    if not pending:
        return None
    row=pending[0]
    need(row.get("candidate_sha")==candidate
         and type(row.get("signed_owner_proof")) is dict,
         "NATIVE_STARTED_RELEASE_ID_CHANGED")
    return row["signed_owner_proof"]


def controller_from_root(*,manifest:dict[str,Any],
                         scope:dict[str,Any],owner_proof:dict[str,Any]):
    from tools import pmv4_e_native_root_manifest_attestation as attestor
    from tools import pmv4_e_native_root_host as hostmod
    from tools import pmv4_e_native_backend_bridge as bridge
    from tools import pmv4_e_native_systemd_adapter as adapter
    from tools import pmv4_e_signed_native_ledger as native
    from tools.independent_component_release import PRODUCTION_ROOT

    source_root=PRODUCTION_RELEASE_ROOT/manifest["candidate_sha"]
    source_meta=source_root.lstat()
    need(not source_root.is_symlink() and stat.S_ISDIR(source_meta.st_mode)
         and source_meta.st_uid==source_meta.st_gid==0
         and source_meta.st_mode&0o022==0,
         "IMMUTABLE_SOURCE_RELEASE_UNAVAILABLE")
    proof=attestor.inspect(
        source_root=TRUST,
        release_dir=NATIVE_ROOT/"releases"/manifest["candidate_sha"],
        production=True)
    need(proof.get("status")=="root_source_attested_no_release_authority"
         and proof.get("candidate_sha")==manifest["candidate_sha"]
         and proof.get("scope_sha256")==manifest["source_scope_sha256"],
         "SEALED_ROOT_STAGE_E_NOT_ATTESTED")
    core=hostmod.NativeStageEHost(
        manifest=manifest,scope=scope,owner_proof=owner_proof,
        production=True)
    wrapped=bridge.StageERootBridge(native_root=core,systemd=core.systemd)
    component=adapter.StageEUnitAdapter(
        wrapped,native_invocation=lambda:
            core.exclusive_host_lock_held() and core.freeze_lock_held())
    def activate(bundle,m):
        component.activate(
            candidate_sha=m["candidate_sha"],rollback_sha=m["rollback_sha"],
            scope_sha256=m["source_scope_sha256"],action=m["action"])
    def restore(_prior,m):
        component.restore(
            rollback_sha=m["rollback_sha"],
            scope_sha256=m["source_scope_sha256"])

    return native.StageESignedNativeLedger(
        source_root=source_root,root=PRODUCTION_ROOT,
        host_transaction=core.host_transaction,
        freeze_transaction=core.freeze_transaction,
        verify_protected=core.core_host.protected,
        verify_source_and_ci=core.core_host.source_and_ci,
        verify_image=core.core_host.image,
        observe_component=core.observe_component,
        activate_component=activate,
        restore_component=restore,
        verify_component=core.verify_component,
        production=True)


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate-sha",required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight",action="store_true")
    modes.add_argument("--promote",action="store_true")
    modes.add_argument("--recover-interrupted",action="store_true")
    args=parser.parse_args(argv)
    need(os.geteuid()==0 and Path(__file__)==ROOT_ENTRY
         and Path(__file__).resolve()==ROOT_ENTRY
         and not Path(__file__).is_symlink(),
         "CANONICAL_ROOT_ENTRY_NOT_INSTALLED")
    candidate=exact_candidate(args.candidate_sha)
    manifest,scope=installed_release(candidate)
    bind_original_native_packages(scope)
    from tools import pmv4_e_root_cutover_preflight as preflight
    if args.preflight:
        from tools import pmv4_e_native_root_manifest_attestation as attestor
        witness=attestor.inspect(
            source_root=TRUST,
            release_dir=NATIVE_ROOT/"releases"/candidate,
            production=True)
        observed=preflight.evaluate(preflight.collect())
        print(json.dumps({"status":"read_only_exact_root_stage_e_preflight_passed",
                          "root_source":witness["status"],
                          "current_root":observed["status"],
                          "production_mutations":False},sort_keys=True))
        return 0
    if args.promote:
        signed=owner_proof_for_promote(manifest)
    else:
        signed=started_proof_for_recovery(candidate)
        if signed is None:
            print(json.dumps({"status":"nothing_pending",
                              "production_mutations":False},sort_keys=True))
            return 0
    controller=controller_from_root(
        manifest=manifest,scope=scope,owner_proof=signed)
    result=(controller.promote(manifest,signed)
            if args.promote else controller.recover_interrupted_rollback())
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (StageERootEntryDenied,PermissionError,OSError,ValueError,
            TypeError) as exc:
        print("DENIED:"+type(exc).__name__+
              (":"+str(exc)[:140] if isinstance(exc,PermissionError) else ""),
              file=sys.stderr)
        raise SystemExit(2)
