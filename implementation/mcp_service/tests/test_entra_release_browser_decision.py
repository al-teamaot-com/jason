"""Independent host-verifiable V5 browser decision protocol security tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from copy import deepcopy

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from jason_mcp.entra_release_stepup import ExactRelease, EntraStepUpDenied, ReleaseIdentityRoute
from jason_mcp.entra_release_browser_decision import (
    create_browser_decision_envelope, verify_browser_decision_envelope,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
APPROVAL = ExactRelease(
    approval_id="relapproval-"+"a"*32,
    candidate_sha="b"*40, rollback_sha="c"*40,
    scope_sha256="d"*64, manifest_sha256="e"*64,
    expires_at=NOW+timedelta(minutes=10),
)
ROUTE = ReleaseIdentityRoute(
    tenant_id="11111111-1111-4111-8111-111111111111",
    regular_teams_oid="22222222-2222-4222-8222-222222222222",
    admin_approver_oid="33333333-3333-4333-8333-333333333333",
    owner_subject_id="owner-fixture-01",
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def proof():
    return {
        "authenticated_admin_oid": ROUTE.admin_approver_oid,
        "tenant_id": ROUTE.tenant_id,
        "owner_subject_id": ROUTE.owner_subject_id,
        "approval_id": APPROVAL.approval_id,
        "channel": "microsoft_entra_browser_stepup",
        "candidate_sha": APPROVAL.candidate_sha,
        "scope_sha256": APPROVAL.scope_sha256,
        "rollback_sha": APPROVAL.rollback_sha,
        "manifest_sha256": APPROVAL.manifest_sha256,
        "auth_time": int(NOW.timestamp())-40,
        "evidence_sha256": "f"*64,
        "release_authorized": False,
    }


def signed():
    key=Ed25519PrivateKey.generate()
    env=create_browser_decision_envelope(
        approval=APPROVAL, route=ROUTE, verified_login_proof=proof(),
        decision="approve", signing_key=key, key_id="release-admin-v5",
        now=NOW,
    )
    return key, env


def checked(key, env, *, approval=APPROVAL, route=ROUTE, now=NOW):
    return verify_browser_decision_envelope(
        env, approval=approval, route=route,
        trusted_public_keys={"release-admin-v5":key.public_key()},
        now=now,
    )


def test_valid_admin_cryptographic_decision_is_only_source_evidence():
    key, env=signed()
    proof_receipt=checked(key,env)
    assert proof_receipt["verification"]=="signature_and_exact_subject_verified"
    assert proof_receipt["release_authorized"] is False
    assert proof_receipt["decision"]=="approve"
    assert proof_receipt["authenticated_admin_oid"]==ROUTE.admin_approver_oid
    assert "private_key" not in str(env)
    assert "id_token" not in str(env)


@pytest.mark.parametrize("field,value",[
    ("decision","deny"),
    ("candidate_sha","a"*40),
    ("rollback_sha","a"*40),
    ("scope_sha256","a"*64),
    ("manifest_sha256","a"*64),
    ("approval_id","relapproval-"+"b"*32),
    ("tenant_id","00000000-0000-4000-8000-000000000000"),
    ("authenticated_admin_oid","22222222-2222-4222-8222-222222222222"),
    ("owner_subject_id","attacker"),
    ("channel","microsoft_teams"),
    ("release_fingerprint","f"*64),
    ("auth_time",0),
])
def test_any_tampered_field_invalidates_signature(field,value):
    key,env=signed()
    bad=deepcopy(env);bad["payload"][field]=value
    with pytest.raises(EntraStepUpDenied):
        checked(key,bad)


def test_wrong_public_key_fails():
    _,env=signed()
    with pytest.raises(EntraStepUpDenied,match="SIGNATURE"):
        checked(Ed25519PrivateKey.generate(),env)


def test_untrusted_signing_key_id_fails():
    key,env=signed();env["key_id"]="unreviewed-key-01"
    with pytest.raises(EntraStepUpDenied,match="KEY_NOT_TRUSTED"):
        checked(key,env)


@pytest.mark.parametrize("changed",[
    {"candidate_sha":"a"*40},
    {"rollback_sha":"a"*40},
    {"scope_sha256":"a"*64},
    {"manifest_sha256":"a"*64},
    {"approval_id":"relapproval-"+"b"*32},
])
def test_changed_authoritative_release_not_authorized(changed):
    key,env=signed()
    with pytest.raises(EntraStepUpDenied,match="SCOPE_OR_IDENTITY"):
        checked(key,env,approval=replace(APPROVAL,**changed))


def test_normal_teams_identity_can_never_sign_admin_proof():
    fake=proof();fake["authenticated_admin_oid"]=ROUTE.regular_teams_oid
    with pytest.raises(EntraStepUpDenied,match="IDENTITY_OR_RELEASE"):
        create_browser_decision_envelope(
            approval=APPROVAL,route=ROUTE,
            verified_login_proof=fake,decision="approve",
            signing_key=Ed25519PrivateKey.generate(),
            key_id="release-admin-v5",now=NOW,
        )


@pytest.mark.parametrize("changed",[
    {"release_authorized":True},
    {"auth_time":int(NOW.timestamp())-3600},
    {"auth_time":"recent"},
    {"channel":"microsoft_teams"},
    {"evidence_sha256":"f"*32},
])
def test_unverified_or_stale_login_cannot_issue_signature(changed):
    fake=proof();fake.update(changed)
    with pytest.raises(EntraStepUpDenied):
        create_browser_decision_envelope(
            approval=APPROVAL,route=ROUTE,
            verified_login_proof=fake,decision="approve",
            signing_key=Ed25519PrivateKey.generate(),
            key_id="release-admin-v5",now=NOW,
        )


def test_expired_or_future_decisions_fail_host_verifier():
    key,env=signed()
    with pytest.raises(EntraStepUpDenied,match="NOT_FRESH"):
        checked(key,env,now=NOW+timedelta(seconds=301))
    with pytest.raises(EntraStepUpDenied,match="NOT_FRESH"):
        checked(key,env,now=NOW-timedelta(seconds=1))


def test_signing_denial_is_not_silent_approval():
    key=Ed25519PrivateKey.generate()
    env=create_browser_decision_envelope(
        approval=APPROVAL,route=ROUTE,verified_login_proof=proof(),
        decision="deny",signing_key=key,key_id="release-admin-v5",now=NOW,
    )
    res=checked(key,env)
    assert res["decision"]=="deny"
    assert res["release_authorized"] is False


def test_schema_addition_and_wrong_signature_format_fail_closed():
    key,env=signed()
    env["extra_authority"]="release_now"
    with pytest.raises(EntraStepUpDenied,match="SCHEMA"):
        checked(key,env)
    key,env=signed()
    env["signature"]="not-a-real-signature"
    with pytest.raises(EntraStepUpDenied,match="SIGNATURE"):
        checked(key,env)
