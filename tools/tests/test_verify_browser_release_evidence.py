"""Host-side read-only V5 signed decision boundary."""
from base64 import b64encode
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import pytest

from connectors.src.jason_connectors.approval_requests import ApprovalRequest, ApprovalRequestStatus
from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute
from jason_mcp.entra_release_browser_decision import create_browser_decision_envelope
from tools.verify_browser_release_evidence import (
    V5BrowserHostAttestationDenied, verify_pending_v5_admin_browser_decision,
)

NOW=datetime.now(timezone.utc).replace(microsecond=0)
TENANT="11111111-1111-4111-8111-111111111111"
REGULAR="22222222-2222-4222-8222-222222222222"
ADMIN="33333333-3333-4333-8333-333333333333"
OWNER="owner-fixture-01"
POLICY="a"*64
RELEASE=ExactRelease(
    approval_id="relapproval-"+"b"*32,candidate_sha="c"*40,rollback_sha="d"*40,
    scope_sha256="e"*64,manifest_sha256="f"*64,
    expires_at=NOW+timedelta(minutes=10),
)
ROUTE=ReleaseIdentityRoute(
    tenant_id=TENANT,regular_teams_oid=REGULAR,admin_approver_oid=ADMIN,
    owner_subject_id=OWNER,
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def environment(tmp_path):
    key=Ed25519PrivateKey.generate()
    trust=tmp_path/"root-reviewed.json"
    trust.write_text(json.dumps({
        "schema_version":"1.0","channel":"entra_browser_admin",
        "tenant_id":TENANT,"admin_approver_oid":ADMIN,
        "organization_id":"synthetic-org",
        "reviewed_policy_sha256":POLICY,
        "keys":[{
            "key_id":"reviewed-admin-signing-key","state":"active",
            "public_key_b64":b64encode(key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )).decode("ascii"),
        }],
    }))
    trust.chmod(0o600)
    login={
        "authenticated_admin_oid":ADMIN,"tenant_id":TENANT,
        "owner_subject_id":OWNER,"approval_id":RELEASE.approval_id,
        "channel":"microsoft_entra_browser_stepup",
        "candidate_sha":RELEASE.candidate_sha,
        "rollback_sha":RELEASE.rollback_sha,
        "scope_sha256":RELEASE.scope_sha256,
        "manifest_sha256":RELEASE.manifest_sha256,
        "auth_time":int(NOW.timestamp())-45,
        "evidence_sha256":"0"*64,"release_authorized":False,
    }
    signed=create_browser_decision_envelope(
        approval=RELEASE,route=ROUTE,verified_login_proof=login,
        decision="approve",signing_key=key,
        key_id="reviewed-admin-signing-key",now=NOW,
    )
    request=ApprovalRequest(
        approval_id=RELEASE.approval_id,
        request_id="request-fixture-01",
        correlation_id="correlation-fixture-01",
        organization_id="synthetic-org",
        client_id=None,
        requested_by="svc-jason-release-manager",
        capability="release.production.approve",
        requested_mode="release:"+RELEASE.candidate_sha,
        requested_at=NOW-timedelta(minutes=1),
        expires_at=RELEASE.expires_at,
        authorized_approver_ids=(OWNER,),
        metadata={
            "candidate_sha":RELEASE.candidate_sha,
            "rollback_sha":RELEASE.rollback_sha,
            "scope_sha256":RELEASE.scope_sha256,
            "manifest_sha256":RELEASE.manifest_sha256,
            "owner_policy_sha256":POLICY,
            "browser_approval_channel":"entra_browser_admin",
        },
    )
    args=dict(
        request=request,envelope=signed,exact_release=RELEASE,
        route=ROUTE,policy_version="5.0",policy_sha256=POLICY,
        organization_id="synthetic-org",
        owner_identity_ids=(OWNER,),root_trust_path=trust,now=NOW,
    )
    return args


def test_host_verified_source_alone_never_grants_release(tmp_path):
    args=environment(tmp_path)
    attested=verify_pending_v5_admin_browser_decision(**args)
    assert attested["status"]=="cryptographic_evidence_only"
    assert attested["release_authorized"] is False
    assert attested["decision"]=="approve"
    assert attested["authenticated_admin_oid"]==ADMIN


@pytest.mark.parametrize("field,value",[
    ("policy_version","4.0"),
    ("policy_sha256","f"*64),
    ("organization_id","other-organization"),
    ("owner_identity_ids",("other-owner",)),
    ("now",NOW+timedelta(minutes=11)),
])
def test_host_policy_or_ttl_changed_fails_closed(tmp_path,field,value):
    args=environment(tmp_path);args[field]=value
    with pytest.raises(PermissionError):
        verify_pending_v5_admin_browser_decision(**args)


@pytest.mark.parametrize("field,value",[
    ("candidate_sha","0"*40),
    ("rollback_sha","0"*40),
    ("scope_sha256","0"*64),
    ("manifest_sha256","0"*64),
    ("owner_policy_sha256","0"*64),
    ("browser_approval_channel","microsoft_teams"),
])
def test_request_metadata_mutations_fail_closed(tmp_path,field,value):
    args=environment(tmp_path)
    m=dict(args["request"].metadata);m[field]=value
    args["request"]=replace(args["request"],metadata=m)
    with pytest.raises(PermissionError):
        verify_pending_v5_admin_browser_decision(**args)


@pytest.mark.parametrize("field,value",[
    ("requested_by","untrusted-requester"),
    ("capability","service.ticket.update"),
    ("client_id","client1"),
    ("organization_id","other-org"),
    ("authorized_approver_ids",("normal-teams-oid",)),
    ("status",ApprovalRequestStatus.APPROVED),
])
def test_existing_request_owner_authority_unchanged(tmp_path,field,value):
    args=environment(tmp_path)
    args["request"]=replace(args["request"],**{field:value})
    with pytest.raises(PermissionError):
        verify_pending_v5_admin_browser_decision(**args)


def test_signed_admin_decision_not_swappable_between_releases(tmp_path):
    args=environment(tmp_path)
    args["exact_release"]=replace(RELEASE,rollback_sha="0"*40)
    with pytest.raises(PermissionError):
        verify_pending_v5_admin_browser_decision(**args)


def test_host_no_approval_write_even_with_valid_signature(tmp_path):
    args=environment(tmp_path)
    before=args["request"]
    result=verify_pending_v5_admin_browser_decision(**args)
    assert args["request"] is before
    assert before.status == ApprovalRequestStatus.PENDING
    assert result["release_authorized"] is False
