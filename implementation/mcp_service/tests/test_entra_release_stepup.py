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
    REDIRECT, EntraStepUpDenied, ReleaseIdentityRoute, ExactRelease,
    new_login, login_authorization_url, regular_teams_notice,
    verified_admin_signin,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
ADMIN = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
REGULAR = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
CLIENT = "267b5641-cea0-4251-95c5-685178e0e087"
ROUTE = ReleaseIdentityRoute(TENANT, REGULAR, ADMIN)
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
    assert note["view_url"].startswith("https://mcp-jason.teamaot.com/admin/release-approval?")
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
