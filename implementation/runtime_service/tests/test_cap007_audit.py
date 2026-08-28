from __future__ import annotations

from jason_runtime.cap007 import Cap007EventAudit
from orchestrator.event_store import SQLiteOrchestrationEventStore


def test_cap007_audit_adapter_persists_safe_orchestration_event(tmp_path):
    store = SQLiteOrchestrationEventStore(tmp_path / "events.sqlite3")
    audit = Cap007EventAudit(store)

    audit.append(
        "email.send.completed",
        {
            "execution_id": "exec-email-1",
            "correlation_id": "corr-email-1",
            "principal_id": "person-al",
            "organization_id": "aot",
            "client_id": None,
            "capability": "communication.email.send",
            "provider": "aws-ses",
            "sender": "jason@teamaot.com",
            "recipient_count": 1,
            "subject_sha256": "a" * 64,
            "message_id": "provider-message-1",
            "accepted": True,
        },
    )

    events = store.list_by_execution("exec-email-1")
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "email.send.completed"
    assert event.capability_name == "communication.email.send"
    assert event.stage == "completed"
    assert event.payload["provider"] == "aws-ses"
    assert event.payload["recipient_count"] == 1
    assert "recipient" not in event.payload
    assert "subject" not in event.payload
    assert "text_body" not in event.payload
    assert "html_body" not in event.payload
    assert "access_key_id" not in event.payload
    assert "secret_access_key" not in event.payload

    store.close()


def test_cap007_audit_adapter_maps_attempted_to_invoking(tmp_path):
    store = SQLiteOrchestrationEventStore(tmp_path / "events.sqlite3")
    audit = Cap007EventAudit(store)

    audit.append(
        "email.send.attempted",
        {
            "execution_id": "exec-email-2",
            "correlation_id": "corr-email-2",
            "principal_id": "person-al",
            "organization_id": "aot",
            "client_id": None,
            "capability": "communication.email.send",
            "provider": "aws-ses",
            "sender": "jason@teamaot.com",
            "recipient_count": 1,
            "subject_sha256": "b" * 64,
        },
    )

    event = store.list_by_execution("exec-email-2")[0]
    assert event.stage == "invoking"
    store.close()
