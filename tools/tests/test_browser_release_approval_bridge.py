"""Dormant browser decision bridge reuses Jason's only approval ledger."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, ApprovalRequestStatus, InMemoryApprovalRequestRepository,
)
from jason_runtime.mobile_release_approval import MobileReleaseSignedEvidenceStore
from jason_runtime.browser_release_approval_bridge import V5BrowserApprovalDecisionBridge
from tools.tests.test_verify_browser_release_evidence import environment


class Authority:
    def __init__(self, allowed=True):
        self.allowed=allowed
        self.calls=0
    def can_approve(self,**kwargs):
        self.calls+=1
        return self.allowed


def fixture(tmp_path, *, allowed=True):
    src=environment(tmp_path)
    repo=InMemoryApprovalRequestRepository()
    repo.put(src["request"])
    authority=Authority(allowed)
    flow=ApprovalRequestService(repo,authority)
    evidence=MobileReleaseSignedEvidenceStore(tmp_path/"approval-ledger.sqlite")
    bridge=V5BrowserApprovalDecisionBridge(
        approvals=flow,requests=repo,signed_evidence=evidence,
        reviewed_route=src["route"],
        root_trust_path=src["root_trust_path"],
        reviewed_policy_sha256=src["policy_sha256"],
        organization_id=src["organization_id"],
        owner_identity_ids=src["owner_identity_ids"],
        policy_version="5.0",
    )
    return src,repo,bridge,authority


def test_exact_v5_admin_evidence_uses_existing_single_approval_ledger(tmp_path):
    source,repository,bridge,authority=fixture(tmp_path)
    result=bridge.handle_signed_browser_decision(
        envelope=source["envelope"],exact_release=source["exact_release"],
        now=source["now"],
    )
    assert result["status"]=="existing_approval_ledger_decision"
    assert result["decision_status"]=="approved"
    assert result["release_authorized"] is False
    assert result["executed"] is False
    assert repository.get(source["exact_release"].approval_id).status is ApprovalRequestStatus.APPROVED
    assert authority.calls==1


def test_v4_policy_cannot_call_v5_decision_bridge(tmp_path):
    src,repo,bridge,authority=fixture(tmp_path)
    bridge.policy_version="4.0"
    with pytest.raises(PermissionError,match="V5_BROWSER_POLICY_NOT_INSTALLED"):
        bridge.handle_signed_browser_decision(
            envelope=src["envelope"],exact_release=src["exact_release"],now=src["now"],
        )
    assert repo.get(src["exact_release"].approval_id).status is ApprovalRequestStatus.PENDING


def test_jason_canonical_authority_denial_blocks_signed_evidence_approval(tmp_path):
    src,repo,bridge,authority=fixture(tmp_path,allowed=False)
    with pytest.raises(PermissionError,match="Jason authority denied"):
        bridge.handle_signed_browser_decision(
            envelope=src["envelope"],exact_release=src["exact_release"],now=src["now"],
        )
    assert repo.get(src["exact_release"].approval_id).status is ApprovalRequestStatus.PENDING
    assert authority.calls==1


@pytest.mark.parametrize("tamper",["tenant","oid","sha","policy","expiry","channel"])
def test_browser_bridge_rejects_cross_binding_or_stale_scope(tmp_path,tamper):
    src,repo,bridge,authority=fixture(tmp_path)
    env=src["envelope"]
    if tamper=="tenant":
        bridge.reviewed_route=replace(bridge.reviewed_route,tenant_id="99999999-9999-4999-8999-999999999999")
    elif tamper=="oid":
        bridge.reviewed_route=replace(bridge.reviewed_route,admin_approver_oid=bridge.reviewed_route.regular_teams_oid)
    elif tamper=="sha":
        src["exact_release"]=replace(src["exact_release"],candidate_sha="0"*40)
    elif tamper=="policy":
        bridge.reviewed_policy_sha256="0"*64
    elif tamper=="expiry":
        src["now"]=src["now"]+timedelta(minutes=11)
    elif tamper=="channel":
        env=dict(env);env["payload"]=dict(env["payload"])
        env["payload"]["channel"]="microsoft_teams"
    with pytest.raises(PermissionError):
        bridge.handle_signed_browser_decision(
            envelope=env,exact_release=src["exact_release"],now=src["now"],
        )
    assert repo.get(src["request"].approval_id).status is ApprovalRequestStatus.PENDING


def test_parallel_double_submit_cannot_create_second_decision(tmp_path):
    src,repo,bridge,authority=fixture(tmp_path)
    kwargs=dict(envelope=src["envelope"],exact_release=src["exact_release"],now=src["now"])
    first=bridge.handle_signed_browser_decision(**kwargs)
    assert first["decision_status"]=="approved"
    with pytest.raises(PermissionError):
        bridge.handle_signed_browser_decision(**kwargs)
    assert authority.calls==1
