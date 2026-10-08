from datetime import datetime, timedelta, timezone

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService,
    InMemoryApprovalRequestRepository,
)
from jason_runtime.playbook_action_approval import (
    OwnerOnlyPlaybookActionAuthority,
    PlaybookActionApprovalCoordinator,
    PlaybookActionApprovalInteractionFlow,
)
from jason_runtime.playbook_approval_resume import (
    PlaybookActionProposal,
    SQLitePlaybookActionProposalStore,
)


NOW = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)


class Sender:
    def __init__(self):
        self.calls = []

    def send(self, request):
        self.calls.append(request.approval_id)
        return ("teams-message-1",)


class Binding:
    status = "active"
    jason_identity_id = "person-al"


class Bindings:
    def find(self, **kwargs):
        return Binding()


def proposal():
    return PlaybookActionProposal(
        proposal_id="proposal-idle-1",
        playbook_id="idle_log_off",
        playbook_version="1.1.0",
        policy_id="playbook-autonomy:idle_log_off",
        ticket_id=141066,
        client_id="507",
        target_id="device-1",
        capability="automation.component.execute",
        action_id="Set Idle Log Off AOT Ver 02042026-1",
        arguments={
            "device_uid": "device-1",
            "component_uid": "component-1",
            "component_name": "Set Idle Log Off AOT Ver 02042026-1",
            "variables": {},
            "job_name": "Jason autonomous idle_log_off idle_log_off_repair T141066",
            "idempotency_key": "autonomy:idle_log_off:1.1.0:141066:device-1:idle_log_off_repair",
        },
        disruption_classification="modifying_future_user_session",
        expected_verification="authoritative Idle Log Off alert clears",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=4),
    )


def setup(tmp_path):
    proposals = SQLitePlaybookActionProposalStore(tmp_path / "proposals.sqlite3")
    requests = InMemoryApprovalRequestRepository()
    service = ApprovalRequestService(
        repository=requests,
        authority=OwnerOnlyPlaybookActionAuthority(("person-al",)),
    )
    sender = Sender()
    coordinator = PlaybookActionApprovalCoordinator(
        proposal_store=proposals,
        approval_service=service,
        sender=sender,
        owner_identity_ids=("person-al",),
    )
    flow = PlaybookActionApprovalInteractionFlow(
        bindings=Bindings(),
        approval_service=service,
        proposal_store=proposals,
    )
    return proposals, requests, sender, coordinator, flow


def test_one_exact_request_is_created_and_delivered_once(tmp_path):
    proposals, requests, sender, coordinator, _ = setup(tmp_path)
    item = proposal()
    coordinator.ensure_pending(item)
    coordinator.ensure_pending(item)
    approval_id = coordinator.approval_id_for(item)
    request = requests.get(approval_id)
    assert request is not None
    assert request.metadata["proposal_fingerprint"] == item.fingerprint
    assert request.metadata["target_id"] == "device-1"
    assert sender.calls == [approval_id]
    proposals.close()


def test_matching_teams_approval_binds_exact_execution(tmp_path):
    proposals, _, _, coordinator, flow = setup(tmp_path)
    item = proposal()
    coordinator.ensure_pending(item)
    approval_id = coordinator.approval_id_for(item)
    result = flow.handle(
        approval_id=approval_id,
        decision="approve",
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conversation",
        channel_response_id="response-1",
        decided_at=NOW + timedelta(minutes=5),
    )
    assert result["status"] == "completed"
    state = coordinator.state_for_ticket(item.ticket_id)
    assert state is not None and state.status == "approved"
    auth = coordinator.authorization_for(
        ticket_id=item.ticket_id,
        capability=item.capability,
        action_id=item.action_id,
        target_id=item.target_id,
        arguments=item.arguments,
    )
    assert auth.approval_request_id == approval_id
    assert auth.proposal_fingerprint == item.fingerprint
    proposals.close()


def test_changed_arguments_cannot_use_approval(tmp_path):
    proposals, _, _, coordinator, flow = setup(tmp_path)
    item = proposal()
    coordinator.ensure_pending(item)
    flow.handle(
        approval_id=coordinator.approval_id_for(item),
        decision="approve",
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conversation",
        channel_response_id="response-1",
        decided_at=NOW + timedelta(minutes=5),
    )
    changed = dict(item.arguments)
    changed["variables"] = {"minutes": "5"}
    with pytest.raises(PermissionError):
        coordinator.authorization_for(
            ticket_id=item.ticket_id,
            capability=item.capability,
            action_id=item.action_id,
            target_id=item.target_id,
            arguments=changed,
        )
    proposals.close()


def test_denial_is_terminal_and_never_authorizes_execution(tmp_path):
    proposals, _, _, coordinator, flow = setup(tmp_path)
    item = proposal()
    coordinator.ensure_pending(item)
    flow.handle(
        approval_id=coordinator.approval_id_for(item),
        decision="deny",
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        conversation_id="conversation",
        channel_response_id="response-1",
        decided_at=NOW + timedelta(minutes=5),
    )
    with pytest.raises(PermissionError):
        coordinator.authorization_for(
            ticket_id=item.ticket_id,
            capability=item.capability,
            action_id=item.action_id,
            target_id=item.target_id,
            arguments=item.arguments,
        )
    proposals.close()


def test_approval_dispatcher_routes_playaction_prefix_only_to_action_flow():
    from jason_runtime.procurement_teams_flow import ApprovalInteractionDispatcher

    class Flow:
        def __init__(self, label):
            self.label = label
            self.calls = 0

        def handle(self, **kwargs):
            self.calls += 1
            return {"flow": self.label, "approval_id": kwargs["approval_id"]}

    procurement = Flow("procurement")
    playbook_action = Flow("playbook_action")
    fallback = Flow("fallback")
    dispatcher = ApprovalInteractionDispatcher(
        procurement=procurement,
        playbook_action=playbook_action,
        fallback=fallback,
    )

    result = dispatcher.handle(approval_id="playaction-abc")
    assert result["flow"] == "playbook_action"
    assert playbook_action.calls == 1
    assert procurement.calls == 0
    assert fallback.calls == 0
