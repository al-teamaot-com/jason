"""ASGI-only acceptance for non-activated browser OAuth adapter."""
from datetime import datetime, timedelta, timezone
import asyncio
import functools
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from starlette.requests import Request

from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute, EntraStepUpDenied
from jason_mcp.entra_release_browser_sessions import OneTimeBrowserLoginStore
from jason_mcp.entra_release_browser_http import AdminReleaseBrowserAdapter

TENANT = "11111111-1111-4111-8111-111111111111"
REGULAR = "22222222-2222-4222-8222-222222222222"
ADMIN = "33333333-3333-4333-8333-333333333333"
CLIENT = "44444444-4444-4444-8444-444444444444"
NOW = datetime.now(timezone.utc)
RELEASE = ExactRelease(
    approval_id="relapproval-"+"a"*32,
    candidate_sha="b"*40, rollback_sha="c"*40,
    scope_sha256="d"*64, manifest_sha256="e"*64,
    expires_at=NOW+timedelta(minutes=10),
)
ROUTE = ReleaseIdentityRoute(
    tenant_id=TENANT, regular_teams_oid=REGULAR, admin_approver_oid=ADMIN,
    owner_subject_id="owner-fixture-01",
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def harness(tmp_path, *, ca=True, resolver=None, sink=None):
    store = OneTimeBrowserLoginStore(tmp_path/"browser.db")
    sink = sink if sink is not None else []
    a = AdminReleaseBrowserAdapter(
        route=ROUTE, client_id=CLIENT,
        load_exact_release=resolver or (lambda rid: RELEASE),
        login_store=store, credential_loader=lambda:"synthetic-client-secret-at-least-16",
        verify_ca_enforcement=lambda:ca, required_auth_context="c1",
        proof_sink=sink.append,
    )
    return a, store, sink


async def call(adapter, method, path, **kwargs):
    """Exercise Starlette Request without HTTPX or live network."""
    parsed = urlsplit(path)
    headers = [(b"host", b"approval.example.org")]
    for k,v in (kwargs.get("headers") or {}).items():
        headers.append((k.lower().encode("ascii"),v.encode("ascii")))
    cookies = kwargs.get("cookies") or {}
    if cookies:
        headers.append((b"cookie", "; ".join(k+"="+v for k,v in cookies.items()).encode("ascii")))
    body = kwargs.get("content", "")
    if isinstance(body,str):
        body=body.encode("ascii")
    scope={"type":"http","http_version":"1.1","method":method,
        "path":parsed.path,"raw_path":parsed.path.encode("ascii"),
        "query_string":parsed.query.encode("ascii"),"scheme":"https",
        "server":("approval.example.org",443),"client":("127.0.0.1",50000),
        "headers":headers}
    async def receive():
        return {"type":"http.request","body":body,"more_body":False}
    req=Request(scope,receive)
    if parsed.path.endswith("/callback"):
        return await adapter.callback(req)
    if method=="POST":
        return await adapter.begin(req)
    return await adapter.notice(req)



def run_async(func):
    @functools.wraps(func)
    def run(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return run


@run_async
async def test_notice_is_only_nonactionable_and_nostore(tmp_path):
    app,_,sink=harness(tmp_path)
    res=await call(app,"GET","/admin/release-approval?request="+RELEASE.approval_id)
    assert res.status_code==200
    assert res.headers["Cache-Control"]=="no-store"
    assert "does not approve" in res.body.decode().lower()
    assert "Action.Submit" not in res.body.decode()
    assert not sink


@run_async
async def test_missing_ca_attestation_denies_before_session(tmp_path):
    app,store,sink=harness(tmp_path,ca=False)
    url="/admin/release-approval?request="+RELEASE.approval_id
    assert (await call(app,"GET",url)).status_code==403
    res=await call(app,"POST","/admin/release-approval",
                   headers={"Origin":"https://approval.example.org",
                            "Content-Type":"application/x-www-form-urlencoded"},
                   content="request="+RELEASE.approval_id)
    assert res.status_code==403
    import sqlite3
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM browser_login_sessions").fetchone()[0]==0


@run_async
@pytest.mark.parametrize("headers,body",[
    ({"Origin":"https://untrusted.example.org","Content-Type":"application/x-www-form-urlencoded"},"request=relapproval-"+ "a"*32),
    ({"Content-Type":"application/x-www-form-urlencoded"},"request=relapproval-"+ "a"*32),
    ({"Origin":"https://approval.example.org","Content-Type":"application/json"},'{"request":"x"}'),
    ({"Origin":"https://approval.example.org","Content-Type":"application/x-www-form-urlencoded"},"request=x&request=y"),
])
async def test_csrf_content_type_and_parameter_pollution_denied(tmp_path,headers,body):
    app,_,_=harness(tmp_path)
    res=await call(app,"POST","/admin/release-approval",headers=headers,content=body)
    assert res.status_code==403


@run_async
async def test_begin_uses_confidential_azure_and_secure_cookie(tmp_path):
    app,store,_=harness(tmp_path)
    res=await call(app,"POST","/admin/release-approval",
                   headers={"Origin":"https://approval.example.org",
                            "Content-Type":"application/x-www-form-urlencoded"},
                   content="request="+RELEASE.approval_id)
    assert res.status_code==303
    assert res.headers["location"].startswith("https://login.microsoftonline.com/"+TENANT)
    params=parse_qs(urlsplit(res.headers["location"]).query)
    assert params["prompt"]==["login"]
    assert params["code_challenge_method"]==["S256"]
    assert params["redirect_uri"]==[ROUTE.registered_redirect_uri]
    assert "client_secret" not in res.headers["location"]
    cookie=res.headers["set-cookie"]
    for term in ("__Host-jason-admin-release=","HttpOnly","Secure","SameSite=lax","Path=/"):
        assert term.lower() in cookie.lower()
    assert store.lookup_release_id(cookie_value=cookie.split(";")[0].split("=",1)[1])==RELEASE.approval_id


@run_async
async def test_callback_replays_fail_and_never_issue_approval(tmp_path):
    app,store,sink=harness(tmp_path)
    begin=await call(app,"POST","/admin/release-approval",
                     headers={"Origin":"https://approval.example.org",
                              "Content-Type":"application/x-www-form-urlencoded"},
                     content="request="+RELEASE.approval_id)
    cookie=begin.headers["set-cookie"].split(";")[0].split("=",1)[1]
    state=parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    callback="/admin/release-approval/callback?code="+("x"*40)+"&state="+state
    evidence={"release_authorized":False,"authenticated_admin_oid":ADMIN}
    with patch("jason_mcp.entra_release_browser_http.redeem_admin_browser_code",
               return_value=evidence) as oauth:
        response=await call(app,"GET",callback,cookies={"__Host-jason-admin-release":cookie})
        assert response.status_code==200
        assert "No release has been approved" in response.body.decode()
        assert sink==[evidence]
        oauth.assert_called_once()
        assert oauth.call_args.kwargs["approval"]==RELEASE
        replay=await call(app,"GET",callback,cookies={"__Host-jason-admin-release":cookie})
        assert replay.status_code==403
        assert len(sink)==1


@run_async
async def test_callback_wrong_state_does_not_burn_valid_session(tmp_path):
    app,store,sink=harness(tmp_path)
    begin=await call(app,"POST","/admin/release-approval",
                     headers={"Origin":"https://approval.example.org",
                              "Content-Type":"application/x-www-form-urlencoded"},
                     content="request="+RELEASE.approval_id)
    cookie=begin.headers["set-cookie"].split(";")[0].split("=",1)[1]
    wrong=await call(app,"GET","/admin/release-approval/callback?code="+ "x"*40+"&state=bad",
                     cookies={"__Host-jason-admin-release":cookie})
    assert wrong.status_code==403
    assert store.lookup_release_id(cookie_value=cookie)==RELEASE.approval_id
    assert sink==[]


@run_async
async def test_scope_changed_between_start_and_callback_denied(tmp_path):
    original=[RELEASE]
    app,store,sink=harness(tmp_path,resolver=lambda rid:original[0])
    begin=await call(app,"POST","/admin/release-approval",
                     headers={"Origin":"https://approval.example.org",
                              "Content-Type":"application/x-www-form-urlencoded"},
                     content="request="+RELEASE.approval_id)
    cookie=begin.headers["set-cookie"].split(";")[0].split("=",1)[1]
    state=parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    from dataclasses import replace
    original[0]=replace(RELEASE,rollback_sha="f"*40)
    response=await call(app,"GET","/admin/release-approval/callback?code="+ "x"*40+"&state="+state,
                        cookies={"__Host-jason-admin-release":cookie})
    assert response.status_code==403 and sink==[]
