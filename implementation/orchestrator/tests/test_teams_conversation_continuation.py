from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.teams_conversation_continuation import (
    SQLiteTeamsConversationContinuationStore,
)


NOW = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


def test_continuation_is_bound_to_org_principal_and_conversation(tmp_path):
    store = SQLiteTeamsConversationContinuationStore(
        tmp_path / "continuation.sqlite3",
        ttl_seconds=1200,
    )
    store.put(
        principal_id="person-al",
        organization_id="aot",
        conversation_id="conv-1",
        last_message_id="message-1",
        response_kind="result",
        last_response_text="AOT-50107 — bitlocker status: Encrypted. Source: datto_rmm.",
        last_capability_name="endpoint.device.search",
        requested_facts=("bitlocker status",),
        resource_selector={"hostname": "AOT-50107"},
        now=NOW,
    )

    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=1),
    ) is not None
    assert store.get(
        organization_id="other-org",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=1),
    ) is None
    assert store.get(
        organization_id="aot",
        principal_id="other-person",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=1),
    ) is None
    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="other-conv",
        now=NOW + timedelta(minutes=1),
    ) is None


def test_continuation_expires_without_reuse(tmp_path):
    store = SQLiteTeamsConversationContinuationStore(
        tmp_path / "continuation.sqlite3",
        ttl_seconds=1200,
    )
    store.put(
        principal_id="person-al",
        organization_id="aot",
        conversation_id="conv-1",
        last_message_id="message-1",
        response_kind="guidance",
        last_response_text="No provider request was made.",
        last_capability_name=None,
        requested_facts=("bitlocker recovery key",),
        resource_selector={"hostname": "AOT-50107"},
        now=NOW,
    )

    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=21),
    ) is None
