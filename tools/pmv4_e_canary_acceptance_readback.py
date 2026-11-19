#!/usr/bin/env python3
"""Root-only independent acceptance of Stage E generic-controller canary.

Never authorizes PMv3 retirement, disables a timer or performs provider calls.
This source must be pinned by a later reviewed exact root install before use.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from tools import pmv4_e_root_receipt_readback as historical

SOURCE="d85faad76881439953527d391c314df0f5d2967a"
BUILD="c39545d31603f3f29db77ba880971838e20fcf26"
SCOPE="b9107ef85af95fe20ecd40523006e561c90d06585835d63a9970719bbd03f4c6"
MANIFEST="92472001a64ecdd3d9c53d321b544aa7d10bdcf27f5dd2ad8b72b97bca6d2924"
FREEZE="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
POLICY="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"
APPROVAL_ID="owner-mcp-215fd672872d4f84a99ee17a25cf6fd5"
ACTION="pmv4-e-oneowner-providerfree-native-canary-and-cleanup-v1"
ROOT=Path("/var/lib/jason/independent-component-release")
TERMINAL=ROOT/"control"/("pmv4-e-canary-"+SOURCE+"-accepted.json")
STARTED=ROOT/"control"/("pmv4-e-canary-"+SOURCE+"-transaction.json")
NATIVE=ROOT/"receipts"/("owner-"+APPROVAL_ID+".json")
BUNDLE=ROOT/"releases"/SOURCE/"manifest.json"
ACTIVE=ROOT/"active"/"pmv4-e-canary.json"
ROOT_SIGNER=Path("/opt/jason/independent-component-release/trusted/implementation/kernel/signed_owner_release.py")
ROOT_SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
ROOT_OWNER_PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE_PATH=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
FREEZE_UID=1000
FREEZE_GID=1000
POLICY_PATH=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
CANARY_NAME="jason-pmv4-e-canary-pmv4-e-canary-1"
CANARY_PROJECT="jason-pmv4-e-canary"
PRIVATE_NETWORK=CANARY_PROJECT+"-private"
SHA256=re.compile(r"^[0-9a-f]{64}$")


class CanaryAcceptanceDenied(PermissionError):
    pass


def need(ok:bool,code:str)->None:
    if not ok:
        raise CanaryAcceptanceDenied("PMV4_E_CANARY_READBACK_"+code)


def root_data(path:Path,*,mode:int=0o600,maximum:int=100000)->bytes:
    try:
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_uid==0 and meta.st_gid==0
             and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==mode
             and 0<meta.st_size<=maximum,
             "ROOT_FILE_UNTRUSTED:"+path.name)
        raw=path.read_bytes()
        need(len(raw)==meta.st_size,
             "ROOT_FILE_MODIFIED_DURING_READ:"+path.name)
        return raw
    except CanaryAcceptanceDenied:
        raise
    except OSError as exc:
        raise CanaryAcceptanceDenied(
            "PMV4_E_CANARY_READBACK_ROOT_FILE_UNAVAILABLE:"+path.name) from exc


def validate_service_file_meta(meta:Any,*,path_name:str,
                               expected_uid:int=FREEZE_UID,
                               expected_gid:int=FREEZE_GID,mode:int=0o600,
                               maximum:int=100000)->None:
    need(stat.S_ISREG(meta.st_mode) and meta.st_uid==expected_uid
         and meta.st_gid==expected_gid and meta.st_nlink==1
         and stat.S_IMODE(meta.st_mode)==mode
         and 0<meta.st_size<=maximum,
         "SERVICE_FILE_UNTRUSTED:"+path_name)


def service_owned_data(path:Path,*,expected_uid:int=FREEZE_UID,
                       expected_gid:int=FREEZE_GID,mode:int=0o600,
                       maximum:int=100000)->bytes:
    """Read the service-user-owned freeze without treating it as root data."""
    try:
        meta=path.lstat()
        need(not path.is_symlink(),"SERVICE_FILE_UNTRUSTED:"+path.name)
        validate_service_file_meta(
            meta,path_name=path.name,expected_uid=expected_uid,
            expected_gid=expected_gid,mode=mode,maximum=maximum)
        raw=path.read_bytes()
        need(len(raw)==meta.st_size,
             "SERVICE_FILE_MODIFIED_DURING_READ:"+path.name)
        return raw
    except CanaryAcceptanceDenied:
        raise
    except OSError as exc:
        raise CanaryAcceptanceDenied(
            "PMV4_E_CANARY_READBACK_SERVICE_FILE_UNAVAILABLE:"+path.name) from exc


def exact_json(path:Path,*,mode:int=0o600,maximum:int=100000)->dict[str,Any]:
    try:
        value=json.loads(root_data(path,mode=mode,maximum=maximum))
    except (ValueError,TypeError) as exc:
        raise CanaryAcceptanceDenied(
            "PMV4_E_CANARY_READBACK_JSON_INVALID:"+path.name) from exc
    need(isinstance(value,dict),"DOCUMENT_NOT_OBJECT:"+path.name)
    return value


def signer_module():
    source=root_data(ROOT_SIGNER,mode=0o444,maximum=100000)
    need(sha256(source).hexdigest()==ROOT_SIGNER_SHA,
         "PINNED_ROOT_SIGNER_CHANGED")
    spec=importlib.util.spec_from_file_location(
        "pmv4_e_verified_root_signer",ROOT_SIGNER)
    need(spec is not None and spec.loader is not None,
         "ROOT_SIGNER_IMPORT_NOT_TRUSTED")
    signed=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(signed)
    return signed


def verify_historical_signed_journal(native:dict[str,Any])->None:
    signed=native.get("signed_owner_proof")
    need(isinstance(signed,dict),
         "NATIVE_SIGNED_OWNER_EVIDENCE_MISSING")
    try:
        started=datetime.fromisoformat(
            str(native.get("started_at") or "").replace("Z","+00:00"))
    except ValueError as exc:
        raise CanaryAcceptanceDenied(
            "PMV4_E_CANARY_READBACK_NATIVE_START_TIME_INVALID") from exc
    need(started.tzinfo is not None and started<=datetime.now(timezone.utc),
         "NATIVE_START_TIME_NOT_HISTORIC")
    source=signer_module()
    root_public=source.read_pinned_root_owner_public_key(
        ROOT_OWNER_PUBLIC)
    try:
        proof=source.verify_exact_owner_release(
            signed,public_key=root_public,
            expected_candidate_sha=SOURCE,
            expected_rollback_sha="0"*40,
            expected_release_id="release-"+SOURCE[:16],
            expected_scope_sha256=SCOPE,
            expected_manifest_sha256=MANIFEST,
            expected_freeze_sha256=FREEZE,
            at=started,
        )
    except (PermissionError,TypeError,ValueError) as exc:
        raise CanaryAcceptanceDenied(
            "PMV4_E_CANARY_READBACK_NATIVE_OWNER_SIGNATURE_NOT_VERIFIED") from exc
    need(proof.get("approval_id")==APPROVAL_ID
         and proof.get("decision")=="approve",
         "NATIVE_OWNER_APPROVAL_NOT_EXACT")


def exact_receipts()->dict[str,Any]:
    terminal=exact_json(TERMINAL)
    started=exact_json(STARTED)
    native=exact_json(NATIVE)
    bundle=exact_json(BUNDLE,mode=0o444)
    need(terminal.get("schema_version")=="1.0"
         and terminal.get("state")=="accepted_and_removed"
         and terminal.get("action")==ACTION
         and terminal.get("source_sha")==SOURCE
         and terminal.get("build_sha")==BUILD
         and terminal.get("approval_id")==APPROVAL_ID
         and terminal.get("scope_sha256")==SCOPE
         and terminal.get("manifest_sha256")==MANIFEST
         and terminal.get("native_generic_acceptance_verified") is True
         and terminal.get("isolated_canary_rollback_verified") is True
         and terminal.get("protected_before_equals_after") is True
         and terminal.get("production_freeze_unchanged") is True
         and terminal.get("provider_calls")==0
         and terminal.get("pmv3_units_modified") is False
         and terminal.get("retirement_authorized") is False
         and terminal.get("protected_policy_sha256")==POLICY,
         "FINAL_CANARY_ACCEPTANCE_RECEIPT_NOT_EXACT")
    need(started.get("schema_version")=="1.0"
         and started.get("state")=="started"
         and started.get("action")==ACTION
         and started.get("source_sha")==SOURCE
         and started.get("build_sha")==BUILD
         and started.get("owner_approval_id")==APPROVAL_ID
         and started.get("scope_sha256")==SCOPE
         and started.get("manifest_sha256")==MANIFEST,
         "INITIAL_CANARY_ROOT_TRANSACTION_NOT_EXACT")
    protected=started.get("protected_before")
    need(isinstance(protected,dict)
         and {"jason-runtime","jason-pmv4-ticket-core",
              "jason-mcp-pilot","jason-pmv4-shadow-gateway",
              "jason-teams-gateway","openbao"}.issubset(protected),
         "ROOT_PROTECTED_BASELINE_NOT_RECORDED")
    need(native.get("schema_version")=="1.0"
         and native.get("state")=="accepted"
         and native.get("component_id")=="pmv4-e-canary"
         and native.get("candidate_sha")==SOURCE
         and native.get("rollback_sha")=="0"*40
         and native.get("approval_id")==APPROVAL_ID
         and native.get("release_id")=="release-"+SOURCE[:16]
         and native.get("scope_sha256")==SCOPE
         and native.get("manifest_sha256")==MANIFEST
         and native.get("freeze_sha256")==FREEZE,
         "NATIVE_SIGNED_ACCEPTANCE_JOURNAL_NOT_EXACT")
    need(bundle.get("candidate_sha")==SOURCE
         and bundle.get("rollback_sha")=="0"*40
         and bundle.get("component_id")=="pmv4-e-canary"
         and bundle.get("scope_sha256")==SCOPE
         and bundle.get("freeze_sha256")==FREEZE
         and sha256(json.dumps(bundle,sort_keys=True,separators=(",",":"),
                  ensure_ascii=False,allow_nan=False).encode()).hexdigest()==MANIFEST
         and bundle.get("provider_scope",{}).get("provider")=="none",
         "ROOT_CANARY_MANIFEST_NOT_EXACT")
    verify_historical_signed_journal(native)
    return {
        "owner_signature_verified_at_native_start":True,
        "root_terminal_state":"accepted_and_removed",
        "root_initial_state":"started",
        "native_journal_state":"accepted",
        "approval_id":APPROVAL_ID,
        "source_sha":SOURCE,
        "build_sha":BUILD,
        "historical_protected_count":len(protected),
    }


def probe_clean_host(*,runner=subprocess.run,
                     expected_freeze_sha:str=FREEZE,
                     expected_policy_sha:str=POLICY)->dict[str,Any]:
    # The defaults are immutable production acceptance pins. Overriding them
    # is only for synthetic fixtures that cannot reproduce a SHA preimage.
    for expected in (expected_freeze_sha,expected_policy_sha):
        need(isinstance(expected,str) and SHA256.fullmatch(expected) is not None,
             "EXPECTED_SOURCE_DIGEST_INVALID")
    freeze=service_owned_data(FREEZE_PATH)
    need(sha256(freeze).hexdigest()==expected_freeze_sha,
         "PRODUCTION_FREEZE_CHANGED")
    need(sha256(root_data(POLICY_PATH)).hexdigest()==expected_policy_sha,
         "PRODUCTION_POLICY_CHANGED")
    for argv in (
        ["/usr/bin/docker","ps","-aq","--filter",
         "label=com.docker.compose.project="+CANARY_PROJECT],
        ["/usr/bin/docker","network","ls","--filter",
         "name=^"+PRIVATE_NETWORK+"$","--format","{{.Name}}"],
    ):
        p=runner(argv,capture_output=True,text=True,timeout=25)
        need(p.returncode==0 and not p.stdout.strip(),
             "PRIVATE_CANARY_STILL_PRESENT_OR_DOCKER_UNAVAILABLE")
    need(not ACTIVE.exists() and not ACTIVE.is_symlink(),
         "CANARY_ACTIVE_POINTER_NOT_REMOVED")
    return {"policy_sha256":expected_policy_sha,
            "freeze_sha256":expected_freeze_sha,
            "canary_container_absent":True,
            "canary_network_absent":True,
            "active_pointer_absent":True}


def inspect()->dict[str,Any]:
    need(os.geteuid()==0,"ROOT_ONLY")
    # Preserve existing C/D/A1 and exact prior root desired state checks.
    historical_evidence=historical.inspect()
    need(historical_evidence.get("status")==
         "pre_retirement_root_acceptance_verified",
         "C_D_A1_PROTECTED_PRECONDITIONS_NOT_ACCEPTED")
    receipts=exact_receipts()
    clean=probe_clean_host()
    return {
        "status":"native_providerfree_canary_accepted_and_removed",
        "phase":"E",
        **receipts,**clean,
        "stage_c_d_a1_root_acceptance":True,
        "pmv3_retirement_authorized":False,
        "replacement_scheduler_parity_accepted":False,
        "production_mutations":False,
        "provider_calls":0,
    }


def main()->None:
    try:
        print(json.dumps(inspect(),sort_keys=True))
    except (CanaryAcceptanceDenied,
            historical.StageERootEvidenceDenied) as exc:
        print(json.dumps({
            "status":"not_verified",
            "code":str(exc)[:180],
            "pmv3_retirement_authorized":False,
            "production_mutations":False,
        },sort_keys=True))
        raise SystemExit(2)


if __name__=="__main__":
    main()
