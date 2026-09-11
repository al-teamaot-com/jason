from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.governed_evidence_cache import (
    CacheAccessContext,
    EvidenceSource,
    FreshnessClass,
    GovernedEvidenceCache,
)


NOW = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


def context(*, principal="person-al", organization="aot", client="client-aot"):
    return CacheAccessContext(
        correlation_id="corr-cache-1",
        principal_id=principal,
        organization_id=organization,
        client_id=client,
    )


def source(*, version="v7", source_hash=None):
    return EvidenceSource(
        provider="it_glue",
        resource_type="document",
        external_id="doc-42",
        source_reference="itglue:document:42",
        source_version=version,
        source_hash=source_hash,
    )


def allow(entry, access):
    assert entry.organization_id == access.organization_id


def test_realtime_operational_telemetry_is_never_cached() -> None:
    audit = Audit()
    cache = GovernedEvidenceCache(audit=audit)
    result = cache.put(
        cache_key="drmm:device:1:online",
        context=context(),
        capability_name="managed_device.read",
        freshness=FreshnessClass.REALTIME,
        source=EvidenceSource(
            provider="datto_rmm",
            resource_type="device",
            external_id="device-1",
            source_reference="drmm:device:1",
        ),
        observed_at=NOW,
        provenance=("provider:datto_rmm",),
        data={"online": True, "logged_in_user": "someone"},
        cached_at=NOW,
    )

    assert result is None
    assert audit.events[-1][0] == "evidence_cache.bypass"


def test_static_document_requires_change_identity() -> None:
    cache = GovernedEvidenceCache()
    with pytest.raises(ValueError, match="source_version or source_hash"):
        cache.put(
            cache_key="itglue:doc:42",
            context=context(),
            capability_name="documentation.read",
            freshness=FreshnessClass.STATIC,
            source=source(version=None),
            observed_at=NOW,
            provenance=("provider:it_glue",),
            data={"policy": "approved"},
            cached_at=NOW,
        )


def test_static_document_hit_requires_fresh_authorization_and_version_match() -> None:
    calls = []
    cache = GovernedEvidenceCache()
    entry = cache.put(
        cache_key="itglue:doc:42",
        context=context(),
        capability_name="documentation.read",
        freshness=FreshnessClass.STATIC,
        source=source(version="v7"),
        observed_at=NOW,
        provenance=("provider:it_glue", "document-version:v7"),
        evidence_ids=("evidence-1",),
        data={"policy": "approved"},
        cached_at=NOW,
    )
    assert entry is not None

    def authorize(cached, access):
        calls.append((cached.cache_key, access.principal_id))

    hit = cache.get(
        cache_key="itglue:doc:42",
        context=context(principal="second-reader"),
        authorize=authorize,
        now=NOW + timedelta(days=30),
        current_source_version="v7",
    )

    assert hit is not None
    assert calls == [("itglue:doc:42", "second-reader")]
    assert hit.source.provider == "it_glue"
    assert hit.source.source_reference == "itglue:document:42"
    assert hit.source.source_version == "v7"
    assert hit.provenance == ("provider:it_glue", "document-version:v7")
    assert hit.evidence_ids == ("evidence-1",)


def test_static_document_invalidates_on_source_version_change() -> None:
    cache = GovernedEvidenceCache()
    cache.put(
        cache_key="itglue:doc:42",
        context=context(),
        capability_name="documentation.read",
        freshness=FreshnessClass.STATIC,
        source=source(version="v7"),
        observed_at=NOW,
        provenance=("provider:it_glue",),
        data={"policy": "approved"},
        cached_at=NOW,
    )

    assert cache.get(
        cache_key="itglue:doc:42",
        context=context(),
        authorize=allow,
        now=NOW + timedelta(days=1),
        current_source_version="v8",
    ) is None


def test_slow_change_cache_expires_by_freshness_policy() -> None:
    cache = GovernedEvidenceCache()
    cache.put(
        cache_key="autotask:contact:7",
        context=context(),
        capability_name="contact.read",
        freshness=FreshnessClass.SLOW_CHANGE,
        source=EvidenceSource(
            provider="autotask",
            resource_type="contact",
            external_id="7",
            source_reference="autotask:contact:7",
        ),
        observed_at=NOW,
        provenance=("provider:autotask",),
        data={"name": "Example"},
        cached_at=NOW,
    )

    assert cache.get(
        cache_key="autotask:contact:7",
        context=context(),
        authorize=allow,
        now=NOW + timedelta(hours=7),
    ) is None


def test_cache_hit_never_crosses_organization_scope() -> None:
    cache = GovernedEvidenceCache()
    cache.put(
        cache_key="itglue:doc:42",
        context=context(),
        capability_name="documentation.read",
        freshness=FreshnessClass.STATIC,
        source=source(),
        observed_at=NOW,
        provenance=("provider:it_glue",),
        data={"policy": "approved"},
        cached_at=NOW,
    )

    with pytest.raises(PermissionError, match="scope"):
        cache.get(
            cache_key="itglue:doc:42",
            context=context(organization="other-org", client="other-client"),
            authorize=lambda entry, access: None,
            now=NOW,
        )


def test_authorizer_can_revoke_access_to_existing_cache_entry() -> None:
    cache = GovernedEvidenceCache()
    cache.put(
        cache_key="itglue:doc:42",
        context=context(),
        capability_name="documentation.read",
        freshness=FreshnessClass.STATIC,
        source=source(),
        observed_at=NOW,
        provenance=("provider:it_glue",),
        data={"policy": "approved"},
        cached_at=NOW,
    )

    def deny(entry, access):
        del entry, access
        raise PermissionError("current authorization denied")

    with pytest.raises(PermissionError, match="current authorization denied"):
        cache.get(
            cache_key="itglue:doc:42",
            context=context(),
            authorize=deny,
            now=NOW,
        )
