"""V5 independent host consumer: signed root acceptance, no Teams impersonation."""
from __future__ import annotations
from datetime import timedelta
from hashlib import sha256
import json,os,sqlite3,uuid
from pathlib import Path
from cryptography.hazmat.primitives import serialization
import pytest

from tools.release_v5_browser_consumer import consume_v5_browser_release_decisions
from implementation.runtime_service.tests.v5_synthetic_identity import AOT_ADMIN_OID,AOT_TENANT,AOT_OWNER_ROLE
from implementation.runtime_service.tests.test_release_v5_browser_flow import _fixture
from implementation.runtime_service.tests.test_mobile_release_approval import NOW,RELEASE


def _host_state(tmp_path):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    bind=tmp_path/"bindings.sqlite3"
    con=sqlite3.connect(bind)
    con.execute("""CREATE TABLE microsoft_identity_bindings(
      microsoft_tenant_id TEXT,microsoft_object_id TEXT,jason_identity_id TEXT,
      client_id TEXT,email_address TEXT,status TEXT)""")
    ident="person-entra-"+uuid.UUID(AOT_ADMIN_OID).hex
    con.execute("INSERT INTO microsoft_identity_bindings VALUES (?,?,?,?,?,?)",
      (AOT_TENANT,AOT_ADMIN_OID,ident,None,"admin@example.org","active"))
    con.commit();con.close()
    auth=tmp_path/"authority.sqlite3"
    con=sqlite3.connect(auth)
    con.execute("CREATE TABLE identities(identity_id TEXT PRIMARY KEY,payload TEXT)")
    con.execute("INSERT INTO identities VALUES (?,?)",(ident,json.dumps({
        "identity_id":ident,"identity_type":"human",
        "organization_id":"aot","status":"active",
    })))
    con.commit();con.close()
    pub=root/"v5-owner-approval-public-key.raw"
    pub.write_bytes(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ));pub.chmod(0o600)
    ccc=tmp_path/"ccc";ccc.mkdir(mode=0o700)
    original=flow.signed_evidence.path
    return flow,req,db,policy,key,proof,ca_path,root,bind,auth,pub,ccc,original


def _consume(items,approve,**kwargs):
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    params=dict(
        repo=root,state_root=root,approve_release=approve,
        record_initial_unfreeze=None,database=source,
        policy_file=flow.policy_path,ccc_root=ccc,
        bindings_db=bind,authority_db=auth,
        protected_main_sha_reader=lambda repo:req.metadata["candidate_sha"],
        public_key_path=pub,ca_attestation_path=ca,
        clock=lambda:NOW+timedelta(seconds=6),
    )
    params.update(kwargs)
    return consume_v5_browser_release_decisions(**params)


def test_existing_host_consumes_exact_admin_signed_decision_once(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(
        approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5),
    )
    grants=[]
    def approve(repo,state_root,**kwargs):
        grants.append(kwargs)
    assert _consume(items,approve)==1
    assert grants==[{
        "release_id":RELEASE,
        "candidate_sha":req.metadata["candidate_sha"],
        "source":"authenticated_entra_browser_owner:"+req.approval_id,
    }]
    review=json.loads((ccc/"material-review.json").read_text())
    assert review["recorded_by"]=="person-al"
    assert review["source_revision"]==req.metadata["candidate_sha"]
    assert "Entra admin browser" in review["reason"]
    assert _consume(items,approve)==0
    assert len(grants)==1


def test_denial_never_generates_release_or_ccc_approval(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(approval_id=req.approval_id,decision="deny",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5))
    grants=[]
    assert _consume(items,lambda *a,**kw:grants.append(kw))==1
    assert not grants
    assert not (ccc/"material-review.json").exists()
    assert _consume(items,lambda *a,**kw:grants.append(kw))==0


def test_wrong_public_key_cannot_become_root_release(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5))
    pub.write_bytes(b"x"*32)
    with pytest.raises(PermissionError,match="ROOT_BROWSER_KEY_MISMATCH"):
        _consume(items,lambda *a,**kw:pytest.fail("no release expected"))


def test_active_admin_identity_binding_cannot_be_swapped(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5))
    con=sqlite3.connect(bind)
    con.execute("UPDATE microsoft_identity_bindings SET microsoft_object_id=?",(
        "00000000-0000-0000-0000-000000000001",))
    con.commit();con.close()
    with pytest.raises(PermissionError,match="ADMIN_OWNER_BINDING_NOT_ACTIVE"):
        _consume(items,lambda *a,**kw:pytest.fail("no release expected"))


def test_protected_main_sha_drift_is_not_authority(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5))
    with pytest.raises(PermissionError,match="CANDIDATE_NOT_PROTECTED_MAIN"):
        _consume(items,lambda *a,**kw:pytest.fail("no release expected"),
            protected_main_sha_reader=lambda repo:"0"*40)


def test_unreviewed_root_ca_receipt_cannot_authorize_browser_decision(tmp_path):
    items=_host_state(tmp_path)
    flow,req,db,policy,key,proof,ca,root,bind,auth,pub,ccc,source=items
    flow.handle(approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5))
    ca.unlink()
    with pytest.raises(PermissionError,match="ATTESTATION_MISSING"):
        _consume(items,lambda *a,**kw:pytest.fail("no release expected"))
