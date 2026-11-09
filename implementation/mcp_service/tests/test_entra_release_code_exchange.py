"""Entra browser admin OAuth token exchange: no release writes."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs
import json
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from jason_mcp.entra_release_stepup import (
    ReleaseIdentityRoute, ExactRelease, new_login, EntraStepUpDenied,
)
from jason_mcp.entra_release_code_exchange import redeem_admin_browser_code


NOW=datetime.now(timezone.utc).replace(microsecond=0)
TENANT="11111111-1111-4111-8111-111111111111"
ADMIN="22222222-2222-4222-8222-222222222222"
REGULAR="33333333-3333-4333-8333-333333333333"
CLIENT="44444444-4444-4444-8444-444444444444"
REDIRECT="https://approval.example.org/admin/release-approval/callback"
ROUTE=ReleaseIdentityRoute(
    tenant_id=TENANT,regular_teams_oid=REGULAR,admin_approver_oid=ADMIN,
    owner_subject_id="owner-fixture",
    registered_redirect_uri=REDIRECT,
    notice_uri="https://approval.example.org/admin/release-approval",
)
APPROVAL=ExactRelease(
    approval_id="relapproval-"+"a"*32,
    candidate_sha="b"*40, rollback_sha="c"*40,
    scope_sha256="d"*64, manifest_sha256="e"*64,
    expires_at=NOW+timedelta(minutes=12),
)
SECRET="synthetic-never-use-in-production-test-secret"
CODE="synthetic-code-for-testing-not-a-real-auth-code-123"


@pytest.fixture
def exchange():
    login=new_login(APPROVAL,now=NOW)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def signed_token(**kwargs):
        claims={
            "iss":f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud":CLIENT,"tid":TENANT,"oid":ADMIN,"nonce":login.nonce,
            "iat":int(NOW.timestamp()),"nbf":int(NOW.timestamp())-3,
            "exp":int((NOW+timedelta(minutes=9)).timestamp()),
            "auth_time":int((NOW-timedelta(seconds=10)).timestamp()),
            "acrs":["c1"],
        }
        claims.update(kwargs)
        return jwt.encode(claims,key,algorithm="RS256",headers={"kid":"test"})
    class KeyClient:
        def get_signing_key_from_jwt(self,token):return SimpleNamespace(key=key.public_key())
    class MockResponse:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,length):return self.data[:length]
    calls=[]
    def request_open(request,timeout):
        calls.append((request,timeout))
        return MockResponse(json.dumps({"id_token":signed_token(),
            "access_token":"never-log-or-return",
            "refresh_token":"never-log-or-return"}).encode())
    def redeem(**kwargs):
        args=dict(
            code=CODE,login=login,returned_state=login.state,
            approval=APPROVAL,route=ROUTE,
            app_client_id=CLIENT,client_secret=SECRET,
            required_auth_context="c1",now=NOW+timedelta(seconds=8),
            jwk_client=KeyClient(),request_open=request_open,
        )
        args.update(kwargs)
        return redeem_admin_browser_code(**args)
    return SimpleNamespace(redeem=redeem,calls=calls,login=login,
        signed_token=signed_token,key_client=KeyClient())


def test_code_exchange_is_tenant_scoped_pkce_and_never_approves(exchange):
    proof=exchange.redeem()
    assert proof["authenticated_admin_oid"]==ADMIN
    assert proof["release_authorized"] is False
    assert "access_token" not in proof and "refresh_token" not in proof
    assert "id_token" not in proof and "code_verifier" not in proof
    assert len(exchange.calls)==1
    request,timeout=exchange.calls[0]
    assert timeout==10 and request.get_method()=="POST"
    assert request.full_url==f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    body=parse_qs(request.data.decode())
    assert body["redirect_uri"]==[REDIRECT]
    assert body["code_verifier"]==[exchange.login.code_verifier]
    assert body["scope"]==["openid profile"]
    assert body["grant_type"]==["authorization_code"]
    assert body["client_id"]==[CLIENT]


@pytest.mark.parametrize("kwargs",[
    {"code":"x"},
    {"code":"a code with spaces that is invalid"},
    {"client_secret":"short"},
    {"returned_state":"not-the-exact-state"},
    {"required_auth_context":""},
    {"app_client_id":"not-a-guid"},
])
def test_bad_code_state_or_policy_fails_before_provider_call(exchange,kwargs):
    args={
        "code":CODE,"login":exchange.login,"returned_state":exchange.login.state,
        "approval":APPROVAL,"route":ROUTE,
        "app_client_id":CLIENT,"client_secret":SECRET,
        "required_auth_context":"c1","now":NOW+timedelta(seconds=8),
        "jwk_client":exchange.key_client,
        "request_open":lambda *_a,**_kw:pytest.fail("no token call expected"),
    }
    args.update(kwargs)
    with pytest.raises(EntraStepUpDenied):
        redeem_admin_browser_code(**args)


def test_token_exchange_failure_does_not_log_secret_or_claim_success(exchange):
    from urllib.error import HTTPError
    def fail(req,timeout):
        raise HTTPError(req.full_url,400,"Invalid code",None,None)
    with pytest.raises(EntraStepUpDenied,match="TOKEN_EXCHANGE_FAILED") as caught:
        exchange.redeem(request_open=fail)
    assert SECRET not in str(caught.value)
    assert CODE not in str(caught.value)


def test_token_missing_cannot_be_accepted(exchange):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,n):return b'{"access_token":"has-no-id-token"}'
    with pytest.raises(EntraStepUpDenied,match="ID_TOKEN_UNAVAILABLE"):
        exchange.redeem(request_open=lambda *_a,**_kw:Response())


def test_signed_regular_identity_cannot_assert_admin_when_redeemed(exchange):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,n):
            return json.dumps({"id_token":exchange.signed_token(oid=REGULAR)}).encode()
    with pytest.raises(EntraStepUpDenied,match="PRIVILEGED_ADMIN_SESSION"):
        exchange.redeem(request_open=lambda *_a,**_kw:Response())


def test_expired_exact_release_fails_before_code_exchange(exchange):
    expired=ExactRelease(
        approval_id=APPROVAL.approval_id,
        candidate_sha=APPROVAL.candidate_sha,
        rollback_sha=APPROVAL.rollback_sha,
        scope_sha256=APPROVAL.scope_sha256,
        manifest_sha256=APPROVAL.manifest_sha256,
        expires_at=NOW+timedelta(seconds=5),
    )
    with pytest.raises(EntraStepUpDenied,match="SESSION_OR_POLICY"):
        exchange.redeem(
            approval=expired,
            request_open=lambda *_a,**_kw:pytest.fail("provider must not be called"),
        )
