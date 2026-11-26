"""Root's GitHub CI verifier: required successful checks, not all noisy jobs."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from tools import pmv4_e_canary_oneowner_root as r

BUILD="d"*40
MAIN=BUILD
OLDER=r.CANDIDATE
REQUIRED=[
    "cap-001","cap-003","cap-007","system-registry","runtime-service",
    "repository-hygiene","conversation-experience","teams-gateway",
]
WORKFLOWS=[
    "Validate Jason","SEC-007 Security Regressions",
    "Validate Jason Teams Gateway","Validate Conversation Experience Foundation",
]


def api_fixture(monkeypatch,*,target=BUILD,failed=None,missing=None,
                wrong_app=False,unprotected=False,stale=False,
                skipped_router=True,wrong_branch=False):
    found=[]
    now=datetime.now(timezone.utc)
    completed=(now-timedelta(days=10) if stale else now-timedelta(minutes=3))
    stamp=completed.isoformat()
    rows=[
        {
            "name":name,
            "sha":target,"status":"completed",
            "conclusion":"failure" if name==failed else "success",
            "app":0 if wrong_app and name=="cap-001" else 15368,
            "at":stamp,
        } for name in REQUIRED if name!=missing
    ]
    if skipped_router:
        rows.extend({
            "name":"classify","sha":target,"status":"completed",
            "conclusion":"skipped","app":15368,"at":stamp,
        } for _ in range(4))
    def f(endpoint,query):
        found.append(endpoint)
        if endpoint.endswith("/branches/main"):
            return {"name":"main","protected":not unprotected,"sha":MAIN}
        if "/compare/" in endpoint:
            return {"status":"identical" if target==MAIN else "ahead",
                    "merge_base_sha":target}
        if endpoint.endswith("/protection/required_status_checks"):
            return {"strict":True,"checks":[{"context":n,"app_id":15368}
                                            for n in REQUIRED]}
        if "/check-runs" in endpoint:
            return {"count":len(rows),"rows":rows}
        if "/actions/runs?" in endpoint:
            jobs=[
                {"name":name,"sha":target,
                 "branch":"feature/testing" if wrong_branch else "main",
                 "event":"push","status":"completed","conclusion":"success",
                 "at":stamp,
                } for name in WORKFLOWS
            ]
            return {"total":len(jobs),"rows":jobs}
        raise AssertionError("Unexpected GitHub call:"+endpoint)
    monkeypatch.setattr(r,"gh_api",f)
    return found


def test_ci_accepts_exact_required_and_skipped_nonrequired_routing_jobs(
    monkeypatch,
):
    endpoints=api_fixture(monkeypatch)
    result=r.verify_ci(MAIN)
    assert result["required_ci_passed"] is True
    assert result["check_count"]==8
    assert result["protected_main"]==MAIN
    assert len(endpoints)==5


def test_ancestor_source_ci_does_not_require_same_head(monkeypatch):
    api_fixture(monkeypatch,target=OLDER)
    result=r.verify_ci(OLDER)
    assert result["required_ci_passed"] is True
    assert result["protected_main"]==MAIN


@pytest.mark.parametrize("bad,matcher",[
    ({"failed":"cap-003"},"NATIVE_REQUIRED_CHECK_NOT_SUCCESSFUL"),
    ({"missing":"cap-003"},"REQUIRED_CHECK_RUN_MISSING_OR_AMBIGUOUS"),
    ({"wrong_app":True},"NATIVE_REQUIRED_CHECK_NOT_SUCCESSFUL"),
    ({"unprotected":True},"CURRENT_PROTECTED_MAIN_UNVERIFIED"),
    ({"stale":True},"NATIVE_REQUIRED_CHECK_STALE"),
    ({"wrong_branch":True},"REQUIRED_PROTECTED_WORKFLOW_NOT_SUCCESSFUL"),
])
def test_unauthorized_or_stale_native_github_state_denies(monkeypatch,bad,matcher):
    api_fixture(monkeypatch,**bad)
    with pytest.raises(r.Denied,match=matcher):
        r.verify_ci(MAIN)
