"""Offline HTTPS browser -> admin Entra -> one existing signed release receipt."""
from __future__ import annotations
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import os,re
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from cryptography.hazmat.primitives import serialization

from jason_mcp.entra_release_browser_web import (
    AdminReleaseBrowserWeb,LOGIN_COOKIE,DECISION_COOKIE,
)
from implementation.runtime_service.tests.v5_synthetic_identity import AOT_ADMIN_OID,AOT_TENANT,ORIGIN
from implementation.runtime_service.tests.test_release_v5_browser_flow import (
    _fixture,
)
from implementation.runtime_service.tests.test_mobile_release_approval import NOW


def harness(tmp_path,*,enabled=True):
    flow,req,repo,policy,key,proof,ca,root=_fixture(tmp_path)
    oauth=tmp_path/"client-secret";oauth.write_text("synthetic-secret-which-is-never-production");oauth.chmod(0o600)
    signing=tmp_path/"signer";signing.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ));signing.chmod(0o600)
    calls=[]
    def fake_redeemer(**kwargs):
        calls.append(kwargs)
        assert kwargs["route"].admin_approver_oid==AOT_ADMIN_OID
        assert kwargs["route"].tenant_id==AOT_TENANT
        assert kwargs["login"].approval_id==req.approval_id
        assert kwargs["required_auth_context"]=="c1"
        assert kwargs["client_secret"]=="synthetic-secret-which-is-never-production"
        return proof
    web=AdminReleaseBrowserWeb(
        policy_path=flow.policy_path,
        state_root=root,
        approval_db=tmp_path/"approvals.sqlite3",
        session_db=tmp_path/"sessions.sqlite3",
        ca_attestation_path=ca,
        oauth_secret_file=oauth,
        browser_signer_file=signing,
        enabled=enabled,clock=lambda:NOW+timedelta(seconds=4),
        token_redeemer=fake_redeemer,
    )
    app=Starlette(routes=[
        Route("/admin/release-approval",web.begin,methods=["GET"]),
        Route("/admin/release-approval/callback",web.callback,methods=["GET"]),
        Route("/admin/release-approval/decision",web.decide,methods=["POST"]),
    ])
    client=TestClient(app,base_url=ORIGIN,follow_redirects=False)
    return SimpleNamespace(client=client,web=web,request=req,
                           repo=repo,ca=ca,root=root,
                           calls=calls,signing=signing)


def start(session):
    response=session.client.get("/admin/release-approval?request="+session.request.approval_id)
    assert response.status_code==303
    assert response.url.path=="/admin/release-approval"
    url=response.headers["location"]
    params=parse_qs(urlsplit(url).query)
    assert "/oauth2/v2.0/authorize" in url
    assert params["redirect_uri"]==[
        "https://approvals.example.org/admin/release-approval/callback"
    ]
    assert params["prompt"]==["login"]
    assert params["code_challenge_method"]==["S256"]
    cookie=response.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "secure" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    return params["state"][0]


def login(session,*,state=None):
    expected=state if state is not None else start(session)
    response=session.client.get(
        "/admin/release-approval/callback",
        params={"code":"synthetic-auth-code-from-microsoft-1234567890",
                "state":expected},
    )
    return response


def test_entire_browser_approval_records_one_existing_exact_signed_receipt(tmp_path):
    s=harness(tmp_path)
    state=start(s)
    assert s.repo.get(s.request.approval_id).status.value=="pending"
    page=login(s,state=state)
    assert page.status_code==200
    assert "Administrator release decision" in page.text
    assert "Candidate SHA" in page.text
    assert s.request.metadata["candidate_sha"] in page.text
    assert s.request.metadata["rollback_sha"] in page.text
    assert s.request.metadata["scope_sha256"] in page.text
    assert "csrf" in page.text
    assert "samesite=strict" in page.headers["set-cookie"].lower()
    assert s.repo.get(s.request.approval_id).status.value=="pending"
    csrf=re.search(r"name='csrf' value='([^']+)'",page.text).group(1)
    posted=s.client.post(
        "/admin/release-approval/decision",
        headers={"origin":ORIGIN,"sec-fetch-site":"same-origin"},
        data={"csrf":csrf,"decision":"approve"},
    )
    assert posted.status_code==200,posted.text
    assert "Administrator decision recorded" in posted.text
    assert s.repo.get(s.request.approval_id).status.value=="approved"
    assert s.repo.accepted_decision(s.request.approval_id).channel=="microsoft_entra_browser_stepup"
    assert len(s.calls)==1
    repeated=s.client.post(
        "/admin/release-approval/decision",headers={"origin":ORIGIN},
        data={"csrf":csrf,"decision":"approve"},
    )
    assert repeated.status_code==403
    assert len(s.calls)==1


def test_regular_teams_link_without_admin_signin_never_approves(tmp_path):
    s=harness(tmp_path)
    state=start(s)
    assert s.client.post(
        "/admin/release-approval/decision",
        headers={"origin":ORIGIN},data={"csrf":"x"*48,"decision":"approve"},
    ).status_code==403
    assert s.repo.get(s.request.approval_id).status.value=="pending"


def test_wrong_oauth_state_does_not_consume_valid_browser_session(tmp_path):
    s=harness(tmp_path)
    state=start(s)
    bad=login(s,state="attacker-state")
    assert bad.status_code==403
    assert s.repo.get(s.request.approval_id).status.value=="pending"
    good=login(s,state=state)
    assert good.status_code==200


def test_cross_origin_form_and_wrong_csrf_never_authorize(tmp_path):
    s=harness(tmp_path)
    state=start(s);page=login(s,state=state)
    csrf=re.search(r"name='csrf' value='([^']+)'",page.text).group(1)
    for headers,data in [
        ({"origin":"https://attacker.example"},
         {"csrf":csrf,"decision":"approve"}),
        ({"origin":ORIGIN},{"csrf":"invalid","decision":"approve"}),
        ({"origin":ORIGIN},{"csrf":csrf,"decision":"anything"}),
    ]:
        assert s.client.post(
            "/admin/release-approval/decision",headers=headers,data=data,
        ).status_code==403
    assert s.repo.get(s.request.approval_id).status.value=="pending"
    assert s.client.post(
        "/admin/release-approval/decision",headers={"origin":ORIGIN},
        data={"csrf":csrf,"decision":"deny"},
    ).status_code==200
    assert s.repo.get(s.request.approval_id).status.value=="denied"


def test_disabled_profile_never_exposes_oauth_login_or_submit(tmp_path):
    s=harness(tmp_path,enabled=False)
    result=s.client.get("/admin/release-approval?request="+s.request.approval_id)
    assert result.status_code==403
    assert "location" not in result.headers
    assert s.repo.get(s.request.approval_id).status.value=="pending"


def test_missing_mfa_enforcement_ca_receipt_blocks_before_oidc_request(tmp_path):
    s=harness(tmp_path)
    s.ca.unlink()
    result=s.client.get("/admin/release-approval?request="+s.request.approval_id)
    assert result.status_code==403
    assert "location" not in result.headers
    assert s.calls==[]


def test_wrong_host_is_rejected_without_identity_disclosure(tmp_path):
    s=harness(tmp_path)
    result=s.client.get(
        ORIGIN+"/admin/release-approval?request="+s.request.approval_id,
        headers={"host":"attacker.example"},
    )
    assert result.status_code==403
    assert "location" not in result.headers


def test_missing_private_signing_key_is_not_a_release_approval(tmp_path):
    s=harness(tmp_path)
    state=start(s);page=login(s,state=state)
    csrf=re.search(r"name='csrf' value='([^']+)'",page.text).group(1)
    original_signer=s.signing.read_bytes()
    s.signing.unlink()
    result=s.client.post(
        "/admin/release-approval/decision",headers={"origin":ORIGIN},
        data={"csrf":csrf,"decision":"approve"},
    )
    assert result.status_code==403
    assert s.repo.get(s.request.approval_id).status.value=="pending"

    # A missing signer is recoverable: do not consume the real Owner's
    # one-use decision until the reviewed signing key is available.
    s.signing.write_bytes(original_signer)
    s.signing.chmod(0o600)
    retried=s.client.post(
        "/admin/release-approval/decision",headers={"origin":ORIGIN},
        data={"csrf":csrf,"decision":"approve"},
    )
    assert retried.status_code==200
    assert s.repo.get(s.request.approval_id).status.value=="approved"
