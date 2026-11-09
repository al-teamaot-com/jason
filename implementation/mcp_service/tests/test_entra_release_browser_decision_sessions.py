"""One-time browser approval consent is separate from Entra authentication."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from jason_mcp.entra_release_stepup import EntraStepUpDenied, ExactRelease, ReleaseIdentityRoute
from jason_mcp.entra_release_browser_decision_sessions import OneTimeAdminDecisionStore

NOW=datetime.now(timezone.utc).replace(microsecond=0)
RELEASE=ExactRelease(
    approval_id="relapproval-"+"a"*32,candidate_sha="b"*40,rollback_sha="c"*40,
    scope_sha256="d"*64,manifest_sha256="e"*64,expires_at=NOW+timedelta(minutes=10),
)
ROUTE=ReleaseIdentityRoute(
    tenant_id="11111111-1111-4111-8111-111111111111",
    regular_teams_oid="22222222-2222-4222-8222-222222222222",
    admin_approver_oid="33333333-3333-4333-8333-333333333333",
    owner_subject_id="owner-fixture-01",
    registered_redirect_uri="https://approval.example.org/admin/release-approval/callback",
    notice_uri="https://approval.example.org/admin/release-approval",
)


def proof():
    return {
        "authenticated_admin_oid":ROUTE.admin_approver_oid,
        "tenant_id":ROUTE.tenant_id,
        "owner_subject_id":ROUTE.owner_subject_id,
        "approval_id":RELEASE.approval_id,
        "channel":"microsoft_entra_browser_stepup",
        "candidate_sha":RELEASE.candidate_sha,
        "scope_sha256":RELEASE.scope_sha256,
        "rollback_sha":RELEASE.rollback_sha,
        "manifest_sha256":RELEASE.manifest_sha256,
        "auth_time":int(NOW.timestamp())-40,
        "evidence_sha256":"f"*64,
        "release_authorized":False,
    }


def test_login_does_not_consume_explicit_approval(tmp_path):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    issued=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    assert issued.cookie_value and issued.csrf_token
    assert issued.cookie_value != issued.csrf_token
    assert store.load_consent(cookie_value=issued.cookie_value,approval=RELEASE,now=NOW)==issued.csrf_token
    assert (tmp_path/"decision.db").stat().st_mode&0o777==0o600
    with sqlite3.connect(store.path) as conn:
        row=conn.execute("SELECT cookie_sha256,login_proof FROM admin_release_decision_sessions").fetchone()
        assert row[0] != issued.cookie_value
        assert "id_token" not in row[1]
        assert "client_secret" not in row[1]


def test_explicit_approve_is_atomic_once_and_nonauthorizing(tmp_path):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    session=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    result=store.consume_explicit_decision(
        cookie_value=session.cookie_value,csrf_token=session.csrf_token,
        decision="approve",approval=RELEASE,route=ROUTE,now=NOW,
    )
    assert result["authenticated_admin_oid"]==ROUTE.admin_approver_oid
    assert result["release_authorized"] is False
    with pytest.raises(EntraStepUpDenied,match="MISSING"):
        store.consume_explicit_decision(
            cookie_value=session.cookie_value,csrf_token=session.csrf_token,
            decision="approve",approval=RELEASE,route=ROUTE,now=NOW,
        )


def test_explicit_denial_is_separate_and_one_use(tmp_path):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    session=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    result=store.consume_explicit_decision(
        cookie_value=session.cookie_value,csrf_token=session.csrf_token,
        decision="deny",approval=RELEASE,route=ROUTE,now=NOW,
    )
    assert result["release_authorized"] is False


@pytest.mark.parametrize("invalid",[
    {"csrf_token":"x"*43},
    {"decision":"yes"},
    {"cookie_value":"y"*50},
    {"decision":""},
])
def test_forged_choice_does_not_burn_valid_session(tmp_path,invalid):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    session=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    args={"cookie_value":session.cookie_value,"csrf_token":session.csrf_token,
          "decision":"approve","approval":RELEASE,"route":ROUTE,"now":NOW}
    args.update(invalid)
    with pytest.raises(EntraStepUpDenied):
        store.consume_explicit_decision(**args)
    assert store.load_consent(cookie_value=session.cookie_value,approval=RELEASE,now=NOW)==session.csrf_token


@pytest.mark.parametrize("changed",[
    {"candidate_sha":"a"*40},{"rollback_sha":"a"*40},
    {"scope_sha256":"a"*64},{"manifest_sha256":"a"*64},
    {"approval_id":"relapproval-"+"b"*32},
])
def test_changed_release_cannot_inherit_admin_choice(tmp_path,changed):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    session=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    with pytest.raises(EntraStepUpDenied):
        store.consume_explicit_decision(
            cookie_value=session.cookie_value,csrf_token=session.csrf_token,
            decision="approve",approval=replace(RELEASE,**changed),route=ROUTE,now=NOW,
        )


def test_expired_choice_denied(tmp_path):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    session=store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=proof(),now=NOW)
    with pytest.raises(EntraStepUpDenied,match="EXPIRED"):
        store.consume_explicit_decision(
            cookie_value=session.cookie_value,csrf_token=session.csrf_token,
            decision="approve",approval=RELEASE,route=ROUTE,
            now=NOW+timedelta(seconds=301),
        )


def test_ordinary_teams_account_cannot_issue_admin_consent(tmp_path):
    store=OneTimeAdminDecisionStore(tmp_path/"decision.db")
    swapped=proof();swapped["authenticated_admin_oid"]=ROUTE.regular_teams_oid
    with pytest.raises(EntraStepUpDenied):
        store.issue(approval=RELEASE,route=ROUTE,verified_login_proof=swapped,now=NOW)


def test_private_directory_required(tmp_path):
    public=tmp_path/"public";public.mkdir(mode=0o755)
    with pytest.raises(EntraStepUpDenied,match="PRIVATE"):
        OneTimeAdminDecisionStore(public/"db.sqlite")
