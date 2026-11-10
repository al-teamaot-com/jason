"""Source-only V5 dual-channel approval security invariants. No provider writes."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from jason_mcp.entra_release_stepup import (
    EntraStepUpDenied, ReleaseIdentityRoute, ExactRelease,
    new_login, login_authorization_url, regular_teams_notice,
    verified_admin_signin,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "11111111-1111-4111-8111-111111111111"
ADMIN = "22222222-2222-4222-8222-222222222222"
REGULAR = "33333333-3333-4333-8333-333333333333"
CLIENT = "44444444-4444-4444-8444-444444444444"
REDIRECT = "https://approval.example.org/admin/release-approval/callback"
NOTICE = "https://approval.example.org/admin/release-approval"
ROUTE = ReleaseIdentityRoute(
    tenant_id=TENANT,
    regular_teams_oid=REGULAR,
    admin_approver_oid=ADMIN,
    owner_subject_id="owner-fixture",
    registered_redirect_uri=REDIRECT,
    notice_uri=NOTICE,
)
APPROVAL = ExactRelease(
    approval_id="relapproval-" + "a" * 32,
    candidate_sha="b" * 40,
    rollback_sha="c" * 40,
    scope_sha256="d" * 64,
    manifest_sha256="e" * 64,
    expires_at=NOW + timedelta(minutes=12),
)


class SignedKey:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=self.key.public_key())


@pytest.fixture
def fixture():
    login = new_login(APPROVAL, now=NOW)
    key = SignedKey()
    def mint(**overrides):
        claims = {
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud": CLIENT, "tid": TENANT, "oid": ADMIN,
            "nonce": login.nonce, "iat": int(NOW.timestamp()),
            "nbf": int(NOW.timestamp())-5,
            "exp": int((NOW+timedelta(minutes=10)).timestamp()),
            "auth_time": int((NOW-timedelta(seconds=30)).timestamp()),
            "acrs": ["c1"],
        }
        claims.update(overrides)
        return jwt.encode(claims, key.key, algorithm="RS256", headers={"kid":"test-key"})
    def verify(token=None, **kwargs):
        return verified_admin_signin(
            id_token=token or mint(),
            login=login, returned_state=login.state,
            approval=APPROVAL, route=ROUTE, app_client_id=CLIENT,
            required_auth_context="c1", now=NOW+timedelta(seconds=20),
            jwk_client=key, **kwargs,
        )
    return SimpleNamespace(login=login, mint=mint, verify=verify, key=key)


def test_teams_notice_is_nonactionable_and_only_regular_receiver():
    note = regular_teams_notice(route=ROUTE, approval=APPROVAL)
    assert note["recipient_entra_oid"] == REGULAR
    assert note["recipient_entra_oid"] != ADMIN
    assert note["kind"] == "notification"
    assert note["can_approve_from_teams"] is False
    assert note["card"] is None
    assert note["view_url"].startswith("https://approval.example.org/admin/release-approval?")
    assert "candidate_sha" not in note["view_url"]
    assert "nonce" not in note["view_url"]
    assert "approval" in note["view_url"]


def test_admin_signin_pkce_tenant_scoped_not_admin_teams(fixture):
    url=login_authorization_url(
        route=ROUTE, login=fixture.login,
        client_id=CLIENT, redirect_uri=REDIRECT,
        required_auth_context="c1",
    )
    u=urlsplit(url);params=parse_qs(u.query)
    assert u.hostname == "login.microsoftonline.com"
    assert f"/{TENANT}/" in u.path
    assert params["scope"] == ["openid profile"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["prompt"] == ["login"]
    assert params["max_age"] == ["300"]
    import json
    assert json.loads(params["claims"][0]) == {
        "id_token": {"acrs": {"essential": True, "value": "c1"}},
    }
    assert params["state"] == [fixture.login.state]
    assert params["nonce"] == [fixture.login.nonce]
    assert "code_verifier" not in params
    assert ADMIN not in url and REGULAR not in url


def test_existing_admin_role_mfa_pkce_requires_signed_recent_mfa(fixture):
    url=login_authorization_url(
        route=ROUTE,login=fixture.login,client_id=CLIENT,
        redirect_uri=REDIRECT,required_auth_context=None,
    )
    import json
    claims=json.loads(parse_qs(urlsplit(url).query)["claims"][0])
    assert claims=={"id_token":{
        "amr":{"essential":True},"auth_time":{"essential":True},
    }}
    def authenticate(token):
        return verified_admin_signin(
            id_token=token,login=fixture.login,returned_state=fixture.login.state,
            approval=APPROVAL,route=ROUTE,app_client_id=CLIENT,
            required_auth_context=None,now=NOW+timedelta(seconds=20),
            jwk_client=fixture.key,
        )
    proof=authenticate(fixture.mint(amr=["pwd","mfa"],acrs=[]))
    assert proof["authenticated_admin_oid"]==ADMIN
    assert proof["release_authorized"] is False
    for methods in ([],["pwd"],["otp"],"mfa",None):
        with pytest.raises(EntraStepUpDenied,match="PRIVILEGED_ADMIN_SESSION"):
            authenticate(fixture.mint(amr=methods,acrs=[]))
    with pytest.raises(EntraStepUpDenied,match="PRIVILEGED_ADMIN_SESSION"):
        authenticate(fixture.mint(amr=["mfa"],
                    auth_time=int((NOW-timedelta(hours=1)).timestamp())))


def test_verified_admin_token_is_only_identity_evidence_not_release_authority(fixture):
    proof=fixture.verify()
    assert proof["authenticated_admin_oid"] == ADMIN
    assert proof["channel"] == "microsoft_entra_browser_stepup"
    assert proof["release_authorized"] is False
    assert proof["candidate_sha"] == APPROVAL.candidate_sha
    assert proof["scope_sha256"] == APPROVAL.scope_sha256
    assert proof["rollback_sha"] == APPROVAL.rollback_sha
    assert len(proof["evidence_sha256"]) == 64


@pytest.mark.parametrize("alterations", [
    {"oid": REGULAR},
    {"oid": "a"*36},
    {"tid": "00000000-0000-0000-0000-000000000001"},
    {"aud": "00000000-0000-0000-0000-000000000001"},
    {"iss": "https://login.microsoftonline.com/common/v2.0"},
    {"nonce": "attacker-nonce"},
    {"acrs": ["c2"]},
    {"auth_time": int((NOW-timedelta(hours=1)).timestamp())},
    {"auth_time": int((NOW+timedelta(minutes=10)).timestamp())},
    {"auth_time": "recent"},
    {"exp": int((NOW-timedelta(minutes=1)).timestamp())},
])
def test_invalid_admin_token_fails_closed(fixture,alterations):
    with pytest.raises(EntraStepUpDenied):
        fixture.verify(token=fixture.mint(**alterations))


def test_mfa_conditional_access_auth_context_is_required(fixture):
    with pytest.raises(EntraStepUpDenied, match="STEP_UP_POLICY_MISSING"):
        verified_admin_signin(
            id_token=fixture.mint(), login=fixture.login,
            returned_state=fixture.login.state,
            approval=APPROVAL, route=ROUTE, app_client_id=CLIENT,
            required_auth_context="", now=NOW, jwk_client=fixture.key,
        )


def test_expired_or_cross_approval_session_fails_closed(fixture):
    for altered in (
        replace(fixture.login, approval_id="relapproval-"+"f"*32),
        replace(fixture.login, exact_release_fingerprint="f"*64),
        replace(fixture.login, started_at=NOW-timedelta(minutes=10)),
    ):
        with pytest.raises(EntraStepUpDenied, match="SESSION_OR_STATE"):
            verified_admin_signin(
                id_token=fixture.mint(), login=altered,
                returned_state=altered.state,
                approval=APPROVAL, route=ROUTE, app_client_id=CLIENT,
                required_auth_context="c1", now=NOW+timedelta(seconds=20),
                jwk_client=fixture.key,
            )
    with pytest.raises(EntraStepUpDenied, match="SESSION_OR_STATE"):
        verified_admin_signin(
            id_token=fixture.mint(), login=fixture.login,
            returned_state="wrong-state",
            approval=APPROVAL, route=ROUTE, app_client_id=CLIENT,
            required_auth_context="c1", now=NOW+timedelta(seconds=20),
            jwk_client=fixture.key,
        )


def test_expired_release_never_accepted(fixture):
    with pytest.raises(EntraStepUpDenied, match="SESSION_OR_STATE"):
        verified_admin_signin(
            id_token=fixture.mint(), login=fixture.login,
            returned_state=fixture.login.state,
            approval=APPROVAL, route=ROUTE, app_client_id=CLIENT,
            required_auth_context="c1",
            now=APPROVAL.expires_at,
            jwk_client=fixture.key,
        )


def test_regular_user_can_never_be_the_admin_signer(fixture):
    with pytest.raises(EntraStepUpDenied, match="SEPARATE_ENTRA_ADMIN_REQUIRED"):
        regular_teams_notice(
            route=replace(ROUTE, admin_approver_oid=REGULAR),
            approval=APPROVAL,
        )
    with pytest.raises(EntraStepUpDenied, match="REVIEWED_ENTRA_APP_REDIRECT_REQUIRED"):
        login_authorization_url(
            route=ROUTE, login=fixture.login, client_id=CLIENT,
            redirect_uri="https://attacker.example/steal-token",
            required_auth_context="c1",
        )


def test_wrong_signature_or_algorithm_cannot_assert_admin_identity(fixture):
    foreign=SignedKey()
    payload={
        "iss":f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud":CLIENT,"tid":TENANT,"oid":ADMIN,"nonce":fixture.login.nonce,
        "iat":int(NOW.timestamp()),"nbf":int(NOW.timestamp())-5,
        "exp":int((NOW+timedelta(minutes=10)).timestamp()),
        "auth_time":int(NOW.timestamp()),"acrs":["c1"],
    }
    tampered=jwt.encode(payload,foreign.key,algorithm="RS256",headers={"kid":"test-key"})
    with pytest.raises(EntraStepUpDenied,match="SIGNATURE_OR_CLAIMS_INVALID"):
        fixture.verify(token=tampered)
    unsigned=jwt.encode(payload,key="",algorithm="none")
    with pytest.raises(EntraStepUpDenied):
        fixture.verify(token=unsigned)


def test_exact_scope_cannot_be_changed_mid_browser_login(fixture):
    from jason_mcp.entra_release_stepup import EntraStepUpDenied
    altered = replace(APPROVAL, scope_sha256="f"*64)
    with pytest.raises(EntraStepUpDenied, match="SESSION_OR_STATE"):
        verified_admin_signin(
            id_token=fixture.mint(), login=fixture.login,
            returned_state=fixture.login.state,
            approval=altered, route=ROUTE, app_client_id=CLIENT,
            required_auth_context="c1", now=NOW+timedelta(seconds=20),
            jwk_client=fixture.key,
        )


def test_acrs_string_is_not_an_authenticated_mfa_context(fixture):
    with pytest.raises(EntraStepUpDenied, match="PRIVILEGED_ADMIN_SESSION"):
        fixture.verify(token=fixture.mint(acrs="c1"))


def test_owner_and_web_endpoint_are_required_policy_inputs_not_deployment_defaults():
    # A reusable source module cannot quietly default to the original owner,
    # AOT's hostname or one tenant's Entra Object IDs.
    with pytest.raises(TypeError):
        ReleaseIdentityRoute(TENANT, REGULAR, ADMIN)
    assert ROUTE.owner_subject_id == "owner-fixture"
    other = replace(ROUTE, owner_subject_id="governed-second-owner")
    assert other.validate() is None
    notice = regular_teams_notice(route=other, approval=APPROVAL)
    assert notice["recipient_entra_oid"] == REGULAR
    assert notice["view_url"].startswith(other.notice_uri + "?")

@pytest.mark.parametrize("bad_route", [
    {"notice_uri": "http://approval.example.org/admin/release-approval"},
    {"notice_uri": "https://attacker.example/admin/release-approval"},
    {"registered_redirect_uri": "https://attacker.example/admin/release-approval/callback"},
    {"registered_redirect_uri": "https://approval.example.org/admin/release-approval/callback?next=evil"},
    {"registered_redirect_uri": "https://user:pass@approval.example.org/admin/release-approval/callback"},
    {"registered_redirect_uri": "https://127.0.0.1/admin/release-approval/callback"},
    {"registered_redirect_uri": "https://localhost/admin/release-approval/callback"},
    {"notice_uri": "https://approval.example.org/admin/release-approval#fragment"},
    {"notice_uri": "https://approval.example.org:444/admin/release-approval"},
    {"owner_subject_id": ""},
    {"owner_subject_id": "al_admin@example.org"},
    {"owner_subject_id": " "},
    {"admin_approver_oid": REGULAR},
])
def test_unreviewed_approval_identity_or_redirect_is_never_accepted(bad_route):
    with pytest.raises(EntraStepUpDenied):
        regular_teams_notice(
            route=replace(ROUTE, **bad_route), approval=APPROVAL,
        )


def test_authorize_requires_redirect_matching_policy_not_an_arbitrary_call():
    with pytest.raises(EntraStepUpDenied, match="REVIEWED_ENTRA_APP_REDIRECT_REQUIRED"):
        login_authorization_url(
            route=ROUTE, login=new_login(APPROVAL, now=NOW),
            client_id=CLIENT,
            redirect_uri="https://other.example.org/admin/release-approval/callback",
            required_auth_context="c1",
        )


def test_second_tenant_and_approver_can_be_configured_without_source_change():
    different = replace(
        ROUTE,
        tenant_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        regular_teams_oid="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        admin_approver_oid="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        owner_subject_id="person-second-owner",
        registered_redirect_uri="https://jason.example.net/admin/release-approval/callback",
        notice_uri="https://jason.example.net/admin/release-approval",
    )
    assert different.validate() is None
    token_login = new_login(APPROVAL, now=NOW)
    url = login_authorization_url(
        route=different, login=token_login, client_id=CLIENT,
        redirect_uri=different.registered_redirect_uri,
        required_auth_context="c1",
    )
    assert different.tenant_id in url
    notice = regular_teams_notice(route=different, approval=APPROVAL)
    assert notice["view_url"].startswith(different.notice_uri + "?")
    assert notice["recipient_entra_oid"] == different.regular_teams_oid
