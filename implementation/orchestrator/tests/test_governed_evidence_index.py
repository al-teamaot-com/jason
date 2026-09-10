from datetime import datetime, timezone

import pytest

from orchestrator.governed_evidence_cache import (
    CacheAccessContext,
    EvidenceSource,
    FreshnessClass,
    GovernedEvidenceCache,
)
from orchestrator.governed_evidence_index import GovernedEvidenceIndex


NOW = datetime(2026, 9, 10, 16, 0, tzinfo=timezone.utc)


def context(*, principal="reader-a", organization="aot", client="client-a"):
    return CacheAccessContext(
        correlation_id="corr-index",
        principal_id=principal,
        organization_id=organization,
        client_id=client,
    )


def static_entry(cache, *, key="itglue:document:42", client="client-a"):
    entry = cache.put(
        cache_key=key,
        context=context(client=client),
        capability_name="documentation.document.read",
        freshness=FreshnessClass.STATIC,
        source=EvidenceSource(
            provider="it_glue",
            resource_type="document",
            external_id=key.rsplit(":", 1)[-1],
            source_reference=key,
            source_hash="sha256:document-v1",
        ),
        observed_at=NOW,
        provenance=("provider:it_glue", "source-hash:document-v1"),
        evidence_ids=("evidence-doc-42",),
        data={"title": "Remote Access Policy", "content": "MFA is required for remote access."},
        cached_at=NOW,
    )
    assert entry is not None
    return entry


def test_static_index_returns_authorized_policy_without_duplicating_content() -> None:
    cache = GovernedEvidenceCache()
    entry = static_entry(cache)
    index = GovernedEvidenceIndex(cache=cache)
    record = index.index_static_entry(
        entry=entry,
        searchable_text="Remote Access Policy MFA remote access",
    )

    assert not hasattr(record, "content")
    assert record.source_reference == "itglue:document:42"

    calls = []

    def authorize(cached, access):
        calls.append((cached.cache_key, access.principal_id))

    hits = index.search(
        query="remote access policy",
        context=context(principal="reader-b"),
        authorize=authorize,
    )

    assert len(hits) == 1
    assert hits[0].entry.data["title"] == "Remote Access Policy"
    assert calls == [("itglue:document:42", "reader-b")]


def test_static_index_never_crosses_client_scope() -> None:
    cache = GovernedEvidenceCache()
    entry = static_entry(cache, client="client-a")
    index = GovernedEvidenceIndex(cache=cache)
    index.index_static_entry(entry=entry, searchable_text="Remote Access Policy")

    assert index.search(
        query="remote access",
        context=context(client="client-b"),
        authorize=lambda entry, access: None,
    ) == ()


def test_static_index_honors_revoked_current_authorization() -> None:
    cache = GovernedEvidenceCache()
    entry = static_entry(cache)
    index = GovernedEvidenceIndex(cache=cache)
    index.index_static_entry(entry=entry, searchable_text="Remote Access Policy")

    def deny(entry, access):
        del entry, access
        raise PermissionError("current authorization denied")

    with pytest.raises(PermissionError, match="current authorization denied"):
        index.search(
            query="remote access",
            context=context(),
            authorize=deny,
        )


def test_nonstatic_evidence_cannot_enter_static_index() -> None:
    cache = GovernedEvidenceCache()
    entry = cache.put(
        cache_key="autotask:ticket:1",
        context=context(),
        capability_name="service.ticket.read",
        freshness=FreshnessClass.TRANSACTIONAL,
        source=EvidenceSource(
            provider="autotask",
            resource_type="ticket",
            external_id="1",
            source_reference="autotask:ticket:1",
        ),
        observed_at=NOW,
        provenance=("provider:autotask",),
        data={"title": "Remote access issue"},
        cached_at=NOW,
    )
    assert entry is not None
    index = GovernedEvidenceIndex(cache=cache)

    with pytest.raises(ValueError, match="only static"):
        index.index_static_entry(entry=entry, searchable_text="Remote access issue")
