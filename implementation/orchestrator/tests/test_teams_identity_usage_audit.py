from __future__ import annotations

from orchestrator.event_store import SQLiteOrchestrationEventStore
from orchestrator.teams_conversation_flow import TeamsConversationPrincipalEvidence
from orchestrator.teams_identity_binding import SQLiteMicrosoftDirectoryUsageAudit


def test_directory_usage_audit_keeps_only_allowlisted_trace_fields(tmp_path):
    store = SQLiteOrchestrationEventStore(tmp_path / "events.sqlite3")
    audit = SQLiteMicrosoftDirectoryUsageAudit(store)
    evidence = TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-never-export",
        microsoft_object_id="object-never-export",
        authentication_assurance="botframework-authenticated",
        conversation_id="conv-1",
        message_id="msg-1",
    )

    audit.record(
        "identity.directory.completed",
        principal_id="user-al",
        organization_id="aot",
        client_id=None,
        evidence=evidence,
        details={
            "outcome": "completed",
            "email_address": "al@teamaot.com",
            "access_token": "token-never-export",
            "authorization": "authorization-never-export",
            "provider_response": "response-never-export",
            "prompt": "prompt-never-export",
        },
    )

    rows = store.list_by_correlation("teams-directory:conv-1:msg-1")
    assert len(rows) == 1
    event = rows[0]
    assert event.event_type == "identity.directory.completed"
    assert event.principal_id == "user-al"
    assert event.capability_name == "identity.profile.enrich"
    assert event.payload["requester_kind"] == "human"
    assert event.payload["details"] == {
        "provider": "microsoft_graph",
        "product": "Microsoft Graph",
        "operation": "user.profile.read",
        "source_channel": "teams",
        "purpose": "Enrich authenticated Jason human identity with directory email",
        "outcome": "completed",
        "email_address": "al@teamaot.com",
    }

    serialized = str(dict(event.payload))
    assert "tenant-never-export" not in serialized
    assert "object-never-export" not in serialized
    assert "token-never-export" not in serialized
    assert "authorization-never-export" not in serialized
    assert "response-never-export" not in serialized
    assert "prompt-never-export" not in serialized


def test_directory_usage_audit_rejects_unknown_event_type(tmp_path):
    store = SQLiteOrchestrationEventStore(tmp_path / "events.sqlite3")
    audit = SQLiteMicrosoftDirectoryUsageAudit(store)
    evidence = TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        authentication_assurance="botframework-authenticated",
        conversation_id="conv-1",
        message_id="msg-1",
    )

    try:
        audit.record(
            "identity.directory.raw_provider_dump",
            principal_id="user-al",
            organization_id="aot",
            client_id=None,
            evidence=evidence,
            details={"access_token": "never"},
        )
    except ValueError as error:
        assert "unsupported Microsoft directory usage event type" in str(error)
    else:
        raise AssertionError("unknown directory audit event type must fail closed")
