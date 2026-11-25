"""Independent Root reads current canonical identity, binding and exact grants."""
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3

import pytest
from tools.owner_objective_root_worker import active_owner

OWNER="person-licensed"
SERVICE="registered-service"
CAPS=("release.documentation.publisher.restore","release.documentation.publisher.verify",
      "interaction.owner.acceptance.record")


@pytest.fixture
def authority(tmp_path):
    bindings,core=tmp_path/"bindings.db",tmp_path/"authority.db"
    with sqlite3.connect(bindings) as db:
        db.execute("CREATE TABLE microsoft_identity_bindings (microsoft_tenant_id,microsoft_object_id,jason_identity_id,client_id,status)")
        db.execute("INSERT INTO microsoft_identity_bindings VALUES (?,?,?,?,?)",("tenant","owner-oid",OWNER,None,"active"))
    with sqlite3.connect(core) as db:
        db.execute("CREATE TABLE identities (identity_id PRIMARY KEY,payload)")
        db.execute("CREATE TABLE authority_grants (grant_id PRIMARY KEY,payload)")
        for subject,kind in ((OWNER,"human"),(SERVICE,"service")):
            db.execute("INSERT INTO identities VALUES (?,?)",(subject,json.dumps(
                dict(identity_id=subject,identity_type=kind,organization_id="aot",status="active"))))
        hashes={}
        for subject in (OWNER,SERVICE):
            for index,cap in enumerate(CAPS):
                identifier=subject+str(index)
                grant=dict(grant_id=identifier,subject_id=subject,capability=cap,organization_id="aot",
                    client_id=None,permission="execute",approval_required=subject==SERVICE,
                    effective_from=None,effective_until=None,status="active")
                raw=json.dumps(grant,sort_keys=True,separators=(",",":"))
                hashes[identifier]=sha256(raw.encode()).hexdigest()
                db.execute("INSERT INTO authority_grants VALUES (?,?)",(identifier,raw))
    config=dict(tenant_id="tenant",owner_oid="owner-oid",owner_identity_id=OWNER,
        requester_identity_id=SERVICE,bindings_db=str(bindings),authority_db=str(core),
        required_grants_sha256=hashes)
    return config,core,bindings


def test_exact_current_registered_authority_is_accepted_read_only(authority):
    config,core,bindings=authority
    before=(core.read_bytes(),bindings.read_bytes())
    assert active_owner(config,"tenant","owner-oid")==OWNER
    assert before==(core.read_bytes(),bindings.read_bytes())


@pytest.mark.parametrize("target",["owner_identity","service_identity","binding","owner_grant","service_grant"])
def test_revocation_is_visible_to_root_before_next_step(authority,target):
    config,core,bindings=authority
    assert active_owner(config,"tenant","owner-oid")==OWNER
    if target=="binding":
        with sqlite3.connect(bindings) as db:db.execute("UPDATE microsoft_identity_bindings SET status='revoked'")
    elif target.endswith("identity"):
        subject=OWNER if target.startswith("owner") else SERVICE
        with sqlite3.connect(core) as db:
            payload=json.loads(db.execute("SELECT payload FROM identities WHERE identity_id=?",(subject,)).fetchone()[0])
            payload["status"]="revoked"
            db.execute("UPDATE identities SET payload=? WHERE identity_id=?",(json.dumps(payload),subject))
    else:
        identifier=(OWNER if target.startswith("owner") else SERVICE)+"0"
        with sqlite3.connect(core) as db:
            payload=json.loads(db.execute("SELECT payload FROM authority_grants WHERE grant_id=?",(identifier,)).fetchone()[0])
            payload["status"]="revoked"
            db.execute("UPDATE authority_grants SET payload=? WHERE grant_id=?",(json.dumps(payload),identifier))
    assert active_owner(config,"tenant","owner-oid") is None


def test_missing_exact_grant_cannot_fall_back_to_unrelated_wildcard_authority(authority):
    config,core,bindings=authority
    config["required_grants_sha256"].pop(OWNER+"0")
    assert active_owner(config,"tenant","owner-oid") is None
