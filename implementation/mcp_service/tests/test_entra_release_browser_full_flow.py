"""Offline complete browser sign-in -> explicit choice -> signed evidence proof.

No provider calls, no release mutation, no live route mount.
"""
import asyncio
import functools
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request

from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute
from jason_mcp.entra_release_browser_http import AdminReleaseBrowserAdapter
from jason_mcp.entra_release_browser_sessions import OneTimeBrowserLoginStore
from jason_mcp.entra_release_browser_decision_sessions import OneTimeAdminDecisionStore
from jason_mcp.entra_release_browser_decision import verify_browser_decision_envelope

TENANT = "11111111-1111-4111-8111-111111111111"
REGULAR = "22222222-2222-4222-8222-222222222222"
ADMIN = "33333333-3333-4333-8333-333333333333"
CLIENT = "44444444-4444-4444-8444-444444444444"
NOW = datetime.now(timezone.utc)
RELEASE = ExactRelease(
    approval_id="relapproval-"+"a"*32,candidate_sha="b"*40,rollback_sha="c"*40,
    scope_sha256="d"*64,manifest_sha256="e"*64,expires_at=NOW+timedelta(minutes=10),
)
ROUTE = ReleaseIdentityRoute(
    tenant_id=TENANT,regular_teams_oid=REGULAR,admin_approver_oid=ADMIN,
    owner_subject_id="owner-fixture-01",
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def proof():
    return {
        "authenticated_admin_oid":ADMIN,"tenant_id":TENANT,
        "owner_subject_id":ROUTE.owner_subject_id,"approval_id":RELEASE.approval_id,
        "channel":"microsoft_entra_browser_stepup",
        "candidate_sha":RELEASE.candidate_sha,"rollback_sha":RELEASE.rollback_sha,
        "scope_sha256":RELEASE.scope_sha256,"manifest_sha256":RELEASE.manifest_sha256,
        "auth_time":int(datetime.now(timezone.utc).timestamp())-30,
        "evidence_sha256":"f"*64,"release_authorized":False,
    }


def harness(tmp_path, *, ca=True, resolver=None, signer=True, sink=True):
    key=Ed25519PrivateKey.generate()
    received=[]
    adapter=AdminReleaseBrowserAdapter(
        route=ROUTE,client_id=CLIENT,
        load_exact_release=resolver or (lambda approval_id:RELEASE),
        login_store=OneTimeBrowserLoginStore(tmp_path/"login.db"),
        credential_loader=lambda:"synthetic-client-secret-at-least-16",
        verify_ca_enforcement=lambda:ca,
        required_auth_context="c1",
        decision_store=OneTimeAdminDecisionStore(tmp_path/"decision.db"),
        signing_key_loader=(lambda:key) if signer else None,
        signing_key_id="reviewed-v5-test-key",signed_decision_sink=received.append if sink else None,
    )
    return adapter,key,received


async def request(adapter, method, url, *, body="", headers=None, cookie=None):
    split=urlsplit(url)
    headers=[(b"host",b"approval.example.org")]+[
        (k.lower().encode("ascii"),v.encode("ascii"))
        for k,v in (headers or {}).items()
    ]
    if cookie is not None:
        name,value=cookie
        headers.append((b"cookie",(name+"="+value).encode("ascii")))
    scope={
        "type":"http","http_version":"1.1","scheme":"https",
        "path":split.path,"raw_path":split.path.encode("ascii"),
        "method":method,"query_string":split.query.encode("ascii"),
        "headers":headers,"server":("approval.example.org",443),
        "client":("127.0.0.1",53000),
    }
    async def receive():
        return {"type":"http.request","body":body.encode("ascii"),"more_body":False}
    req=Request(scope,receive)
    if split.path.endswith("/callback"):
        return await adapter.callback(req)
    if split.path.endswith("/decision"):
        return await (adapter.decision_submit(req) if method=="POST" else adapter.decision_page(req))
    if method=="POST":
        return await adapter.begin(req)
    return await adapter.notice(req)


def run_async(fn):
    @functools.wraps(fn)
    def wrapper(*args,**kwargs):
        return asyncio.run(fn(*args,**kwargs))
    return wrapper


def cookie_value(response, name):
    match=re.search(re.escape(name)+r"=([^;]+)",response.headers["set-cookie"])
    assert match is not None
    return match.group(1)


async def sign_in(adapter, *, proof_override=None):
    begin=await request(
        adapter,"POST","/admin/release-approval",
        body="request="+RELEASE.approval_id,
        headers={"Origin":"https://approval.example.org",
                 "Content-Type":"application/x-www-form-urlencoded"},
    )
    assert begin.status_code==303
    session=cookie_value(begin,"__Host-jason-admin-release")
    state=parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    with patch("jason_mcp.entra_release_browser_http.redeem_admin_browser_code",
               return_value=proof_override if proof_override is not None else proof()):
        callback=await request(
            adapter,"GET","/admin/release-approval/callback?code="+("x"*40)+"&state="+state,
            cookie=("__Host-jason-admin-release",session),
        )
    return callback


async def consent(adapter, decision_cookie):
    page=await request(
        adapter,"GET","/admin/release-approval/decision",
        cookie=("__Host-jason-admin-decision",decision_cookie),
    )
    assert page.status_code==200
    match=re.search(r"name='csrf' type='hidden' value='([^']+)'",page.body.decode())
    assert match is not None
    return match.group(1)


async def choose(adapter, decision_cookie, csrf, choice="approve", **kwargs):
    return await request(
        adapter,"POST","/admin/release-approval/decision",
        body="csrf="+csrf+"&decision="+choice,
        cookie=("__Host-jason-admin-decision",decision_cookie),
        headers=kwargs.get("headers") or {
            "Origin":"https://approval.example.org",
            "Content-Type":"application/x-www-form-urlencoded",
        },
    )


@run_async
async def test_signed_choice_requires_two_distinct_browser_interactions(tmp_path):
    adapter,key,received=harness(tmp_path)
    callback=await sign_in(adapter)
    assert callback.status_code==303
    assert callback.headers["location"]==ROUTE.notice_uri+"/decision"
    decision_cookie=cookie_value(callback,"__Host-jason-admin-decision")
    assert "HttpOnly" in callback.headers["set-cookie"]
    csrf=await consent(adapter,decision_cookie)
    assert not received
    response=await choose(adapter,decision_cookie,csrf)
    assert response.status_code==200
    assert "No release has been deployed" in response.body.decode()
    assert len(received)==1
    validated=verify_browser_decision_envelope(
        received[0],approval=RELEASE,route=ROUTE,
        trusted_public_keys={"reviewed-v5-test-key":key.public_key()},
        now=datetime.now(timezone.utc),
    )
    assert validated["decision"]=="approve"
    assert validated["release_authorized"] is False
    replay=await choose(adapter,decision_cookie,csrf)
    assert replay.status_code==403 and len(received)==1


@run_async
async def test_explicit_deny_signed_but_never_grants_release(tmp_path):
    adapter,key,received=harness(tmp_path)
    callback=await sign_in(adapter)
    decision_cookie=cookie_value(callback,"__Host-jason-admin-decision")
    csrf=await consent(adapter,decision_cookie)
    response=await choose(adapter,decision_cookie,csrf,"deny")
    assert response.status_code==200
    check=verify_browser_decision_envelope(
        received[0],approval=RELEASE,route=ROUTE,
        trusted_public_keys={"reviewed-v5-test-key":key.public_key()},
        now=datetime.now(timezone.utc),
    )
    assert check["decision"]=="deny" and check["release_authorized"] is False


@run_async
async def test_wrong_admin_id_prevents_decision_session(tmp_path):
    adapter,key,received=harness(tmp_path)
    wrong=proof();wrong["authenticated_admin_oid"]=REGULAR
    callback=await sign_in(adapter,proof_override=wrong)
    assert callback.status_code==403
    assert not received


@pytest.mark.parametrize("missing",["signer","sink"])
@run_async
async def test_missing_signer_or_sink_refuses_without_consuming(tmp_path,missing):
    adapter,key,received=harness(tmp_path,signer=missing!="signer",sink=missing!="sink")
    callback=await sign_in(adapter)
    cookie=cookie_value(callback,"__Host-jason-admin-decision")
    csrf=await consent(adapter,cookie)
    response=await choose(adapter,cookie,csrf)
    assert response.status_code==403
    assert await consent(adapter,cookie)==csrf
    assert not received


@run_async
async def test_wrong_csrf_or_wrong_origin_does_not_consume_decision(tmp_path):
    adapter,key,received=harness(tmp_path)
    callback=await sign_in(adapter)
    cookie=cookie_value(callback,"__Host-jason-admin-decision")
    csrf=await consent(adapter,cookie)
    assert (await choose(adapter,cookie,"x"*43)).status_code==403
    assert (await choose(adapter,cookie,csrf,headers={
        "Origin":"https://evil.example.org","Content-Type":"application/x-www-form-urlencoded",
    })).status_code==403
    assert await consent(adapter,cookie)==csrf
    assert not received


@run_async
async def test_signed_decision_scope_change_denied(tmp_path):
    from dataclasses import replace
    current=[RELEASE]
    adapter,key,received=harness(tmp_path,resolver=lambda rid:current[0])
    callback=await sign_in(adapter)
    cookie=cookie_value(callback,"__Host-jason-admin-decision")
    csrf=await consent(adapter,cookie)
    current[0]=replace(RELEASE,scope_sha256="0"*64)
    response=await choose(adapter,cookie,csrf)
    assert response.status_code==403
    assert not received


@run_async
async def test_ca_revoked_before_explicit_submit_refuses(tmp_path):
    active=[True]
    adapter,key,received=harness(tmp_path)
    adapter.verify_ca_enforcement=lambda:active[0]
    callback=await sign_in(adapter)
    cookie=cookie_value(callback,"__Host-jason-admin-decision")
    csrf=await consent(adapter,cookie)
    active[0]=False
    response=await choose(adapter,cookie,csrf)
    assert response.status_code==403
    assert not received
