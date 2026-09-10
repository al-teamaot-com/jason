from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from .governed_evidence_cache import (
    CacheAccessContext,
    GovernedEvidenceCache,
    GovernedEvidenceCacheEntry,
)


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{1,127}")


def _term_hash(term: str) -> str:
    normalized = term.strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        _term_hash(match.group(0))
        for match in _TOKEN.finditer(text)
        if len(match.group(0)) >= 2
    )


@dataclass(frozen=True, slots=True)
class EvidenceIndexRecord:
    cache_key: str
    organization_id: str
    client_id: str | None
    provider: str
    resource_type: str
    external_id: str
    source_reference: str
    term_hashes: frozenset[str]


@dataclass(frozen=True, slots=True)
class EvidenceIndexHit:
    entry: GovernedEvidenceCacheEntry
    matched_terms: int


CacheAuthorizer = Callable[[GovernedEvidenceCacheEntry, CacheAccessContext], None]


class GovernedEvidenceIndex:
    """Provider-neutral searchable pointers into the governed evidence cache.

    The index stores scope, source identity, cache keys, and hashed normalized terms.
    It deliberately does not duplicate document bodies. A search result is returned
    only after the underlying cache entry passes exact current organization/client
    scope and the caller-supplied current authorization callback.
    """

    def __init__(self, *, cache: GovernedEvidenceCache) -> None:
        self._cache = cache
        self._records: dict[str, EvidenceIndexRecord] = {}

    def index_static_entry(
        self,
        *,
        entry: GovernedEvidenceCacheEntry,
        searchable_text: str,
    ) -> EvidenceIndexRecord:
        if entry.freshness.value != "static":
            raise ValueError("only static governed evidence may enter the static evidence index")
        if not searchable_text.strip():
            raise ValueError("searchable_text must be non-empty")
        record = EvidenceIndexRecord(
            cache_key=entry.cache_key,
            organization_id=entry.organization_id,
            client_id=entry.client_id,
            provider=entry.source.provider,
            resource_type=entry.source.resource_type,
            external_id=entry.source.external_id,
            source_reference=entry.source.source_reference,
            term_hashes=_terms(searchable_text),
        )
        self._records[entry.cache_key] = record
        return record

    def remove(self, cache_key: str) -> None:
        self._records.pop(cache_key, None)

    def search(
        self,
        *,
        query: str,
        context: CacheAccessContext,
        authorize: CacheAuthorizer,
        maximum_results: int = 10,
    ) -> tuple[EvidenceIndexHit, ...]:
        query_terms = _terms(query)
        if not query_terms:
            return ()
        if not 1 <= maximum_results <= 50:
            raise ValueError("maximum_results must be between 1 and 50")

        candidates = []
        for record in self._records.values():
            if record.organization_id != context.organization_id:
                continue
            if record.client_id != context.client_id:
                continue
            overlap = len(query_terms & record.term_hashes)
            if overlap:
                candidates.append((overlap, record.cache_key))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        hits: list[EvidenceIndexHit] = []
        for overlap, cache_key in candidates:
            entry = self._cache.get(
                cache_key=cache_key,
                context=context,
                authorize=authorize,
            )
            if entry is None:
                continue
            hits.append(EvidenceIndexHit(entry=entry, matched_terms=overlap))
            if len(hits) >= maximum_results:
                break
        return tuple(hits)
