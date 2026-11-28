"""One-use server-side browser authentication sessions (no approvals)."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3

import pytest

from jason_mcp.entra_release_browser_sessions import OneTimeBrowserLoginStore
from jason_mcp.entra_release_stepup import ExactRelease, EntraStepUpDenied


NOW = datetime.now(timezone.utc).replace(microsecond=0)
APPROVAL = ExactRelease(
    approval_id="relapproval-"+"a"*32,
    candidate_sha="b"*40, rollback_sha="c"*40,
    scope_sha256="d"*64, manifest_sha256="e"*64,
    expires_at=NOW+timedelta(minutes=12),
)


def _store(tmp_path):
    return OneTimeBrowserLoginStore(tmp_path/"sessions.db")


def test_issue_is_bounded_secure_cookie_and_only_server_stores_pkce(tmp_path):
    store=_store(tmp_path)
    session=store.issue(approval=APPROVAL, now=NOW)
    assert session.cookie_secure is True
    assert session.cookie_http_only is True
    assert session.cookie_same_site == "Lax"
    assert len(session.cookie_value) >= 40
    assert session.cookie_value not in str(session.login)
    assert (tmp_path/"sessions.db").stat().st_mode & 0o777 == 0o600
    db=sqlite3.connect(tmp_path/"sessions.db")
    row=db.execute("SELECT cookie_sha256,code_verifier FROM browser_login_sessions").fetchone()
    assert row[0] == sha256(session.cookie_value.encode()).hexdigest()
    assert row[0] != session.cookie_value
    assert row[1] == session.login.code_verifier
    assert session.login.exact_release_fingerprint == APPROVAL.fingerprint()


def test_callback_consumes_exact_state_once(tmp_path):
    store=_store(tmp_path)
    issued=store.issue(approval=APPROVAL, now=NOW)
    login=store.consume(
        cookie_value=issued.cookie_value, returned_state=issued.login.state,
        approval=APPROVAL, now=NOW+timedelta(seconds=15),
    )
    assert login == issued.login
    with pytest.raises(EntraStepUpDenied, match="MISSING_OR_REPLAYED"):
        store.consume(
            cookie_value=issued.cookie_value,
            returned_state=issued.login.state,
            approval=APPROVAL, now=NOW+timedelta(seconds=16),
        )


def test_wrong_cookie_or_state_cannot_consume_valid_session(tmp_path):
    store=_store(tmp_path)
    issued=store.issue(approval=APPROVAL, now=NOW)
    with pytest.raises(EntraStepUpDenied, match="MISSING_OR_REPLAYED"):
        store.consume(
            cookie_value="x"*50, returned_state=issued.login.state,
            approval=APPROVAL, now=NOW+timedelta(seconds=10),
        )
    with pytest.raises(EntraStepUpDenied, match="STATE_OR_SCOPE"):
        store.consume(
            cookie_value=issued.cookie_value, returned_state="attacker",
            approval=APPROVAL, now=NOW+timedelta(seconds=10),
        )
    assert store.consume(
        cookie_value=issued.cookie_value, returned_state=issued.login.state,
        approval=APPROVAL, now=NOW+timedelta(seconds=10),
    ) == issued.login


@pytest.mark.parametrize("changed", [
    {"scope_sha256":"f"*64},
    {"rollback_sha":"f"*40},
    {"manifest_sha256":"f"*64},
    {"candidate_sha":"f"*40},
    {"approval_id":"relapproval-"+"f"*32},
])
def test_mutated_release_never_inherits_login(tmp_path, changed):
    store=_store(tmp_path)
    issued=store.issue(approval=APPROVAL, now=NOW)
    with pytest.raises(EntraStepUpDenied, match="STATE_OR_SCOPE"):
        store.consume(
            cookie_value=issued.cookie_value,
            returned_state=issued.login.state,
            approval=replace(APPROVAL, **changed),
            now=NOW+timedelta(seconds=10),
        )
    assert store.consume(
        cookie_value=issued.cookie_value,
        returned_state=issued.login.state,
        approval=APPROVAL, now=NOW+timedelta(seconds=10),
    ) == issued.login


def test_expired_pending_browser_login_fails_closed(tmp_path):
    store=_store(tmp_path)
    issued=store.issue(approval=APPROVAL, now=NOW)
    with pytest.raises(EntraStepUpDenied, match="STATE_OR_SCOPE"):
        store.consume(
            cookie_value=issued.cookie_value,
            returned_state=issued.login.state,
            approval=APPROVAL, now=NOW+timedelta(minutes=6),
        )


def test_expired_release_prevents_callback_even_if_login_recent(tmp_path):
    store=_store(tmp_path)
    approval=replace(APPROVAL,expires_at=NOW+timedelta(seconds=25))
    issued=store.issue(approval=approval,now=NOW)
    with pytest.raises(EntraStepUpDenied, match="STATE_OR_SCOPE"):
        store.consume(
            cookie_value=issued.cookie_value,
            returned_state=issued.login.state,
            approval=approval, now=NOW+timedelta(seconds=25),
        )


def test_session_file_and_parent_cannot_be_public_or_symlink(tmp_path):
    public=tmp_path/"public"
    public.mkdir()
    os.chmod(public,0o755)
    with pytest.raises(EntraStepUpDenied,match="DIRECTORY_NOT_PRIVATE"):
        OneTimeBrowserLoginStore(public/"sessions.db")
    target=tmp_path/"actual.db"
    target.touch(mode=0o600)
    link=tmp_path/"link.db"
    link.symlink_to(target)
    with pytest.raises(EntraStepUpDenied,match="PATH_SYMLINK"):
        OneTimeBrowserLoginStore(link)
    os.chmod(target,0o644)
    with pytest.raises(EntraStepUpDenied,match="FILE_NOT_PRIVATE"):
        OneTimeBrowserLoginStore(target)


def test_two_parallel_requests_cannot_swap_browser_sessions(tmp_path):
    store=_store(tmp_path)
    a=store.issue(approval=APPROVAL,now=NOW)
    other=replace(APPROVAL,approval_id="relapproval-"+"f"*32)
    b=store.issue(approval=other,now=NOW)
    with pytest.raises(EntraStepUpDenied,match="STATE_OR_SCOPE"):
        store.consume(
            cookie_value=a.cookie_value,returned_state=b.login.state,
            approval=APPROVAL,now=NOW+timedelta(seconds=5),
        )
    assert store.consume(
        cookie_value=b.cookie_value,returned_state=b.login.state,
        approval=other,now=NOW+timedelta(seconds=5),
    ) == b.login
    assert store.consume(
        cookie_value=a.cookie_value,returned_state=a.login.state,
        approval=APPROVAL,now=NOW+timedelta(seconds=5),
    ) == a.login
