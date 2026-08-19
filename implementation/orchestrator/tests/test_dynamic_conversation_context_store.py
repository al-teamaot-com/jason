from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.dynamic_conversation_context_store import (
    SQLiteDynamicConversationContextStore,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    ConversationReferenceResolution,
    DynamicConversationContext,
)


NOW = datetime(2026, 8, 16, 13, 45, tzinfo=timezone.utc)


def sample_context() -> DynamicConversationContext:
    device = ConversationEntity(
        ref="device-1",
        kind="device",
        canonical_id="AOT-50107",
        display_name="AOT-50107",
        provenance="verified endpoint evidence",
    )
    person = ConversationEntity(
        ref="person-1",
        kind="person",
        canonical_id="person-arnold",
        display_name="Arnold Heath",
        provenance="verified identity evidence",
    )
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
        entities=(device, person),
        active_entity_refs={"device": device.ref, "person": person.ref},
        active_topic="security investigation",
        recent_resolutions=(
            ConversationReferenceResolution(
                mention="it",
                entity_ref=device.ref,
                basis="active device from prior verified turn",
            ),
        ),
    )


def test_context_round_trips_and_is_bound_to_identity(tmp_path):
    store = SQLiteDynamicConversationContextStore(
        tmp_path / "dynamic-context.sqlite3",
        ttl_seconds=3600,
    )
    original = sample_context()
    store.put(original, now=NOW)

    loaded = store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=5),
    )

    assert loaded == original
    assert store.get(
        organization_id="other-org",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=5),
    ) is None
    assert store.get(
        organization_id="aot",
        principal_id="other-person",
        conversation_id="conv-1",
        now=NOW + timedelta(minutes=5),
    ) is None


def test_context_expires_without_reuse(tmp_path):
    store = SQLiteDynamicConversationContextStore(
        tmp_path / "dynamic-context.sqlite3",
        ttl_seconds=3600,
    )
    store.put(sample_context(), now=NOW)

    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
        now=NOW + timedelta(hours=1, seconds=1),
    ) is None


def test_store_contains_context_not_provider_payloads(tmp_path):
    path = tmp_path / "dynamic-context.sqlite3"
    store = SQLiteDynamicConversationContextStore(path, ttl_seconds=3600)
    store.put(sample_context(), now=NOW)
    store.close()

    raw = path.read_bytes()
    assert b"AOT-50107" in raw
    assert b"verified endpoint evidence" in raw
    assert b"provider_payload" not in raw
    assert b"access_token" not in raw
