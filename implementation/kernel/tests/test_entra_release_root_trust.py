"""Root-owned Ed25519 verification guard for the existing release controller."""
from base64 import b64encode
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pytest

from kernel.entra_release_root_trust import (
    BrowserReleaseRootTrustDenied, read_root_browser_release_trust,
)
from jason_mcp.entra_release_browser_decision import (
    create_browser_decision_envelope, verify_browser_decision_envelope,
)
from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute

TENANT="11111111-1111-4111-8111-111111111111"
ADMIN="33333333-3333-4333-8333-333333333333"
REGULAR="22222222-2222-4222-8222-222222222222"
POLICY="a"*64
NOW=datetime.now(timezone.utc).replace(microsecond=0)
RELEASE=ExactRelease(
    approval_id="relapproval-"+"b"*32,candidate_sha="c"*40,
    rollback_sha="d"*40,scope_sha256="e"*64,
    manifest_sha256="f"*64,expires_at=NOW+timedelta(minutes=10),
)
ROUTE=ReleaseIdentityRoute(
    tenant_id=TENANT,regular_teams_oid=REGULAR,admin_approver_oid=ADMIN,
    owner_subject_id="owner-fixture-01",
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def info(key):
    return {
        "schema_version":"1.0","channel":"entra_browser_admin",
        "tenant_id":TENANT,"admin_approver_oid":ADMIN,
        "organization_id":"synthetic-org","reviewed_policy_sha256":POLICY,
        "keys":[{
            "key_id":"reviewed-v5-signing-key",
            "public_key_b64":b64encode(key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )).decode("ascii"),
            "state":"active",
        }],
    }


def read(path):
    return read_root_browser_release_trust(
        path,expected_tenant_id=TENANT,expected_admin_oid=ADMIN,
        expected_organization="synthetic-org",expected_policy_sha256=POLICY,
    )


def write(tmp_path, doc):
    p=tmp_path/"reviewed-trust.json"
    p.write_text(json.dumps(doc)+"\n")
    p.chmod(0o600)
    return p


def test_root_trust_and_independent_signed_decision_host_validation(tmp_path):
    key=Ed25519PrivateKey.generate()
    trust=read(write(tmp_path,info(key)))
    assert trust.approved_key_ids==("reviewed-v5-signing-key",)
    proof={
        "authenticated_admin_oid":ADMIN,"tenant_id":TENANT,
        "owner_subject_id":ROUTE.owner_subject_id,"approval_id":RELEASE.approval_id,
        "channel":"microsoft_entra_browser_stepup","candidate_sha":RELEASE.candidate_sha,
        "scope_sha256":RELEASE.scope_sha256,"rollback_sha":RELEASE.rollback_sha,
        "manifest_sha256":RELEASE.manifest_sha256,
        "auth_time":int(NOW.timestamp())-50,
        "evidence_sha256":"1"*64,"release_authorized":False,
    }
    signed=create_browser_decision_envelope(
        approval=RELEASE,route=ROUTE,verified_login_proof=proof,
        decision="approve",signing_key=key,key_id="reviewed-v5-signing-key",now=NOW,
    )
    result=verify_browser_decision_envelope(
        signed,approval=RELEASE,route=ROUTE,
        trusted_public_keys=trust.keys,now=NOW,
    )
    assert result["release_authorized"] is False
    assert result["decision"]=="approve"
    assert result["authenticated_admin_oid"]==ADMIN


@pytest.mark.parametrize("field,value",[
    ("channel","microsoft_teams"),("tenant_id","00000000-0000-4000-8000-000000000000"),
    ("admin_approver_oid",REGULAR),("organization_id","other-tenant"),
    ("reviewed_policy_sha256","0"*64),("schema_version","5.0"),
])
def test_unreviewed_root_policy_change_denied(tmp_path,field,value):
    doc=info(Ed25519PrivateKey.generate());doc[field]=value
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(write(tmp_path,doc))


def test_untrusted_signing_key_cannot_be_substituted(tmp_path):
    doc=info(Ed25519PrivateKey.generate())
    doc["keys"][0]["state"]="inactive"
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(write(tmp_path,doc))


def test_duplicate_key_ids_fail_closed(tmp_path):
    doc=info(Ed25519PrivateKey.generate())
    doc["keys"].append(dict(doc["keys"][0]))
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(write(tmp_path,doc))


def test_missing_file_rejected(tmp_path):
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(tmp_path/"missing.json")


def test_unapproved_world_readable_trust_file_rejected(tmp_path):
    p=write(tmp_path,info(Ed25519PrivateKey.generate()))
    p.chmod(0o644)
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(p)


def test_symlink_trust_file_rejected(tmp_path):
    p=write(tmp_path,info(Ed25519PrivateKey.generate()))
    target=tmp_path/"linked.json"
    target.symlink_to(p)
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(target)


def test_broken_key_encoding_denied(tmp_path):
    doc=info(Ed25519PrivateKey.generate())
    doc["keys"][0]["public_key_b64"]="not a valid key!"
    with pytest.raises(BrowserReleaseRootTrustDenied):
        read(write(tmp_path,doc))
