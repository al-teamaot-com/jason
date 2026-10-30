"""Bounded AOT copier-document ingestion through Jason's governed SharePoint connector.

This is an integration adapter, not a Graph client or credential holder.
Only a separately authenticated organization-service context may read the
preapproved source file IDs; access is independently checked by the connector
and its exact-document release policy. A partial source refresh is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from connectors.core.contracts import ConnectorContext, ConnectorRequest, ConnectorResult

from .kfs_customer_document_evidence import (
    ApprovedCustomerEvidenceIndex,
    document_from_governed_sharepoint_reads,
)


@dataclass(frozen=True, slots=True)
class ApprovedAotCopierSource:
    tenant_id: str
    site_id: str
    drive_id: str
    item_id: str

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.site_id, self.drive_id, self.item_id):
            if not isinstance(value, str) or not value.strip() or value == "*":
                raise ValueError("copier document selectors must be exact and nonempty")


class GovernedDocumentReader(Protocol):
    def execute(self, request: ConnectorRequest) -> ConnectorResult: ...


@dataclass(frozen=True, slots=True)
class GovernedAotCopierSourceLoader:
    connector: GovernedDocumentReader
    principal_id: str
    sources: tuple[ApprovedAotCopierSource, ...]
    max_source_age_days: int = 400

    def __post_init__(self) -> None:
        if not self.principal_id or self.principal_id == "*":
            raise ValueError("trusted AOT workload principal required")
        if not 1 <= len(self.sources) <= 40:
            raise ValueError("between one and 40 explicitly approved sources required")
        if len({(s.tenant_id, s.drive_id, s.item_id) for s in self.sources}) != len(self.sources):
            raise ValueError("duplicate copier source selector")
        if len({s.tenant_id for s in self.sources}) != 1:
            raise ValueError("all approved copier sources must belong to the AOT tenant")
        if not 1 <= self.max_source_age_days <= 730:
            raise ValueError("unbounded source freshness is not approved")

    def _read(self, *, source: ApprovedAotCopierSource, operation: str) -> ConnectorResult:
        context = ConnectorContext(
            correlation_id=str(uuid4()),
            principal_id=self.principal_id,
            organization_id="aot",
            client_id=None,
            capability=operation,
            mode="observe",
            policy_ids=("aot-approved-copier-document-read",),
        )
        return self.connector.execute(ConnectorRequest(
            context=context,
            arguments={
                "site_id": source.site_id,
                "drive_id": source.drive_id,
                "item_id": source.item_id,
            },
        ))

    def refresh(self, *, now: datetime) -> ApprovedCustomerEvidenceIndex:
        """Load every exact approved document; never accept partial refresh output."""
        if now.tzinfo is None:
            raise ValueError("refresh timestamp must be timezone aware")
        docs = []
        for source in self.sources:
            before = self._read(source=source, operation="knowledge.document.metadata.read")
            content = self._read(source=source, operation="knowledge.document.content.read")
            after = self._read(source=source, operation="knowledge.document.metadata.read")
            docs.append(document_from_governed_sharepoint_reads(
                tenant_id=source.tenant_id,
                site_id=source.site_id,
                drive_id=source.drive_id,
                item_id=source.item_id,
                metadata_before=before,
                content_result=content,
                metadata_after=after,
            ))
        return ApprovedCustomerEvidenceIndex.from_documents(
            documents=tuple(docs),
            tenant_id=self.sources[0].tenant_id,
            allowed_site_ids=frozenset(source.site_id for source in self.sources),
            allowed_drive_ids=frozenset(source.drive_id for source in self.sources),
            now=now,
            max_source_age_days=self.max_source_age_days,
        )


@dataclass(frozen=True, slots=True)
class ApprovedAotCopierEvidenceSnapshot:
    """Preapproved refresh snapshot, consumed by reports without Graph calls."""

    index: ApprovedCustomerEvidenceIndex
    refreshed_at: datetime
    max_age_hours: int = 24
    authorization_expires_at: datetime | None = None

    def usable_at(self, now: datetime) -> ApprovedCustomerEvidenceIndex:
        if (
            now.tzinfo is None or self.refreshed_at.tzinfo is None
            or not 1 <= self.max_age_hours <= 168
            or (
                self.authorization_expires_at is not None
                and self.authorization_expires_at.tzinfo is None
            )
        ):
            raise ValueError("source snapshot timestamps and TTL must be valid")
        now_utc = now.astimezone(timezone.utc)
        if (
            self.authorization_expires_at is not None
            and now_utc >= self.authorization_expires_at.astimezone(timezone.utc)
        ):
            raise PermissionError("AOT document authorization has expired")
        age = now_utc - self.refreshed_at.astimezone(timezone.utc)
        from datetime import timedelta
        if not timedelta(0) <= age <= timedelta(hours=self.max_age_hours):
            raise PermissionError("AOT document evidence snapshot is absent or stale")
        return self.index


class GovernedAotCopierEvidenceCache:
    """Lazy, bounded evidence cache; a failed refresh never reuses stale identity.

    The loader is a governed service with exact document grants. The cache keeps
    parsed customer claims (not raw SharePoint bytes or access tokens) in
    process memory, and refreshes only when absent or expired.
    """

    def __init__(
        self, *, loader: GovernedAotCopierSourceLoader, max_age_hours: int = 24,
        authorization_expires_at: datetime | None = None,
    ) -> None:
        if not 1 <= max_age_hours <= 168:
            raise ValueError("copier evidence cache TTL must be between 1 and 168 hours")
        if authorization_expires_at is not None and authorization_expires_at.tzinfo is None:
            raise ValueError("copier document approval expiry must be timezone aware")
        self._loader = loader
        self._ttl = max_age_hours
        self._authorization_expires_at = authorization_expires_at
        self._snapshot: ApprovedAotCopierEvidenceSnapshot | None = None
        self._lock = RLock()

    def index_for_rank(self, now: datetime) -> ApprovedCustomerEvidenceIndex:
        if now.tzinfo is None:
            raise ValueError("authorized report time must be timezone aware")
        with self._lock:
            if (
                self._authorization_expires_at is not None
                and now.astimezone(timezone.utc) >= self._authorization_expires_at.astimezone(timezone.utc)
            ):
                self._snapshot = None
                raise PermissionError("AOT document authorization has expired")
            snapshot = self._snapshot
            if snapshot is not None:
                try:
                    return snapshot.usable_at(now)
                except PermissionError:
                    self._snapshot = None
            # Do not return a stale previous index if any approved file cannot
            # be read or fails the source-version/integrity checks.
            index = self._loader.refresh(now=now)
            self._snapshot = ApprovedAotCopierEvidenceSnapshot(
                index=index, refreshed_at=now, max_age_hours=self._ttl,
                authorization_expires_at=self._authorization_expires_at,
            )
            return index
