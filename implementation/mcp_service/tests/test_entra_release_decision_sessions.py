"""One-time browser form decision is not the same as an OAuth callback."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest

from jason_mcp.entra_release_decision_sessions import OneTimeAdminDecisionStore
from jason_mcp.entra_release_stepup import (
    ExactRelease,EntraStepUpDenied,
)
from jason_mcp.entra_release_stepup import ReleaseIdentityRoute
from implementation.runtime_service.tests.v5_synthetic_identity import (
    AOT_TENANT,AOT_ADMIN_OID,AOT_REQUESTER_OID,CALLBACK_URL,NOTICE_URL,
)
AOT_RELEASE_ROUTE=ReleaseIdentityRoute(
    tenant_id=AOT_TENANT,regular_teams_oid=AOT_REQUESTER_OID,
    admin_approver_oid=AOT_ADMIN_OID,owner_subject_id="person-al",
    registered_redirect_uri=CALLBACK_URL,notice_uri=NOTICE_URL,
)


NOW=datetime.now(timezone.utc).replace(microsecond=0)
APPROVAL=ExactRelease(
    approval_id="relapproval-"+"a"*32,
    candidate_sha="b"*40,rollback_sha="c"*40,
    scope_sha256="d"*64,manifest_sha256="e"*64,
    expires_at=NOW+timedelta(minutes=12),
)


def _proof(approval=APPROVAL):
    return {
        "release_authorized":False,
        "channel":"microsoft_entra_browser_stepup",
        "tenant_id":AOT_RELEASE_ROUTE.tenant_id,
        "authenticated_admin_oid":AOT_RELEASE_ROUTE.admin_approver_oid,
        "approval_id":approval.approval_id,
        "candidate_sha":approval.candidate_sha,
        "rollback_sha":approval.rollback_sha,
        "scope_sha256":approval.scope_sha256,
        "manifest_sha256":approval.manifest_sha256,
        "auth_time":int(NOW.timestamp()),
        "evidence_sha256":"f"*64,
    }


def _store(tmp_path):
    return OneTimeAdminDecisionStore(tmp_path/"admin-browser.sqlite3",route=AOT_RELEASE_ROUTE)


def test_admin_oauth_proof_allows_one_post_only(tmp_path):
    db=_store(tmp_path)
    session=db.issue(approval=APPROVAL,verified_admin_proof=_proof(),now=NOW)
    assert session.approval_id==APPROVAL.approval_id
    assert session.cookie_value!=session.csrf_value
    consumed=db.consume(
        cookie_value=session.cookie_value,csrf_value=session.csrf_value,
        approval=APPROVAL,now=NOW+timedelta(seconds=5),
    )
    assert consumed==_proof()
    with pytest.raises(EntraStepUpDenied,match="REPLAYED"):
        db.consume(
            cookie_value=session.cookie_value,csrf_value=session.csrf_value,
            approval=APPROVAL,now=NOW+timedelta(seconds=8),
        )


def test_wrong_csrf_does_not_consume_admin_browser_session(tmp_path):
    db=_store(tmp_path);s=db.issue(approval=APPROVAL,verified_admin_proof=_proof(),now=NOW)
    with pytest.raises(EntraStepUpDenied,match="CSR"):
        db.consume(cookie_value=s.cookie_value,csrf_value="a"*60,
            approval=APPROVAL,now=NOW+timedelta(seconds=4))
    assert db.consume(cookie_value=s.cookie_value,csrf_value=s.csrf_value,
        approval=APPROVAL,now=NOW+timedelta(seconds=4))==_proof()


@pytest.mark.parametrize("updates",[
    {"candidate_sha":"f"*40},
    {"rollback_sha":"f"*40},
    {"scope_sha256":"f"*64},
    {"manifest_sha256":"f"*64},
    {"approval_id":"relapproval-"+"f"*32},
])
def test_scope_changed_after_login_cannot_be_approved(tmp_path,updates):
    db=_store(tmp_path);s=db.issue(approval=APPROVAL,verified_admin_proof=_proof(),now=NOW)
    changed=replace(APPROVAL,**updates)
    with pytest.raises(EntraStepUpDenied,match="SCOPE_OR_CSRF"):
        db.consume(
            cookie_value=s.cookie_value,csrf_value=s.csrf_value,
            approval=changed,now=NOW+timedelta(seconds=3),
        )


def test_wrong_subject_or_tenant_cannot_issue_decision_session(tmp_path):
    db=_store(tmp_path)
    for key in ("authenticated_admin_oid","tenant_id"):
        p=_proof();p[key]="00000000-0000-0000-0000-000000000001"
        with pytest.raises(EntraStepUpDenied,match="INVALID"):
            db.issue(approval=APPROVAL,verified_admin_proof=p,now=NOW)
    p=_proof();p["release_authorized"]=True
    with pytest.raises(EntraStepUpDenied,match="INVALID"):
        db.issue(approval=APPROVAL,verified_admin_proof=p,now=NOW)


def test_review_session_and_pending_release_expire_independently(tmp_path):
    db=_store(tmp_path);s=db.issue(approval=APPROVAL,verified_admin_proof=_proof(),now=NOW)
    with pytest.raises(EntraStepUpDenied,match="SCOPE_OR_CSRF"):
        db.consume(cookie_value=s.cookie_value,csrf_value=s.csrf_value,
            approval=APPROVAL,now=NOW+timedelta(minutes=6))
