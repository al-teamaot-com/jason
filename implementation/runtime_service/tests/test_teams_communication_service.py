"""Constitutional shared Teams delivery, audience, and approval reuse."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from communication.audience.engine import AudiencePolicyEngine
from communication.audience.models import AudienceType, MessagePurpose
from jason_runtime.teams_communication_service import (
    ExistingTeamsGatewayTransport, JasonTeamsCommunicationService,
    TeamsCommunicationRequest,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from jason_runtime.procurement_billing_audit_maintenance import TeamsGatewayBillingAuditSender
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest, ApprovalRequestStatus, ApprovalPresentation,
)

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
ACTOR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
APPROVAL_SUMMARY = "Please approve the exact expense request"


def canonical_approval():
    now=datetime.now(timezone.utc)
    return ApprovalRequest(
        approval_id="expenseapproval-123",request_id="expense-order-123",
        correlation_id="expense-correlation-1",
        organization_id="aot",client_id=None,
        requested_by="employee-one",capability="finance.expense.approve",
        requested_mode="expense:review-only",
        requested_at=now,expires_at=now+timedelta(hours=1),
        authorized_approver_ids=("supervisor-one",),
        presentation=ApprovalPresentation(
            title="Expense supervisor review",summary=APPROVAL_SUMMARY,
            facts=(("Amount","$75"),("Category","Supplies")),
        ),
    )


def binding(*, status="active"):
    return SimpleNamespace(
        jason_identity_id="supervisor-one",
        microsoft_tenant_id=TENANT, microsoft_object_id=ACTOR, status=status,
    )


def adaptive_card():
    return {"type": "AdaptiveCard", "version": "1.5", "body": [
        {"type": "TextBlock", "text": "Approve exact expense request"},
    ], "actions": [{"type": "Action.Submit", "title": "Approve",
                    "data": {"approval_id": "expenseapproval-123", "decision": "approve"}}]}


class FakeResponse:
    def __init__(self, result):
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.result).encode("utf-8")


def transport(tmp_path, monkeypatch, result=None):
    p=tmp_path/"token"; p.write_text("nonsecret-test-token")
    calls=[]
    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(result or {"status":"succeeded","message_id":"provider-accepted-234",
                                       "conversation_id":"teams-123"})
    # Exercise the exact same provider POST used by the governed Teams send
    # capability. Shared workflows must not own a second HTTP implementation.
    import jason_runtime.teams_message_send as module
    monkeypatch.setattr(module,"urlopen",fake_urlopen)
    return ExistingTeamsGatewayTransport("https://gateway.internal",p), calls


def request(**kwargs):
    fields=dict(
        workflow="expense_supervisor", communication_id="expense-message-1",
        correlation_id="expense-correlation-1",
        sender_identity_id="employee-one",
        recipient_identity_id="supervisor-one",
        organization_id="aot", client_id=None,
        audience_type=AudienceType.SERVICE_MANAGER,
        purpose=MessagePurpose.APPROVAL_REQUEST,
        kind="approval", text=APPROVAL_SUMMARY,
        card=None, approval_id="expenseapproval-123",
    )
    fields.update(kwargs)
    return TeamsCommunicationRequest(**fields)


def facade(trans, *, approvals=None, authorized=True, binding_record=None,
           identity=None):
    binding_record = binding_record or binding()
    identity = identity or SimpleNamespace(
        identity_id="supervisor-one", status="active", organization_id="aot")
    authority = SimpleNamespace(can_communicate=Mock(return_value=authorized))
    existing = approvals or SimpleNamespace(get=lambda approval_id:canonical_approval())
    return JasonTeamsCommunicationService(
        transport=trans,
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **args: binding_record),
        identities=SimpleNamespace(get=lambda key: identity),
        workflow_authority=authority, approval_requests=existing,
        audience=AudiencePolicyEngine(),
    )


def test_expense_supervisor_approval_reuses_existing_transport_and_request(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    receipt=facade(trans).send(request())
    assert receipt.delivery_state=="provider_accepted"
    assert receipt.message_id=="provider-accepted-234"
    assert len(calls)==1
    req,timeout=calls[0]
    assert req.full_url=="https://gateway.internal/internal/proactive/send"
    assert req.get_method()=="POST"
    assert timeout==20
    payload=json.loads(req.data)
    assert payload["tenantId"]==TENANT
    assert payload["aadObjectId"]==ACTOR
    assert payload["card"]["type"]=="AdaptiveCard"
    assert "Approval" not in receipt.delivery_state


def test_invoice_po_card_can_share_same_gateway_without_new_approval_stack(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    req=request(
        workflow="invoice_po",kind="card",approval_id=None,card=adaptive_card(),
        text="Draft invoice and PO for supervisor review",
        purpose=MessagePurpose.OPERATIONAL)
    receipt=facade(trans).send(req)
    assert receipt.message_id=="provider-accepted-234"
    assert len(calls)==1


def test_operational_and_technician_messages_share_gateway(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    for workflow in ("disk_health","backupiq","ticket_followup"):
        facade(trans).send(request(
            workflow=workflow, kind="notification",card=None,approval_id=None,
            purpose=MessagePurpose.OPERATIONAL,text="Internal status updated",
            audience_type=AudienceType.INTERNAL_TECHNICIAN))
    assert len(calls)==3


@pytest.mark.parametrize("wrong",[
    dict(authorized=False),
    dict(identity=SimpleNamespace(status="inactive", organization_id="aot")),
    dict(identity=SimpleNamespace(status="active",organization_id="other")),
    dict(binding_record=binding(status="inactive")),
    dict(approvals=SimpleNamespace(get=lambda aid:None)),
])
def test_missing_workflow_authority_or_approval_or_identity_is_denied(
        tmp_path,monkeypatch,wrong):
    trans,calls=transport(tmp_path,monkeypatch)
    with pytest.raises(PermissionError):
        facade(trans,**wrong).send(request())
    assert not calls


def test_approval_must_be_persisted_pending_with_matching_authorized_approver(
        tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    approvals=SimpleNamespace(get=lambda aid:SimpleNamespace(
        status=ApprovalRequestStatus.APPROVED,organization_id="aot",
        authorized_approver_ids=("supervisor-one",)))
    with pytest.raises(PermissionError,match="not pending"):
        facade(trans,approvals=approvals).send(request())
    approvals=SimpleNamespace(get=lambda aid:SimpleNamespace(
        status=ApprovalRequestStatus.PENDING,organization_id="aot",
        authorized_approver_ids=("other-person",)))
    with pytest.raises(PermissionError,match="unauthorized"):
        facade(trans,approvals=approvals).send(request())
    assert not calls


def test_outbound_audience_and_secret_review_are_enforced(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    with pytest.raises(PermissionError,match="external"):
        facade(trans).send(request(
            kind="notification",approval_id=None,card=None,
            audience_type=AudienceType.CLIENT_END_USER,
            purpose=MessagePurpose.OPERATIONAL))
    with pytest.raises(PermissionError,match="content review"):
        facade(trans).send(request(
            kind="notification",approval_id=None,card=None,
            purpose=MessagePurpose.OPERATIONAL,
            text="Here is the password for the account"))
    with pytest.raises(PermissionError):
        facade(trans).send(request(kind="notification", approval_id="expenseapproval-123",
                                   card=None))
    assert not calls


def test_provider_accepted_receipt_never_masquerades_as_user_approval(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch,result={"status":"rejected"})
    with pytest.raises(RuntimeError,match="proactive send failed"):
        facade(trans).send(request())
    assert len(calls)==1  # no blind retry


def test_old_playbook_sender_uses_exact_same_transport(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    sender=TeamsGatewayPlaybookApprovalSender(
        gateway_url=trans.gateway_url,token_file=trans.token_file,
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **kw:binding()),
        owner_identity_ids=("supervisor-one",))
    assert sender.send_status(text="Verified internal owner status")==("provider-accepted-234",)
    assert len(calls)==1


def test_old_billing_audit_sender_reuses_gateway(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    sender=TeamsGatewayBillingAuditSender(
        gateway_url=trans.gateway_url,token_file=Path(trans.token_file),
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **kw:binding()))
    assert sender.technician(jason_identity_id="supervisor-one",
                             text="Hardware billing decision required",
                             card=adaptive_card())=="provider-accepted-234"
    assert len(calls)==1


def test_card_cannot_be_used_as_an_unapproved_status(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="actionable card"):
        facade(trans).send(request(kind="status",approval_id=None,card=adaptive_card()))
    assert not calls


def test_existing_approval_service_accepts_expense_supervisor_vote_once():
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequestService, InMemoryApprovalRequestRepository,
    )
    from jason_runtime.teams_communication_service import ExistingTeamsApprovalReceiptHandler
    from jason_runtime.procurement_teams_flow import ApprovalInteractionDispatcher

    repo=InMemoryApprovalRequestRepository()
    approval=canonical_approval()
    repo.put(approval)
    authority=SimpleNamespace(can_approve=lambda **arg: (
        arg["approver_identity_id"]=="supervisor-one"
        and arg["organization_id"]=="aot"
        and arg["capability"]=="finance.expense.approve"
        and arg["requested_mode"]=="expense:review-only"
    ))
    service=ApprovalRequestService(repo,authority)
    handler=ExistingTeamsApprovalReceiptHandler(
        bindings=SimpleNamespace(find=lambda **kw:binding()),
        identities=SimpleNamespace(get=lambda key:SimpleNamespace(
            identity_id=key,status="active",organization_id="aot")),
        approval_service=service,
        allowed_capabilities=frozenset({"finance.expense.approve"}),
        approval_prefix="expenseapproval-",
    )
    dispatcher=ApprovalInteractionDispatcher(
        procurement=None,fallback=None,
        workflow_routes={"expenseapproval-":handler},
    )
    kwargs=dict(
        approval_id=approval.approval_id,decision="approve",
        selections={},microsoft_tenant_id=TENANT,microsoft_object_id=ACTOR,
        conversation_id="teams-thread-1",channel_response_id="teams-callback-1",
        decided_at=datetime.now(timezone.utc),
    )
    result=dispatcher.handle(**kwargs)
    assert result["status"]=="completed"
    assert result["approval_status"]=="approved"
    assert result["executed"] is False
    receipt=repo.accepted_decision(approval.approval_id)
    assert receipt is not None
    assert receipt.decided_by=="supervisor-one"
    assert receipt.channel=="microsoft_teams"
    with pytest.raises(ValueError,match="no longer pending"):
        dispatcher.handle(**kwargs)
    assert len(repo.decisions)==1


def test_generic_expense_vote_cannot_override_procurement_or_release_routes():
    from jason_runtime.procurement_teams_flow import ApprovalInteractionDispatcher
    flow=SimpleNamespace(handle=lambda **kw:{"approval_id":kw["approval_id"]})
    with pytest.raises(ValueError,match="overlapping"):
        ApprovalInteractionDispatcher(
            procurement=None,fallback=None,
            workflow_routes={"procapproval-":flow},
        )
    with pytest.raises(ValueError,match="invalid"):
        ApprovalInteractionDispatcher(
            procurement=None,fallback=None,
            workflow_routes={"exp*approval-":flow},
        )
    dispatcher=ApprovalInteractionDispatcher(
        procurement=None,fallback=None,
        workflow_routes={"expenseapproval-":flow},
    )
    with pytest.raises(PermissionError,match="universal plan"):
        dispatcher.handle(approval_id="planapproval-controlled")
    with pytest.raises(PermissionError,match="mobile release"):
        dispatcher.handle(approval_id="relapproval-controlled")


def test_expense_wrong_actor_scope_selection_and_decision_fail_closed():
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequestService, InMemoryApprovalRequestRepository,
    )
    from jason_runtime.teams_communication_service import ExistingTeamsApprovalReceiptHandler
    repo=InMemoryApprovalRequestRepository()
    req=canonical_approval();repo.put(req)
    flow=ExistingTeamsApprovalReceiptHandler(
        bindings=SimpleNamespace(find=lambda **kw:binding()),
        identities=SimpleNamespace(get=lambda key:SimpleNamespace(
            identity_id=key,status="active",organization_id="other")),
        approval_service=ApprovalRequestService(
            repo,SimpleNamespace(can_approve=lambda **kw:True)),
        allowed_capabilities=frozenset({"finance.expense.approve"}),
        approval_prefix="expenseapproval-",
    )
    kwargs=dict(
        approval_id=req.approval_id,decision="approve",selections={},
        microsoft_tenant_id=TENANT,microsoft_object_id=ACTOR,
        conversation_id="teams-thread-1",
        channel_response_id="teams-callback-1",
        decided_at=datetime.now(timezone.utc),
    )
    with pytest.raises(PermissionError,match="identity"):
        flow.handle(**kwargs)
    assert not repo.decisions
    flow.identities=SimpleNamespace(get=lambda key:SimpleNamespace(
        identity_id=key,status="active",organization_id="aot"))
    with pytest.raises(PermissionError,match="selections"):
        flow.handle(**{**kwargs,"selections":{"amount":"1000000"}})
    with pytest.raises(PermissionError,match="not permitted"):
        flow.handle(**{**kwargs,"decision":"execute-anything"})
    assert not repo.decisions


def test_approval_requester_scope_and_display_tampering_blocked(tmp_path,monkeypatch):
    trans,calls=transport(tmp_path,monkeypatch)
    svc=facade(trans)
    for mutation in (
        {"sender_identity_id":"different-employee"},
        {"correlation_id":"different-correlation"},
        {"client_id":"another-client"},
        {"text":"Approve ten thousand dollars instead of seventy-five"},
        {"card":adaptive_card()},
        {"purpose":MessagePurpose.FINANCIAL},
    ):
        with pytest.raises(PermissionError):
            svc.send(request(**mutation))
    assert not calls


def test_old_workflows_cannot_fork_a_second_teams_http_transport():
    import inspect
    from jason_runtime import playbook_autonomy_review as playbooks
    from jason_runtime import procurement_billing_audit_maintenance as billing
    for sender in (playbooks.TeamsGatewayPlaybookApprovalSender,
                   billing.TeamsGatewayBillingAuditSender):
        source=inspect.getsource(sender)
        assert "ExistingTeamsGatewayTransport" in source
        assert "/internal/proactive/send" not in source
        assert "urlopen(" not in source


def test_governed_send_and_legacy_workflows_share_one_provider_post():
    import inspect
    from jason_runtime import teams_message_send
    from jason_runtime.teams_communication_service import ExistingTeamsGatewayTransport

    governed=inspect.getsource(teams_message_send.TeamsMessageSendInvoker.invoke_execution_plan)
    reused=inspect.getsource(ExistingTeamsGatewayTransport.send)
    canonical=inspect.getsource(teams_message_send.post_existing_teams_gateway)
    assert "post_existing_teams_gateway(" in governed
    assert "post_existing_teams_gateway(" in reused
    assert "urlopen(" not in governed
    assert "urlopen(" not in reused
    assert canonical.count("urlopen(")==1
    assert '"/internal/proactive/send"' in canonical


def test_callback_server_clock_rejects_expired_pending_decision():
    from dataclasses import replace
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequestService, InMemoryApprovalRequestRepository,
    )
    from jason_runtime.teams_communication_service import ExistingTeamsApprovalReceiptHandler
    repo=InMemoryApprovalRequestRepository()
    now=datetime.now(timezone.utc)
    expired=replace(canonical_approval(),requested_at=now-timedelta(days=2),
                    expires_at=now-timedelta(days=1))
    repo.put(expired)
    flow=ExistingTeamsApprovalReceiptHandler(
        bindings=SimpleNamespace(find=lambda **kw:binding()),
        identities=SimpleNamespace(get=lambda key:SimpleNamespace(
            identity_id=key,status="active",organization_id="aot")),
        approval_service=ApprovalRequestService(
            repo,SimpleNamespace(can_approve=lambda **kw:True)),
        allowed_capabilities=frozenset({"finance.expense.approve"}),
        approval_prefix="expenseapproval-",
    )
    with pytest.raises(PermissionError,match="expired"):
        flow.handle(
            approval_id=expired.approval_id,decision="approve",selections={},
            microsoft_tenant_id=TENANT,microsoft_object_id=ACTOR,
            conversation_id="test-thread",channel_response_id="test-click",
            decided_at=expired.expires_at-timedelta(minutes=1),
        )
    assert not repo.decisions


def test_callback_binding_cannot_switch_tenant_or_actor():
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequestService, InMemoryApprovalRequestRepository,
    )
    from jason_runtime.teams_communication_service import ExistingTeamsApprovalReceiptHandler
    repo=InMemoryApprovalRequestRepository()
    req=canonical_approval();repo.put(req)
    flow=ExistingTeamsApprovalReceiptHandler(
        bindings=SimpleNamespace(find=lambda **kw:binding()),
        identities=SimpleNamespace(get=lambda key:SimpleNamespace(
            identity_id=key,status="active",organization_id="aot")),
        approval_service=ApprovalRequestService(
            repo,SimpleNamespace(can_approve=lambda **kw:True)),
        allowed_capabilities=frozenset({"finance.expense.approve"}),
        approval_prefix="expenseapproval-",
    )
    for wrong in ({"microsoft_tenant_id":"00000000-2222-4333-8444-555555555555"},
                  {"microsoft_object_id":"00000000-bbbb-4ccc-8ddd-eeeeeeeeeeee"}):
        args=dict(approval_id=req.approval_id,decision="approve",selections={},
            microsoft_tenant_id=TENANT,microsoft_object_id=ACTOR,
            conversation_id="test-thread",channel_response_id="test-click",
            decided_at=datetime.now(timezone.utc))
        args.update(wrong)
        with pytest.raises(PermissionError,match="not bound"):
            flow.handle(**args)
    assert not repo.decisions


def test_canonical_adaptive_card_reports_synthetic_receipt_as_unverified(tmp_path, monkeypatch):
    trans, calls = transport(tmp_path, monkeypatch, result={
        "status": "succeeded",
        "message_id": "accepted:synthetic-card",
        "message_id_synthetic": True,
        "delivery_evidence_type": "provider_call_completed_without_message_id",
        "conversation_id": "teams-conversation-1",
    })
    receipt = facade(trans).send(request())
    assert receipt.delivery_state == "provider_accepted_delivery_unverified"
    assert receipt.message_id == "accepted:synthetic-card"
    assert receipt.message_id_synthetic is True
    assert receipt.delivery_evidence_type == "provider_call_completed_without_message_id"
    assert len(calls) == 1  # unknown outcome cannot trigger a blind resend


def _entra_owner_binding(*, email="al@teamaot.com", client_id=None,
                         identity_id=None, status="active"):
    import uuid
    if identity_id is None:
        identity_id = "person-entra-" + uuid.UUID(ACTOR).hex
    return SimpleNamespace(
        jason_identity_id=identity_id,
        microsoft_tenant_id=TENANT,
        microsoft_object_id=ACTOR,
        email_address=email,
        client_id=client_id,
        status=status,
    )


class _OwnerAliasBindings:
    def __init__(self, binding):
        self.binding = binding
        self.identity_reads = []
        self.email_reads = []

    def find_active_by_jason_identity(self, *, jason_identity_id):
        self.identity_reads.append(jason_identity_id)
        return None

    def find_active_by_email(self, *, email_address):
        self.email_reads.append(email_address)
        return self.binding


def test_release_sender_resolves_legacy_owner_alias_through_exact_verified_email(tmp_path, monkeypatch):
    trans, calls = transport(tmp_path, monkeypatch)
    bindings = _OwnerAliasBindings(_entra_owner_binding())
    sender = TeamsGatewayPlaybookApprovalSender(
        gateway_url=trans.gateway_url,
        token_file=trans.token_file,
        bindings=bindings,
        owner_identity_ids=("person-al",),
        owner_identity_email_fallbacks={"person-al": "al@teamaot.com"},
    )
    assert sender.send_status(text="Exact release review required") == ("provider-accepted-234",)
    assert bindings.identity_reads == ["person-al"]
    assert bindings.email_reads == ["al@teamaot.com"]
    assert len(calls) == 1


@pytest.mark.parametrize("binding_value", [
    _entra_owner_binding(email="wrong@teamaot.com"),
    _entra_owner_binding(identity_id="person-entra-00000000000040008000000000000000"),
    _entra_owner_binding(client_id="client-123"),
    _entra_owner_binding(status="disabled"),
])
def test_release_sender_owner_alias_fallback_fails_closed_on_binding_mismatch(
        tmp_path, monkeypatch, binding_value):
    trans, calls = transport(tmp_path, monkeypatch)
    sender = TeamsGatewayPlaybookApprovalSender(
        gateway_url=trans.gateway_url,
        token_file=trans.token_file,
        bindings=_OwnerAliasBindings(binding_value),
        owner_identity_ids=("person-al",),
        owner_identity_email_fallbacks={"person-al": "al@teamaot.com"},
    )
    with pytest.raises(PermissionError, match="fallback binding identity"):
        sender.send_status(text="Exact release review required")
    assert calls == []


def test_release_sender_without_alias_fallback_keeps_direct_binding_requirement(tmp_path, monkeypatch):
    trans, calls = transport(tmp_path, monkeypatch)
    bindings = _OwnerAliasBindings(_entra_owner_binding())
    sender = TeamsGatewayPlaybookApprovalSender(
        gateway_url=trans.gateway_url,
        token_file=trans.token_file,
        bindings=bindings,
        owner_identity_ids=("person-al",),
    )
    with pytest.raises(PermissionError, match="binding unavailable"):
        sender.send_status(text="Exact release review required")
    assert bindings.email_reads == []
    assert calls == []
