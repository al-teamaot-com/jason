"""Fail-closed Teams licensing acceptance for exact separated release approver.

Tests use isolated JSON, SQLite and Graph fakes; NO real Teams cards or releases.
"""
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, SQLiteApprovalRequestRepository,
)
from jason_runtime.mobile_release_approval import (
    MobileReleaseApprovalMaintenance, MobileReleaseOwnerAuthority,
    read_mobile_release_policy,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender

from implementation.runtime_service.tests.test_admin_separated_release_roles import (
    separated_policy_file, SenderBindings, binding, TENANT, ADMIN, REGULAR,
)
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW, RELEASE, release_record, mark_release_high_impact,
    make_eligible_main_offer,
)


class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, count=None): return json.dumps(self.data).encode()


def actual_sender(tmp_path):
    secret = tmp_path / "gateway-token"
    secret.write_text("not-real-test-token")
    secret.chmod(0o600)
    return TeamsGatewayPlaybookApprovalSender(
        gateway_url="http://127.0.0.1:9999",
        token_file=secret,
        bindings=SenderBindings(binding(ADMIN)),
        owner_identity_ids=("person-al",),
        owner_identity_entra_bindings={"person-al": (TENANT, ADMIN)},
    )


def test_licensed_exact_admin_uses_provider_read_only_preflight(tmp_path):
    sender = actual_sender(tmp_path)
    policy = read_mobile_release_policy(separated_policy_file(tmp_path))
    requests = []
    def fake_send(req, timeout=None):
        requests.append(req)
        assert req.full_url.endswith("/internal/proactive/recipient-eligibility")
        assert json.loads(req.data) == {"tenantId": TENANT, "aadObjectId": ADMIN}
        return Response({"status":"eligible", "tenantId":TENANT, "aadObjectId":ADMIN})
    with patch("urllib.request.urlopen", fake_send):
        sender.preflight_release_recipient_eligibility(policy=policy)
    assert len(requests)==1


@pytest.mark.parametrize("result", [
    {"status":"eligible", "tenantId":TENANT, "aadObjectId":REGULAR},
    {"status":"eligible", "tenantId":"00000000-0000-0000-0000-000000000000", "aadObjectId":ADMIN},
    {"status":"blocked", "error_code":"teams_license_unavailable"},
    {"status":"eligible"},
])
def test_sender_wrong_actor_or_unlicensed_result_fails_closed(tmp_path,result):
    sender = actual_sender(tmp_path)
    policy = read_mobile_release_policy(separated_policy_file(tmp_path))
    with patch("urllib.request.urlopen", return_value=Response(result)):
        with pytest.raises(PermissionError):
            sender.preflight_release_recipient_eligibility(policy=policy)


def test_graph_403_fails_closed_without_email_fallback(tmp_path):
    sender = actual_sender(tmp_path)
    policy = read_mobile_release_policy(separated_policy_file(tmp_path))
    with patch("urllib.request.urlopen", side_effect=HTTPError(
            "http://127.0.0.1:9999",403,"Graph role missing",None,None)):
        with pytest.raises(PermissionError, match="unverified"):
            sender.preflight_release_recipient_eligibility(policy=policy)


def issuer(tmp_path, sender):
    policy_path = separated_policy_file(tmp_path)
    root, path = release_record(tmp_path)
    mark_release_high_impact(root)
    make_eligible_main_offer(root, policy_path)
    repo = SQLiteApprovalRequestRepository(tmp_path/"requests.sqlite3")
    approvals = ApprovalRequestService(repo, MobileReleaseOwnerAuthority(policy_path))
    worker = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path, state_root=root,
        requests=repo, approvals=approvals, sender=sender,
        interval_seconds=60, clock=lambda:NOW, required_policy_version="4.0",
    )
    return worker, repo, root


class Sender:
    def __init__(self, eligible=True):
        self.eligible=eligible;self.sent=[];self.checked=[];self.notices=[]
    def preflight_release_recipient_eligibility(self, *,policy):
        self.checked.append(policy.admin_approver_binding)
        if not self.eligible:
            raise PermissionError("unlicensed admin account")
    def send(self, request):
        self.sent.append(request)
        return ("verified-provider-acceptance-only",)
    def notify_separated_requester_unavailable(self, *,policy,release_id):
        self.notices.append((policy.regular_requester_binding, release_id))
        return "informational-message-only"


def test_unlicensed_admin_creates_no_pending_release_card(tmp_path):
    sender=Sender(False)
    worker, repo, root=issuer(tmp_path, sender)
    assert worker.tick() is False
    assert repo.list_all()==()
    assert sender.sent==[]
    assert sender.checked == [(TENANT, ADMIN)]
    marker=root/"mobile-release-recipient-blocks"/(RELEASE+".json")
    stored=json.loads(marker.read_text())
    assert stored["status"]=="recipient_unavailable"
    assert stored["approval_issued"] is False
    assert stored["alternate_approver_authorized"] is False
    assert stored["admin_approver_object_id"]==ADMIN
    assert stat.S_IMODE(marker.stat().st_mode)==0o600
    assert stored["informational_notice_message_id"]=="informational-message-only"
    assert sender.notices==[((TENANT,REGULAR), RELEASE)]
    baseline=marker.read_bytes()
    worker._next_due=NOW
    assert worker.tick() is False
    assert marker.read_bytes()==baseline
    assert len(sender.notices)==1


def test_missing_verifier_fails_and_records_block_without_sender_fallback(tmp_path):
    class NoCheck:
        sent=[]
        def send(self,request):
            self.sent.append(request)
            return ("should-never-send",)
    sender=NoCheck()
    worker,repo,root=issuer(tmp_path,sender)
    assert worker.tick() is False
    assert repo.list_all()==() and not sender.sent
    assert (root/"mobile-release-recipient-blocks"/(RELEASE+".json")).exists()


def test_verified_admin_creates_single_actionable_release_card_without_grant(tmp_path):
    sender=Sender(True)
    worker,repo,root=issuer(tmp_path,sender)
    assert worker.tick() is True
    assert len(sender.sent)==1
    assert sender.checked==[(TENANT,ADMIN)]
    assert repo.list_all()[0].authorized_approver_ids==("person-al",)
    assert repo.accepted_decision(sender.sent[0].approval_id) is None
    assert not (root/"mobile-release-recipient-blocks"/(RELEASE+".json")).exists()
    worker._next_due=NOW
    assert worker.tick() is False
    assert len(sender.sent)==1


def test_informational_notice_targets_only_regular_bound_actor_without_card(tmp_path):
    class BothBindings:
        def find(self, *,microsoft_tenant_id,microsoft_object_id):
            assert microsoft_tenant_id == TENANT
            assert microsoft_object_id in (ADMIN,REGULAR)
            return binding(microsoft_object_id)
    secret=tmp_path/"token"
    secret.write_text("test-token")
    sender=TeamsGatewayPlaybookApprovalSender(
        gateway_url="http://127.0.0.1:9999", token_file=secret,
        bindings=BothBindings(),owner_identity_ids=("person-al",),
        owner_identity_entra_bindings={"person-al":(TENANT,ADMIN)},
    )
    policy=read_mobile_release_policy(separated_policy_file(tmp_path))
    class Transport:
        def send(self,*,binding,text,card=None):
            assert binding.microsoft_object_id == REGULAR
            assert card is None
            assert "No new approval was issued" in text
            return SimpleNamespace(message_id="read-only-status-1")
    sender._existing_transport=lambda:Transport()
    assert sender.notify_separated_requester_unavailable(
        policy=policy,release_id=RELEASE)=="read-only-status-1"


def test_notification_cannot_use_approver_identity_as_requester(tmp_path):
    sender=actual_sender(tmp_path)
    policy=read_mobile_release_policy(separated_policy_file(tmp_path))
    from dataclasses import replace
    bad=replace(policy,regular_requester_binding=(TENANT,ADMIN))
    with pytest.raises(PermissionError,match="requester"):
        sender.notify_separated_requester_unavailable(policy=bad,release_id=RELEASE)


def test_prior_pending_unlicensed_admin_is_surfaced_without_new_approval(tmp_path):
    from jason_runtime.mobile_release_approval import (
        read_eligible_release, create_mobile_release_request,
    )
    sender=Sender(False)
    worker,repo,root=issuer(tmp_path,sender)
    policy=read_mobile_release_policy(worker.policy_path)
    existing=create_mobile_release_request(
        read_eligible_release(root,RELEASE,policy),policy,now=NOW,
    )
    worker.approvals.create(existing,now=NOW)
    assert len(repo.list_all()) == 1
    assert worker.tick() is False
    assert len(repo.list_all()) == 1
    assert repo.accepted_decision(existing.approval_id) is None
    assert sender.sent == []
    marker=root/"mobile-release-recipient-blocks"/(RELEASE+".json")
    record=json.loads(marker.read_text())
    assert record["previous_pending_request"] is True
    assert record["alternate_approver_authorized"] is False
    assert sender.notices == [((TENANT,REGULAR),RELEASE)]


def test_existing_pending_licensed_admin_does_not_duplicate_approval(tmp_path):
    from jason_runtime.mobile_release_approval import (
        read_eligible_release, create_mobile_release_request,
    )
    sender=Sender(True)
    worker,repo,root=issuer(tmp_path,sender)
    policy=read_mobile_release_policy(worker.policy_path)
    req=create_mobile_release_request(read_eligible_release(root,RELEASE,policy),policy,now=NOW)
    worker.approvals.create(req,now=NOW)
    assert worker.tick() is False
    assert len(repo.list_all()) == 1
    assert sender.sent == []
    assert sender.checked == [(TENANT,ADMIN)]


def test_historical_preflight_policy_drift_does_not_change_binding(tmp_path):
    sender=Sender(False)
    worker,repo,root=issuer(tmp_path,sender)
    assert worker.tick() is False
    original=(root/"mobile-release-recipient-blocks"/(RELEASE+".json")).read_bytes()
    # An authenticated policy migration is required. Rewriting this record
    # does not quietly authorize the previously approved requester.
    policy_path=worker.policy_path
    doc=json.loads(policy_path.read_text())
    doc["regular_requester_binding"]["microsoft_object_id"]=ADMIN
    policy_path.write_text(json.dumps(doc))
    policy_path.chmod(0o600)
    worker._next_due=NOW
    with pytest.raises(PermissionError):
        worker.tick()
    assert (root/"mobile-release-recipient-blocks"/(RELEASE+".json")).read_bytes()==original
    assert not sender.sent
