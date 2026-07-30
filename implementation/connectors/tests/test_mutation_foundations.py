from datetime import datetime, timedelta, timezone

import pytest

from connectors.autotask.mutations import AutotaskMutationConnector
from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext, ConnectorRequest
from connectors.core.mutations import ApprovalGrant


class MemoryAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context, details))


class ApprovalStore:
    def __init__(self, grant):
        self.grant = grant
        self.consumed = []

    def resolve(self, approval_id, context):
        assert approval_id == self.grant.approval_id
        return self.grant

    def consume(self, approval_id, context):
        self.consumed.append(approval_id)


def context(capability, mode="propose"):
    return ConnectorContext(
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        capability=capability,
        mode=mode,
    )


def test_autotask_write_can_be_proposed_without_live_executor():
    audit = MemoryAudit()
    connector = AutotaskMutationConnector(audit=audit)
    result = connector.execute(
        ConnectorRequest(
            context("autotask.ticket.note.add_internal"),
            {"ticket_id": 123, "note": "Reviewed diagnostic evidence.", "reason": "Document investigation"},
        )
    )
    assert result.data["status"] == "proposed"
    assert result.data["plan"]["proposed_changes"]["visibility"] == "internal"
    assert any(event[0] == "connector.mutation.planned" for event in audit.events)


def test_execute_requires_approval_and_idempotency_key():
    connector = AutotaskMutationConnector(audit=MemoryAudit())
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(
            ConnectorRequest(
                context("autotask.ticket.status.update", mode="execute"),
                {"ticket_id": 123, "status_id": 5, "reason": "Move after validation"},
            )
        )


def test_approval_is_bound_to_exact_argument_digest():
    audit = MemoryAudit()
    proposer = AutotaskMutationConnector(audit=audit)
    proposed = proposer.execute(
        ConnectorRequest(
            context("autotask.ticket.note.add_client"),
            {"ticket_id": 123, "note": "Testing completed.", "reason": "Client update"},
        )
    )
    digest = proposed.data["argument_digest"]
    now = datetime.now(timezone.utc)
    grant = ApprovalGrant(
        approval_id="approval-1",
        capability="autotask.ticket.note.add_client",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        approved_by="manager-1",
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=10),
        argument_digest=digest,
    )
    connector = AutotaskMutationConnector(audit=audit, approvals=ApprovalStore(grant))
    with pytest.raises(RuntimeError, match="execution is not configured"):
        connector.execute(
            ConnectorRequest(
                context("autotask.ticket.note.add_client", mode="execute"),
                {
                    "ticket_id": 123,
                    "note": "Testing completed.",
                    "reason": "Client update",
                    "approval_id": "approval-1",
                    "idempotency_key": "idem-1",
                },
            )
        )


def test_approval_does_not_authorize_modified_change():
    audit = MemoryAudit()
    now = datetime.now(timezone.utc)
    grant = ApprovalGrant(
        approval_id="approval-1",
        capability="autotask.ticket.note.add_client",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        approved_by="manager-1",
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=10),
        argument_digest="wrong-digest",
    )
    connector = AutotaskMutationConnector(audit=audit, approvals=ApprovalStore(grant))
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(
            ConnectorRequest(
                context("autotask.ticket.note.add_client", mode="execute"),
                {
                    "ticket_id": 123,
                    "note": "Changed after approval.",
                    "reason": "Client update",
                    "approval_id": "approval-1",
                    "idempotency_key": "idem-1",
                },
            )
        )
