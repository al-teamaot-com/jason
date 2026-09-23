from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Protocol

from .evidence_sanitization import sanitize_evidence_tree


class FreshnessClass(str, Enum):
    STATIC = "static"
    SLOW_CHANGE = "slow_change"
    TRANSACTIONAL = "transactional"
    REALTIME = "realtime"


_DEFAULT_MAX_AGE = {
    FreshnessClass.STATIC: None,
    FreshnessClass.SLOW_CHANGE: timedelta(hours=6),
    FreshnessClass.TRANSACTIONAL: timedelta(minutes=5),
    FreshnessClass.REALTIME: timedelta(seconds=0),
}


@dataclass(frozen=True, slots=True)
class CacheAccessContext:
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None

    def __post_init__(self) -> None:
        if not self.correlation_id.strip() or not self.principal_id.strip():
            raise ValueError("cache access requires correlation_id and principal_id")
        if not self.organization_id.strip():
            raise ValueError("cache access requires organization_id")


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    provider: str
    resource_type: str
    external_id: str
    source_reference: str
    source_version: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.provider,
            self.resource_type,
            self.external_id,
            self.source_reference,
        )
        if not all(value.strip() for value in required):
            raise ValueError("cache evidence source identity is incomplete")
        if self.source_version is not None and not self.source_version.strip():
            raise ValueError("source_version must be non-empty when provided")
        if self.source_hash is not None and not self.source_hash.strip():
            raise ValueError("source_hash must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class GovernedEvidenceCacheEntry:
    cache_key: str
    organization_id: str
    client_id: str | None
    capability_name: str
    freshness: FreshnessClass
    source: EvidenceSource
    observed_at: datetime
    cached_at: datetime
    provenance: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    payload_hash: str
    data: Any

    def __post_init__(self) -> None:
        if not self.cache_key.strip() or not self.organization_id.strip():
            raise ValueError("cache key and organization are required")
        if not self.capability_name.strip():
            raise ValueError("cache capability_name is required")
        if self.observed_at.tzinfo is None or self.cached_at.tzinfo is None:
            raise ValueError("cache timestamps must be timezone-aware")
        if not self.provenance or not all(item.strip() for item in self.provenance):
            raise ValueError("cache entry requires provenance")
        if self.freshness is FreshnessClass.STATIC:
            if self.source.source_version is None and self.source.source_hash is None:
                raise ValueError(
                    "static cache evidence requires source_version or source_hash for change-based invalidation"
                )


class CacheAuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


CacheAuthorizer = Callable[[GovernedEvidenceCacheEntry, CacheAccessContext], None]


class GovernedEvidenceCache:
    """Small provider-neutral cache that never weakens current authorization.

    Realtime evidence is deliberately never admitted. Cached evidence is sanitized
    before storage. Every lookup requires a current authorization callback and exact
    organization/client scope. Static evidence additionally requires provider source
    version/hash identity so it can be invalidated by source change rather than TTL.
    """

    def __init__(self, *, audit: CacheAuditSink | None = None) -> None:
        self._entries: dict[str, GovernedEvidenceCacheEntry] = {}
        self._audit = audit

    def put(
        self,
        *,
        cache_key: str,
        context: CacheAccessContext,
        capability_name: str,
        freshness: FreshnessClass,
        source: EvidenceSource,
        observed_at: datetime,
        provenance: tuple[str, ...],
        evidence_ids: tuple[str, ...] = (),
        data: Any,
        cached_at: datetime | None = None,
    ) -> GovernedEvidenceCacheEntry | None:
        if freshness is FreshnessClass.REALTIME:
            self._record(
                "evidence_cache.bypass",
                context=context,
                cache_key=cache_key,
                source=source,
                freshness=freshness,
                status="realtime_not_cacheable",
            )
            return None
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")

        sanitized = sanitize_evidence_tree(data)
        normalized_cached_at = (cached_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload_hash = _stable_hash(sanitized)
        entry = GovernedEvidenceCacheEntry(
            cache_key=cache_key,
            organization_id=context.organization_id,
            client_id=context.client_id,
            capability_name=capability_name,
            freshness=freshness,
            source=source,
            observed_at=observed_at.astimezone(timezone.utc),
            cached_at=normalized_cached_at,
            provenance=provenance,
            evidence_ids=evidence_ids,
            payload_hash=payload_hash,
            data=sanitized,
        )
        self._entries[cache_key] = entry
        self._record(
            "evidence_cache.stored",
            context=context,
            cache_key=cache_key,
            source=source,
            freshness=freshness,
            status="stored",
        )
        return entry

    def get(
        self,
        *,
        cache_key: str,
        context: CacheAccessContext,
        authorize: CacheAuthorizer,
        now: datetime | None = None,
        current_source_version: str | None = None,
        current_source_hash: str | None = None,
    ) -> GovernedEvidenceCacheEntry | None:
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if entry.organization_id != context.organization_id or entry.client_id != context.client_id:
            self._record(
                "evidence_cache.denied",
                context=context,
                cache_key=cache_key,
                source=entry.source,
                freshness=entry.freshness,
                status="scope_mismatch",
            )
            raise PermissionError("cache entry is outside current organization/client scope")

        # Authorization is always current-user/current-context. A prior authorized
        # population never authorizes a later reader.
        authorize(entry, context)

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        maximum_age = _DEFAULT_MAX_AGE[entry.freshness]
        if maximum_age is not None and current - entry.cached_at > maximum_age:
            self._record(
                "evidence_cache.miss",
                context=context,
                cache_key=cache_key,
                source=entry.source,
                freshness=entry.freshness,
                status="stale",
            )
            return None

        if current_source_version is not None:
            if entry.source.source_version != current_source_version:
                self._record(
                    "evidence_cache.miss",
                    context=context,
                    cache_key=cache_key,
                    source=entry.source,
                    freshness=entry.freshness,
                    status="source_version_changed",
                )
                return None
        if current_source_hash is not None:
            if entry.source.source_hash != current_source_hash:
                self._record(
                    "evidence_cache.miss",
                    context=context,
                    cache_key=cache_key,
                    source=entry.source,
                    freshness=entry.freshness,
                    status="source_hash_changed",
                )
                return None

        self._record(
            "evidence_cache.hit",
            context=context,
            cache_key=cache_key,
            source=entry.source,
            freshness=entry.freshness,
            status="hit",
        )
        return entry

    def invalidate(self, cache_key: str) -> None:
        self._entries.pop(cache_key, None)

    def _record(
        self,
        event_type: str,
        *,
        context: CacheAccessContext,
        cache_key: str,
        source: EvidenceSource,
        freshness: FreshnessClass,
        status: str,
    ) -> None:
        if self._audit is None:
            return
        self._audit.append(
            event_type,
            {
                "correlation_id": context.correlation_id,
                "principal_id": context.principal_id,
                "organization_id": context.organization_id,
                "client_id": context.client_id,
                "cache_key": cache_key,
                "provider": source.provider,
                "resource_type": source.resource_type,
                "external_id": source.external_id,
                "source_reference": source.source_reference,
                "source_version": source.source_version,
                "source_hash": source.source_hash,
                "freshness": freshness.value,
                "status": status,
            },
        )


def _stable_hash(data: Any) -> str:
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
