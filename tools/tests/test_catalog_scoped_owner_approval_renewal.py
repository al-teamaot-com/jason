"""Cryptographic, append-only exact catalog Owner proof renewal after expiry."""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from pathlib import Path
from hashlib import sha256
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release, canonical,
)
from tools import catalog_scoped_owner_approval_renewal as issuer
from tools import catalog_scoped_promotion_root as root
from tools.tests.test_catalog_scoped_promotion import offer as sample_offer
from tools.tests.test_catalog_unsigned_offer_safe_restage import refresh

OWNER_OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
TID="f7054323-d52b-4863-8c2f-1898f0b6077c"
PRINCIPAL=EXACT_OWNER_OAUTH_SUBJECTS[OWNER_OID]


def save(path,value,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    path.write_bytes(json.dumps(value,sort_keys=True,separators=(",",":")).encode()+b"\n")
    path.chmod(mode)
    return path


@pytest.fixture
def scenario(tmp_path,monkeypatch):
    key=Ed25519PrivateKey.generate()
    old=sample_offer()
    latest=refresh(old)
    state=tmp_path/"authority"
    state.mkdir(mode=0o700)
    lock=tmp_path/"native-production-lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    old_time=datetime.now(timezone.utc)-timedelta(minutes=21)
    signed=issue_exact_owner_release(
        approval_id="owner-mcp-"+"a"*32,release_id=old["release_id"],
        candidate_sha=old["candidate_sha"],rollback_sha=old["rollback_sha"],
        scope_sha256=old["scope_sha256"],manifest_sha256=old["manifest_sha256"],
        freeze_sha256=old["freeze_sha256"],verified_tenant_id=TID,
        verified_owner_oid=OWNER_OID,verified_principal=PRINCIPAL,
        verified_organization_id="aot",confirmed_decision="approve",
        at=old_time,private_key=key)
    wrapper={
        "schema_version":"1.0","authorization":"fresh_entra_catalog_scoped_owner",
        "release_id":old["release_id"],"candidate_sha":old["candidate_sha"],
        "manifest_sha256":old["manifest_sha256"],"approved_by":PRINCIPAL,
        "organization_id":"aot","signed_owner_proof":signed,
        "standing_authority":False,"production_mutation":False,
    }
    old_path=save(state/"owner-approvals"/(old["release_id"]+".json"),wrapper)
    save(state/"offers"/(latest["release_id"]+".json"),latest)
    class FakeRootHost:
        def consumed_approval_ids(self):
            return frozenset()
        def pinned_owner_public_key(self):
            return key.public_key()
    monkeypatch.setattr(root,"AUTH_ROOT",state)
    # CI runners do not provision the production-only 'al' account.
    # Keep the production lookup unchanged and model its exact UID in tests.
    from types import SimpleNamespace
    monkeypatch.setattr(root.pwd,"getpwnam",
                        lambda name:SimpleNamespace(
                            pw_uid=os.getuid(),pw_gid=os.getgid())
                        if name=="al" else (_ for _ in ()).throw(KeyError(name)))
    return key,old,latest,state,lock,signed,old_path,FakeRootHost()


def issue(s):
    key,old,current,state,lock,original,original_path,host=s
    return issuer.queue_exact_catalog_owner_renewal(
        state_root=state,release_id=current["release_id"],
        candidate_sha=current["candidate_sha"],manifest_sha256=current["manifest_sha256"],
        approved_by=PRINCIPAL,organization_id="aot",
        verified_token_claims={"oid":OWNER_OID,"tid":TID},
        service_signer=key,affirmative_decision=issuer.APPROVAL_WORDS,lock_path=lock,
    )


def test_expired_original_alone_cannot_authorize_refreshed_source(scenario):
    key,old,current,state,lock,original,original_path,host=scenario
    with pytest.raises(PermissionError,match="SIGNED_OWNER_RENEWAL_NOT_BOUND_TO_CURRENT_OFFER"):
        root._signed_approval(current["release_id"],current,host)
    assert json.loads(original_path.read_text())["signed_owner_proof"]==original


def test_new_exact_owner_renewal_is_immutable_bound_and_root_accepts(scenario):
    key,old,current,state,lock,original,original_path,host=scenario
    before=original_path.read_bytes()
    answer=issue(scenario)
    assert answer["status"]=="renewal_signed_once_not_deployed"
    assert answer["production_mutation"] is False
    signed=root._signed_approval(current["release_id"],current,host)
    assert signed["payload"]["approval_id"]==answer["approval_id"]
    assert signed["payload"]["manifest_sha256"]==current["manifest_sha256"]
    assert signed["payload"]["rollback_sha"]==old["rollback_sha"]
    assert original_path.read_bytes()==before
    child=state/"owner-approval-renewals"/old["release_id"]/(answer["approval_id"]+".json")
    line=json.loads(child.read_text())
    assert line["predecessor_approval_id"]==original["payload"]["approval_id"]
    assert line["predecessor_signed_owner_proof_sha256"]==sha256(canonical(original)).hexdigest()
    assert child.stat().st_mode & 0o777==0o600


def test_issued_renewal_does_not_permit_reapproval_until_expired(scenario):
    issue(scenario)
    with pytest.raises(PermissionError,match="PREDECESSOR_NOT_EXPIRED"):
        issue(scenario)


@pytest.mark.parametrize("mutator",[
    lambda child:child.__setitem__("predecessor_approval_id","owner-mcp-"+"f"*32),
    lambda child:child.__setitem__("predecessor_signed_owner_proof_sha256","f"*64),
    lambda child:child.__setitem__("manifest_sha256","f"*64),
    lambda child:child.__setitem__("standing_authority",True),
    lambda child:child.__setitem__("production_mutation",True),
])
def test_root_rejects_tampered_renewal_chain(scenario,mutator):
    key,old,current,state,lock,original,original_path,host=scenario
    a=issue(scenario)
    p=state/"owner-approval-renewals"/current["release_id"]/(a["approval_id"]+".json")
    row=json.loads(p.read_text())
    mutator(row)
    save(p,row)
    with pytest.raises(PermissionError):
        root._signed_approval(current["release_id"],current,host)


def test_root_rejects_consumed_old_proof_even_with_new_one(scenario):
    key,old,current,state,lock,original,original_path,host=scenario
    issue(scenario)
    host.consumed_approval_ids=lambda:frozenset({original["payload"]["approval_id"]})
    with pytest.raises(PermissionError,match="SIGNED_OWNER_RENEWAL_PREDECESSOR_CONSUMED"):
        root._signed_approval(current["release_id"],current,host)


def test_root_rejects_fork_or_unknown_record(scenario):
    key,old,current,state,lock,original,original_path,host=scenario
    issue(scenario)
    folder=state/"owner-approval-renewals"/current["release_id"]
    (folder/"not-reviewed.txt").write_text("untrusted")
    with pytest.raises(PermissionError,match="SIGNED_OWNER_RENEWAL_UNEXPECTED_RECORD"):
        root._signed_approval(current["release_id"],current,host)


def test_issuer_refuses_wrong_owner_and_no_exact_terminal_action(scenario):
    key,old,current,state,lock,original,original_path,host=scenario
    with pytest.raises(PermissionError,match="EXACT_OWNER_TERMINAL_DECISION_REQUIRED"):
        issuer.queue_exact_catalog_owner_renewal(
            state_root=state,release_id=current["release_id"],
            candidate_sha=current["candidate_sha"],manifest_sha256=current["manifest_sha256"],
            approved_by=PRINCIPAL,organization_id="aot",
            verified_token_claims={"oid":OWNER_OID,"tid":TID},
            service_signer=key,affirmative_decision="APPROVE_ANYTHING",lock_path=lock)
    with pytest.raises(PermissionError,match="RENEWAL_OWNER_IDENTITY_NOT_ORIGINAL"):
        issuer.queue_exact_catalog_owner_renewal(
            state_root=state,release_id=current["release_id"],
            candidate_sha=current["candidate_sha"],manifest_sha256=current["manifest_sha256"],
            approved_by=EXACT_OWNER_OAUTH_SUBJECTS["c848022d-e13b-4457-84b0-e2f5c00dcaf6"],
            organization_id="aot",
            verified_token_claims={"oid":"c848022d-e13b-4457-84b0-e2f5c00dcaf6","tid":TID},
            service_signer=key,affirmative_decision=issuer.APPROVAL_WORDS,lock_path=lock)
