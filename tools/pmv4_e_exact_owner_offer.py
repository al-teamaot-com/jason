#!/usr/bin/env python3
"""One local authenticated Entra Owner proof for the EXACT Stage E transaction.

Uses already installed/pinned signer, OAuth verification and Owner private key
used for the governed Stage E provider-free canary. This module NEVER asks for
a password, exposes a bearer, executes sudo, mutates systemd, modifies freeze,
or grants standing authority. It produces one 0400 signed Owner request.
Source-only until independently reviewed and approved as an exact release.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_signed_bootstrap_phase as bootstrap

ISSUER=Path("/usr/local/lib/jason/owner_signed_release.py")
ISSUER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
REPO=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
CONFIRM="APPROVE-ONE-EXACT-PMV4-E-SIX-UNIT-CUTOVER-AND-ROLLBACK"
SHA40=re.compile(r"^[0-9a-f]{40}$")


class ExactOwnerOfferDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:
        raise ExactOwnerOfferDenied("PMV4_E_OWNER_"+reason)


def pinned_module(path:Path,expected_sha:str,name:str):
    try:
        m=path.lstat()
        data=path.read_bytes()
    except OSError as exc:
        raise ExactOwnerOfferDenied("PMV4_E_OWNER_PINNED_MODULE_UNAVAILABLE") from exc
    need(not path.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==m.st_gid==0
         and m.st_mode&0o022==0
         and sha256(data).hexdigest()==expected_sha,
         "PINNED_IDENTITY_MODULE_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,
         "PINNED_IDENTITY_MODULE_UNLOADABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_blob(revision:str,path:str)->bytes:
    need(SHA40.fullmatch(revision) is not None
         and path in packet.REVIEWED_PATHS,
         "GIT_SOURCE_SCOPE_NOT_REVIEWED")
    result=subprocess.run(
        ["/usr/bin/git","-C",str(REPO),"show",revision+":"+path],
        capture_output=True,timeout=20,check=False)
    need(result.returncode==0 and 0<len(result.stdout)<1_000_000,
         "EXACT_GIT_OBJECT_UNAVAILABLE")
    return result.stdout


def stage_packet(*,candidate:str,artifact:Path)->dict:
    need(os.geteuid()==1000,
         "LOCAL_OWNER_SERVICE_USER_REQUIRED")
    need(SHA40.fullmatch(candidate) is not None,
         "CANDIDATE_SHA_INVALID")
    need(artifact.is_absolute() and artifact.parent==ARTIFACTS
         and artifact.name.startswith("pmv4-e-source-only-")
         and not artifact.is_symlink(),
         "UNREVIEWED_ARTIFACT_PATH")
    a=artifact.lstat()
    need(stat.S_ISDIR(a.st_mode)
         and a.st_uid==a.st_gid==1000
         and stat.S_IMODE(a.st_mode)==0o700,
         "STAGED_ARTIFACT_NOT_PRIVATE")
    # Verify an inert, unprivileged review-only Git clone. Never fetch or
    # change the installed engineering-worker/source repositories while the
    # production freeze is active.
    meta=REPO.lstat()
    need(REPO.parent==ARTIFACTS and not REPO.is_symlink()
         and stat.S_ISDIR(meta.st_mode)
         and meta.st_uid==meta.st_gid==1000
         and stat.S_IMODE(meta.st_mode)==0o700,
         "ISOLATED_REVIEW_REPOSITORY_UNTRUSTED")
    present=subprocess.run(
        ["/usr/bin/git","-C",str(REPO),
         "cat-file","-e",candidate+"^{commit}"],
        capture_output=True,check=False,timeout=20)
    protected=subprocess.run(
        ["/usr/bin/git","-C",str(REPO),
         "merge-base","--is-ancestor",candidate,"origin/main"],
        capture_output=True,check=False,timeout=20)
    need(present.returncode==0 and protected.returncode==0,
         "CANDIDATE_NOT_ON_REVIEWED_PROTECTED_MAIN")
    need(Path(__file__).read_bytes()==git_blob(
         candidate,"tools/pmv4_e_exact_owner_offer.py"),
         "EXECUTING_NONREVIEWED_OWNER_SOURCE")
    for name in ("manifest.json","source-scope.json"):
        p=artifact/name
        meta=p.lstat()
        need(stat.S_ISREG(meta.st_mode)
             and not p.is_symlink()
             and meta.st_uid==meta.st_gid==1000
             and meta.st_nlink==1
             and stat.S_IMODE(meta.st_mode)==0o400,
             "STAGED_MANIFEST_NOT_IMMUTABLE")
    manifest=json.loads((artifact/"manifest.json").read_bytes())
    scope=json.loads((artifact/"source-scope.json").read_bytes())
    need(type(manifest) is dict and type(scope) is dict
         and manifest.get("candidate_sha")==candidate
         and manifest.get("rollback_sha")==ROLLBACK,
         "OWNER_RELEASE_CANDIDATE_OR_ROLLBACK_MISMATCH")
    # Every reviewed source byte must be the exact protected Git blob;
    # unlike mutable worktrees, this check includes the executable itself.
    for relative in packet.REVIEWED_PATHS:
        need(packet.read_reviewed(packet.ROOT,relative)==
             git_blob(candidate,relative),
             "OWNER_REVIEWED_GIT_SOURCE_CHANGED")
    reviewed=contract.validate(manifest,scope,source_root=packet.ROOT)
    need(reviewed["manifest_sha256"]==sha256(
         packet.canonical(manifest)).hexdigest(),
         "SIGNED_MANIFEST_DIGEST_NOT_EXACT")
    need(sha256(FREEZE.read_bytes()).hexdigest()==manifest["freeze_sha256"],
         "LIVE_FREEZE_CHANGED")
    # Source checks are not a substitute for the separately privileged root
    # attestor, which independently validates again before any host mutation.
    need(not (artifact/"owner-proof.json").exists(),
         "OWNER_APPROVAL_ALREADY_ISSUED")
    return {"manifest":manifest,"scope":scope,
            "candidate":candidate,"rollback":ROLLBACK,
            "scope_sha256":manifest["source_scope_sha256"],
            "manifest_sha256":reviewed["manifest_sha256"],
            "freeze_sha256":manifest["freeze_sha256"]}


def checked_identity():
    signer=pinned_module(ISSUER,ISSUER_SHA,
                         "pmv4_e_original_owner_signer")
    oauth=pinned_module(OAUTH,OAUTH_SHA,
                        "pmv4_e_original_owner_oauth")
    meta=PRIVATE.lstat()
    need(not PRIVATE.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid==1000 and
         stat.S_IMODE(meta.st_mode)==0o400 and meta.st_size==32,
         "OWNER_PRIVATE_SIGNER_NOT_AVAILABLE")
    private=Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    public=signer.read_pinned_root_owner_public_key(
        PUBLIC,require_root_owned=True)
    need(signer.public_key_sha256(public)==
         signer.public_key_sha256(private.public_key()),
         "OWNER_SIGNER_ROOT_PUBLIC_KEY_MISMATCH")
    return signer,oauth,private


def authenticate_owner(oauth,plan)->str:
    login="https://login.microsoftonline.com/"+oauth.TENANT+"/oauth2/v2.0/"
    challenge=oauth._form(login+"devicecode",{
        "client_id":oauth.CLIENT_ID,"scope":oauth.SCOPE})
    need(all(isinstance(challenge.get(k),str) for k in
             ("device_code","user_code","verification_uri")),
         "AUTHENTICATED_DEVICE_CHALLENGE_INVALID")
    duration=min(600,int(challenge.get("expires_in",0)))
    need(duration>=60,"DEVICE_AUTHENTICATION_TOO_SHORT")
    print("STAGE_E_ACTION="+packet.ACTION,flush=True)
    print("REVIEWED_CANDIDATE_SHA="+plan["candidate"],flush=True)
    print("EXACT_ROLLBACK_SHA="+plan["rollback"],flush=True)
    print("EXACT_SCOPE_SHA256="+plan["scope_sha256"],flush=True)
    print("MANIFEST_SHA256="+plan["manifest_sha256"],flush=True)
    print("PROTECTED_RUNTIME_MCP_RESTARTS=0;PROVIDER_WRITES=0",flush=True)
    print("ONE_OWNER_APPROVAL_ONLY=true;NOT_STANDING_AUTHORITY=true",flush=True)
    print("ENTRA_VERIFICATION_URI="+challenge["verification_uri"],flush=True)
    print("ENTRA_USER_CODE="+challenge["user_code"],flush=True)
    deadline=time.monotonic()+duration
    interval=max(5,min(20,int(challenge.get("interval",5))))
    while time.monotonic()<deadline:
        token=oauth._form(login+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":oauth.CLIENT_ID,
            "device_code":challenge["device_code"],
        })
        if isinstance(token.get("access_token"),str):
            oid=oauth.jwt_owner(token["access_token"])
            token=None
            value=input("Confirm EXACT "+CONFIRM+": ")
            need(value.strip()==CONFIRM,"EXACT_OWNER_DECISION_NOT_GIVEN")
            return oid
        if token.get("error")=="slow_down":
            interval=min(20,interval+5)
        else:
            need(token.get("error")=="authorization_pending",
                 "ENTRA_OWNER_AUTHENTICATION_REJECTED")
        time.sleep(interval)
    raise ExactOwnerOfferDenied("PMV4_E_OWNER_AUTHENTICATION_EXPIRED")


def signed_request(plan,*,signer,private,owner_oid:str,at=None):
    principal=signer.EXACT_OWNER_OAUTH_SUBJECTS.get(owner_oid)
    need(type(principal) is str and principal,
         "AUTHENTICATED_OWNER_NOT_BOUND")
    timestamp=at or datetime.now(timezone.utc)
    proof=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+uuid4().hex,
        release_id="release-"+plan["candidate"][:16],
        candidate_sha=plan["candidate"],
        rollback_sha=plan["rollback"],
        scope_sha256=plan["scope_sha256"],
        manifest_sha256=plan["manifest_sha256"],
        freeze_sha256=plan["freeze_sha256"],
        verified_tenant_id=signer.TID,
        verified_owner_oid=owner_oid,
        verified_principal=principal,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=timestamp,private_key=private,
    )
    signer.verify_exact_owner_release(
        proof,public_key=private.public_key(),
        expected_candidate_sha=plan["candidate"],
        expected_rollback_sha=plan["rollback"],
        expected_release_id="release-"+plan["candidate"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=plan["manifest_sha256"],
        expected_freeze_sha256=plan["freeze_sha256"],
        at=timestamp,
    )
    return {
        "schema_version":"1.0",
        "request_id":"release-"+plan["candidate"][:16],
        "action":bootstrap.BOOTSTRAP_ACTION,
        "candidate_sha":plan["candidate"],
        "rollback_sha":plan["rollback"],
        "scope_sha256":plan["scope_sha256"],
        "manifest_sha256":plan["manifest_sha256"],
        "freeze_sha256":plan["freeze_sha256"],
        "signed_owner_proof":proof,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate-sha",required=True)
    parser.add_argument("--artifact-dir",required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--approve",action="store_true")
    args=parser.parse_args(argv)
    candidate=args.candidate_sha
    reviewed=stage_packet(
        candidate=candidate,artifact=Path(args.artifact_dir))
    signer,oauth,private=checked_identity()
    if args.check_only:
        print("SOURCE_AND_OWNER_SIGNER_BOUND=PASS")
        print("OWNER_PROOF_ISSUED=false;PRODUCTION_MUTATIONS=false")
        return 0
    owner=authenticate_owner(oauth,reviewed)
    signed=signed_request(
        reviewed,signer=signer,private=private,owner_oid=owner)
    path=Path(args.artifact_dir)/"owner-proof.json"
    raw=packet.canonical(signed)+b"\n"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o400)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        need(path.lstat().st_uid==1000
             and stat.S_IMODE(path.lstat().st_mode)==0o400
             and path.read_bytes()==raw,
             "EXACT_OWNER_PROOF_READBACK_FAILED")
    except BaseException:
        raise
    print("SIGNED_ONE_USE_ENTRA_OWNER_RELEASE_PROOF=VERIFIED")
    print("PRODUCTION_MUTATIONS=false;ROOT_INSTALL_NOT_EXECUTED=true")
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ExactOwnerOfferDenied,PermissionError,OSError,ValueError) as exc:
        print("PMV4_E_OWNER_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:120] if isinstance(exc,PermissionError) else ""),
              file=sys.stderr)
        raise SystemExit(2)
