#!/usr/bin/env python3
"""Renew and promote only the accepted catalog image pair using root trust.

The first signed Owner image approval expired unconsumed. It is immutable.
This entrypoint cannot delete/update that approval or touch root release state;
it can queue a new one-use signed Owner approval only after verified Entra OAuth
and exact terminal consent. The existing privileged root worker owns all image
changes, acceptance and paired rollback.
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
import tempfile
import time

ART=Path("/srv/jason/archive/engineering-artifacts/catalog-isolated-release-20261119")
BASE=ART/"approve_and_promote_exact_catalog.py"
BASE_SHA256="e4c21b48829ea3f1787fe2557e39bb97eae4284bf73fedc7a9ee09b38c4d11ff"
NEW_HOST=Path("/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_host.py")
NEW_ROUTER=Path("/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_root.py")
NEW_HOST_SHA="39b51dda22be70f2468493fc68574fd4085713506d5a270aee863cf8fb697e9d"
NEW_ROUTER_SHA="9d34a497012816cc8b4c1dbcbe5ee5c55a644a3bc0ceb188f2e5e3c908160e66"
RENEWAL_REL="tools/catalog_scoped_owner_approval_renewal.py"
RENEWAL_SHA="35c778618f8c7332a941641800a0af3ef2ebcf0cc37cb833696df3dae73f3389"
WORD="APPROVE_EXACT_CATALOG_SCOPED_RUNTIME_MCP_RENEWAL"
RELEASE="release-755fa5fe3f75958f"
CANDIDATE="755fa5fe3f75958fee2427a0af0777dd242d8f00"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FROZEN="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
RENEWALS=Path("/var/lib/jason/authority/catalog-scoped-release/owner-approval-renewals")
ROOT=Path("/usr/local/lib/jason/catalog-scoped-promotion")

def denied(label:str):
    raise PermissionError("EXACT_CATALOG_RENEWAL_DENIED_"+label)

def sha(raw:bytes)->str:
    return sha256(raw).hexdigest()

def original_base():
    if BASE.is_symlink() or not BASE.is_file():
        denied("BASE_SCRIPT_UNTRUSTED")
    info=BASE.stat()
    if info.st_uid!=1000 or stat.S_IMODE(info.st_mode)!=0o500 or info.st_nlink!=1:
        denied("BASE_SCRIPT_OWNERSHIP_CHANGED")
    if sha(BASE.read_bytes())!=BASE_SHA256:
        denied("EXACT_REVIEWED_OWNER_ISSUER_CHANGED")
    spec=importlib.util.spec_from_file_location("catalog_root_reviewed_existing_owner_issuer",BASE)
    if spec is None or spec.loader is None:denied("EXACT_ISSUER_MODULE_UNAVAILABLE")
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    # New exact decision replaces only the old EXPIRED proof; no old issuer call.
    result.EXPECTED_WORDS=WORD
    result.MODE="--execute"
    sys.path.insert(0,str(ROOT))
    sys.path.insert(0,str(ROOT/"implementation"))
    return result

def get_main(m):
    m.run("git","-C",str(m.GIT),"fetch","origin","main",timeout=90)
    main=m.run("git","-C",str(m.GIT),"ls-remote","origin","refs/heads/main",timeout=30).split()[0]
    if not re.fullmatch(r"[a-f0-9]{40}",main):denied("UNVERIFIED_MAIN")
    if m.run("git","-C",str(m.GIT),"rev-parse","origin/main").strip()!=main:
        denied("PROTECTED_MAIN_NOT_SYNCED")
    return main

def source_main(m,main):
    dest=Path("/srv/jason/archive/engineering-worktrees")/(
        "catalog-renewal-main-"+main[:12]+"-20261119")
    if dest.is_symlink():denied("SOURCE_WORKTREE_SYMLINK")
    if not dest.exists():
        m.run("git","-C",str(m.GIT),"worktree","add","--detach",
              str(dest),main,timeout=90)
    if (m.run("git","-C",str(dest),"rev-parse","HEAD").strip()!=main
            or m.run("git","-C",str(dest),"status","--porcelain").strip()):
        denied("PROTECTED_SOURCE_CHECKOUT_CHANGED")
    m.SOURCE=dest
    return dest

def load_offer(m):
    from tools.catalog_scoped_promotion import validate_offer
    o=validate_offer(json.loads(m.trusted_read(m.OFFER,1000,0o600,maximum=16384)))
    if (o["release_id"]!=RELEASE or o["candidate_sha"]!=CANDIDATE
            or o["rollback_sha"]!=ROLLBACK
            or o["freeze_sha256"]!=FROZEN
            or o["one_transaction_only"] is not True
            or o["no_global_owner_expansion"] is not True
            or o["separate_owner_approval_required"] is not True
            or o.get("status")!="awaiting_exact_owner_approval"):
        denied("RELEASE_IMAGE_SCOPE_CHANGED")
    return o

def signed_predecessor(m):
    p=m.STATE/"owner-approvals"/(RELEASE+".json")
    original=m.trusted_read(p,1000,0o600,maximum=16384)
    row=json.loads(original)
    proof=(row.get("signed_owner_proof") or {}).get("payload") or {}
    if (row.get("release_id")!=RELEASE
            or row.get("candidate_sha")!=CANDIDATE
            or not re.fullmatch(r"owner-mcp-[a-f0-9]{32}",
                                str(proof.get("approval_id")))
            or proof.get("rollback_sha")!=ROLLBACK
            or proof.get("freeze_sha256")!=FROZEN
            or proof.get("manifest_sha256")!=row.get("manifest_sha256")
            or row.get("standing_authority") is not False
            or row.get("production_mutation") is not False):
        denied("EXPIRED_PREDECESSOR_SCOPE_INVALID")
    until=datetime.fromisoformat(proof["expires_at"])
    if until.tzinfo is None:denied("EXPIRED_PREDECESSOR_TIME_INVALID")
    if datetime.now(timezone.utc)<until:
        denied("PREVIOUS_OWNER_APPROVAL_STILL_ACTIVE")
    return row,sha(original)

def installed_catalog_recovery():
    for p,want in ((NEW_HOST,NEW_HOST_SHA),(NEW_ROUTER,NEW_ROUTER_SHA)):
        if p.is_symlink() or not p.is_file():
            denied("CATALOG_ROOT_MODULE_NOT_INSTALLED")
        meta=p.stat()
        if meta.st_uid!=0 or meta.st_mode&0o022 or sha(p.read_bytes())!=want:
            denied("CATALOG_ROOT_MODULE_NOT_TRUSTED")
    freeze=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
    if sha(freeze.read_bytes())!=FROZEN:denied("FREEZE_CHANGED")

ROOT_NATIVE_TX_PARENT=Path("/var/lib/jason-catalog-scoped-promotion")

def root_existing_attempt(m):
    """Attest only the root-private boundary; never traverse its transaction files.

    The uid-1000 issuer cannot inspect the root:root 0700 transaction journal.
    The installed SHA-pinned native root host, which holds the production lock,
    enforces deny_unresolved_previous_attempt and one-use durable intent for
    precisely this release. Absence of a public record is NOT proof of absence
    of a prior root transaction. An actual prior attempt remains root-denied.
    """
    if ROOT_NATIVE_TX_PARENT.is_symlink():
        denied("NATIVE_TRANSACTION_ROOT_SYMLINK")
    try:
        meta=ROOT_NATIVE_TX_PARENT.lstat()
    except OSError:
        denied("NATIVE_TRANSACTION_ROOT_UNAVAILABLE")
    if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid!=0
            or stat.S_IMODE(meta.st_mode)!=0o700 or meta.st_nlink<2):
        denied("NATIVE_TRANSACTION_ROOT_BOUNDARY_UNTRUSTED")
    return None

def queue_stage(m,main,offer_before):
    cli=[sys.executable,str(m.SOURCE/"tools/release_manager_host_runner.py"),
         "--repo",str(m.SOURCE),"catalog-scope-stage",
         "--release-id",RELEASE,"--protected-main-sha",main]
    env=os.environ.copy()
    env["PYTHONPATH"]=":".join((str(m.SOURCE),str(m.SOURCE/"tools"),
                                str(m.SOURCE/"implementation")))
    for attempt in range(2):
        result=subprocess.run(cli,env=env,capture_output=True,text=True,timeout=90)
        if result.returncode:denied("ROOT_STAGE_QUEUE_REJECTED")
        try:queued=json.loads(result.stdout)
        except ValueError:denied("ROOT_STAGE_QUEUE_INVALID")
        if (queued.get("status")!="queued_for_independent_root_validation_not_deployed"
                or queued.get("source_revision")!=main
                or queued.get("release_id")!=RELEASE
                or not re.fullmatch(r"[a-f0-9]{32}",
                                    str(queued.get("request_id")))):
            denied("ROOT_STAGE_REQUEST_NOT_BOUND")
        rid=queued["request_id"]
        receipt=m.RESULTS/(rid+".json")
        deadline=time.monotonic()+130
        while not receipt.exists() and time.monotonic()<deadline:
            time.sleep(2)
        if not receipt.exists():denied("ROOT_STAGE_TIMEOUT")
        native=json.loads(receipt.read_text())
        if (native.get("request_id")!=rid
                or native.get("source_revision")!=main):
            denied("ROOT_STAGE_RESPONSE_NOT_BOUND")
        if native.get("success") is True:
            detail=native.get("detail","")
            if not isinstance(detail,str) or not detail.startswith("CATALOG_SCOPE="):
                denied("ROOT_STAGE_RECEIPT_INVALID")
            accepted=json.loads(detail.partition("=")[2])
            if (accepted.get("status")!="catalog_offer_staged_without_mutation"
                    and accepted.get("status")!="catalog_unsigned_offer_restaged_without_production_mutation"):
                denied("ROOT_STAGE_NOT_VERIFIED")
            if (accepted.get("release_id")!=RELEASE
                    or accepted.get("source_sha")!=main
                    or accepted.get("candidate_sha")!=CANDIDATE
                    or accepted.get("production_mutations") is not False):
                denied("ROOT_STAGE_RECEIPT_CHANGED_SCOPE")
            return
        reason=str(native.get("detail",""))
        if attempt!=0 or reason!="HostReconcileError: CATALOG_SCOPED_ROOT_RECEIPT_INVALID":
            denied("ROOT_STAGE_FAILED_"+reason[:50].replace(" ","_"))
        # Root already atomically refreshed the offer but the old host worker
        # does not accept that first status string. Require exact unchanged
        # source/image/scope and a new independently successful root receipt.
        later=load_offer(m)
        if (later["protected_main_sha"]!=main
                or any(later[k]!=offer_before[k] for k in offer_before
                       if k not in ("protected_main_sha",
                                    "fresh_admission_receipt_sha256",
                                    "manifest_sha256"))):
            denied("ROOT_STAGE_CHANGED_IMAGE_OR_SCOPE")
        print("ROOT_STAGE_ACCEPTED_PENDING_INDEPENDENT_RECEIPT_RECHECK=true",flush=True)
    denied("ROOT_STAGE_NOT_COMPLETED")

def restage_to_latest_main(m):
    for attempt in range(3):
        main=get_main(m)
        source_main(m,main)
        before=load_offer(m)
        if before["protected_main_sha"]!=main:
            queue_stage(m,main,before)
        after=load_offer(m)
        if (after["protected_main_sha"]!=main
                or any(after[k]!=before[k] for k in before
                       if k not in ("protected_main_sha",
                                    "fresh_admission_receipt_sha256",
                                    "manifest_sha256"))):
            denied("FINAL_STAGE_SOURCE_OR_SCOPE_CHANGED")
        if m.run("git","-C",str(m.GIT),"ls-remote",
                 "origin","refs/heads/main").split()[0]==main:
            m.protected_main(after)
            return after
    denied("PROTECTED_MAIN_MOVED_DURING_CATALOG_STAGE")

def canonical_renewal(m,offer):
    source=m.SOURCE/RENEWAL_REL
    git_raw=m.run("git","-C",str(m.SOURCE),"show",
                  offer["protected_main_sha"]+":"+RENEWAL_REL).encode()
    if (sha(git_raw)!=RENEWAL_SHA or not source.is_file()
            or source.is_symlink() or source.read_bytes()!=git_raw):
        denied("CANONICAL_RENEWAL_ISSUER_SOURCE_NOT_REVIEWED")
    # The signer and root trust library are loaded only from installed,
    # root-owned catalog source. Use a read-only private temporary file
    # containing exact protected Git bytes, not a mutable worktree import.
    with tempfile.TemporaryDirectory(prefix="catalog-exact-owner-renewal-") as tmp:
        immutable=Path(tmp)/"source_bound_owner_renewal.py"
        immutable.write_bytes(git_raw);immutable.chmod(0o400)
        spec=importlib.util.spec_from_file_location(
            "verified_catalog_exact_owner_renewal_issuer",immutable)
        if spec is None or spec.loader is None:
            denied("CANONICAL_RENEWAL_ISSUER_UNAVAILABLE")
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if mod.APPROVAL_WORDS!=WORD:denied("CANONICAL_RENEWAL_EXACT_DECISION_CHANGED")
        return mod

def main():
    ap=argparse.ArgumentParser()
    opts=ap.add_mutually_exclusive_group(required=True)
    opts.add_argument("--check-only",action="store_true")
    opts.add_argument("--execute",action="store_true")
    flags=ap.parse_args()
    if os.geteuid()!=1000 or os.getuid()!=1000:denied("JASON_OPERATOR_REQUIRED")
    if flags.execute and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        denied("OWNER_TERMINAL_REQUIRED")
    m=original_base()
    installed_catalog_recovery()
    root_existing_attempt(m)
    signed_predecessor(m)
    m.service_controls()
    old_offer=load_offer(m)
    main_sha=get_main(m)
    source_main(m,main_sha)
    if flags.check_only:
        if old_offer["protected_main_sha"]!=main_sha:
            print("PROTECTED_MAIN_HAS_ADVANCED_SOURCE_ONLY_RESTAGE_REQUIRED=true")
        canonical_renewal(m,dict(old_offer,protected_main_sha=main_sha))
        print("CATALOG_SIGNED_RENEWAL_PREFLIGHT=PASS_NO_OWNER_AUTH_NO_PROVIDER_WRITES")
        return 0
    offer=restage_to_latest_main(m)
    module=canonical_renewal(m,offer)
    helper=m.owner_helper()
    signing=m.signer()
    print("EXACT_CATALOG_RELEASE="+RELEASE,flush=True)
    print("CANDIDATE_SOURCE="+CANDIDATE,flush=True)
    print("ROLLBACK_SOURCE="+ROLLBACK,flush=True)
    print("FROZEN_SHA256="+FROZEN,flush=True)
    print("PROTECTED_MAIN="+offer["protected_main_sha"],flush=True)
    print("MANIFEST_SHA256="+offer["manifest_sha256"],flush=True)
    print("PREDECESSOR_EXPIRED_UNCONSUMED_RECORD_PRESERVED=true",flush=True)
    claims=m.exact_owner_identity(helper)
    # Reconcile any separately merged PMv4 main changes before signing.
    previous=offer
    offer=restage_to_latest_main(m)
    module=canonical_renewal(m,offer)
    m.service_controls()
    if any(offer[k]!=previous[k] for k in previous
           if k not in ("protected_main_sha",
                        "fresh_admission_receipt_sha256","manifest_sha256")):
        denied("CANDIDATE_SCOPE_CHANGED_DURING_ENTRA_AUTH")
    print("APPROVE_EXACT_PROTECTED_MAIN="+offer["protected_main_sha"],flush=True)
    print("APPROVE_EXACT_CATALOG_MANIFEST_SHA256="+offer["manifest_sha256"],flush=True)
    print("APPROVE_EXACT_RUNTIME_MCP_IMAGE_PAIR_ONLY=true",flush=True)
    if input("Type "+WORD+" to approve ONLY a fresh exact catalog image pair: ").strip()!=WORD:
        denied("EXACT_OWNER_DECISION_REQUIRED")
    m.protected_main(offer)
    m.service_controls()
    signed_predecessor(m)
    from implementation.kernel.signed_owner_release import EXACT_OWNER_OAUTH_SUBJECTS
    principal=EXACT_OWNER_OAUTH_SUBJECTS.get(claims.get("oid"))
    if not principal:denied("OWNER_SUBJECT_NOT_IN_PINNED_GOVERNANCE")
    new=module.queue_exact_catalog_owner_renewal(
        state_root=m.STATE,release_id=RELEASE,candidate_sha=CANDIDATE,
        manifest_sha256=offer["manifest_sha256"],
        approved_by=principal,organization_id="aot",
        verified_token_claims=claims,service_signer=signing,
        affirmative_decision=WORD)
    print("FRESH_SIGNED_OWNER_CATALOG_RENEWAL_ID="+new["approval_id"],flush=True)
    print("EXPIRED_PREDECESSOR_AUDIT_ID="+new["predecessor_approval_id"],flush=True)
    # Any rejection leaves signed proof immutable: never reissue in this run.
    m.promote_request(offer,new)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
