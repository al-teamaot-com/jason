"""Exact, expiring, AOT-only document release grants for governed SharePoint reads.

Authorization is a separate input from Graph application consent. This policy
does not authenticate Microsoft or acquire credentials; it must be bound to a
validated Jason service principal before the provider is invoked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


DOCUMENT_READ_OPERATIONS = frozenset({
    "knowledge.document.metadata.read",
    "knowledge.document.content.read",
})


@dataclass(frozen=True, slots=True)
class ApprovedAotDocumentGrant:
    principal_id: str
    microsoft_tenant_id: str
    site_id: str
    drive_id: str
    item_id: str
    operations: frozenset[str]
    expires_at: datetime
    source_classification: str = "internal"

    def __post_init__(self) -> None:
        values = (
            self.principal_id, self.microsoft_tenant_id, self.site_id,
            self.drive_id, self.item_id,
        )
        if any(not isinstance(value, str) or not value.strip() or value == "*" for value in values):
            raise ValueError("document release grant requires exact identifiers")
        if (
            not self.operations or not self.operations.issubset(DOCUMENT_READ_OPERATIONS)
            or self.source_classification != "internal"
        ):
            raise ValueError("document release grant exceeds approved read scope")
        if self.expires_at.tzinfo is None:
            raise ValueError("document release expiry must be timezone aware")


@dataclass(frozen=True, slots=True)
class AotExactDocumentReleasePolicy:
    """No implicit tenant-wide document rights from the app's Sites.Read.All grant."""

    grants: frozenset[ApprovedAotDocumentGrant]
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def authorized(
        self,
        *,
        principal_id: str,
        organization_id: str,
        client_id: str | None,
        tenant_id: str,
        operation: str,
        site_id: str,
        drive_id: str | None,
        item_id: str | None,
    ) -> bool:
        if organization_id != "aot" or client_id is not None:
            return False
        if operation not in DOCUMENT_READ_OPERATIONS or not drive_id or not item_id:
            return False
        current = self.now()
        if current.tzinfo is None:
            raise ValueError("policy clock must be timezone aware")
        return any(
            grant.principal_id == principal_id
            and grant.microsoft_tenant_id == tenant_id
            and grant.site_id == site_id
            and grant.drive_id == drive_id
            and grant.item_id == item_id
            and operation in grant.operations
            and current <= grant.expires_at
            for grant in self.grants
        )
