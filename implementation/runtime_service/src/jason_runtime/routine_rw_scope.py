"""Trusted per-client requester and provider boundary checks for routine RW.

Read-only adapters to existing JKD-001 identity/approval and ClientBoundary stores.
No approval records, identity grants, provider credentials or client mappings are
created in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext
from connectors.microsoft_graph.standard_user_create import (
    SOURCE_AUTHORITY, TrustedCloudUserScope,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository


class TrustedIdentityReader(Protocol):
    def get(self, identity_id: str): ...


class TrustedApprovalReader(Protocol):
    def get(self, approval_id: str): ...


def _require_human_aot(context: ConnectorContext, identities: TrustedIdentityReader) -> None:
    if (context.organization_id != "aot" or not context.client_id
            or not context.principal_id.strip()):
        raise ConnectorAuthorizationError("ROUTINE_RW_AOT_CLIENT_SCOPE_REQUIRED")
    identity = identities.get(context.principal_id)
    if (identity is None or identity.status != "active"
            or identity.organization_id != "aot"
            or identity.identity_type not in ("human", "person")):
        raise ConnectorAuthorizationError("ROUTINE_RW_ACTIVE_AOT_TECHNICIAN_REQUIRED")


@dataclass(frozen=True, slots=True)
class AotItGlueWriteScope:
    identities: TrustedIdentityReader
    boundaries: ClientBoundaryRepository

    def _validated(self, client_id: str):
        boundary = self.boundaries.find_active_for_client(
            client_id=client_id, provider="it_glue",
        )
        if (boundary is None or boundary.status != BoundaryStatus.VALIDATED
                or boundary.provider != "it_glue"
                or boundary.client_id != client_id
                or boundary.profile != "configuration-notes-v1"):
            raise ConnectorAuthorizationError("IT_GLUE_WRITE_BOUNDARY_NOT_VALIDATED")
        return boundary

    def require_authorized(self, context: ConnectorContext) -> None:
        _require_human_aot(context, self.identities)
        self._validated(context.client_id)

    def organization_id_for_client(self, *, client_id: str) -> int:
        boundary = self._validated(client_id)
        try:
            organization_id = int(boundary.external_tenant_id)
        except (TypeError, ValueError) as error:
            raise ConnectorAuthorizationError(
                "IT_GLUE_BOUNDARY_ORGANIZATION_INVALID"
            ) from error
        if organization_id <= 0:
            raise ConnectorAuthorizationError("IT_GLUE_BOUNDARY_ORGANIZATION_INVALID")
        return organization_id


@dataclass(frozen=True, slots=True)
class AotEntraOnboardingScope:
    """Use the existing exact JKD-001 approval, not a new approval framework."""

    identities: TrustedIdentityReader
    approvals: TrustedApprovalReader
    boundaries: ClientBoundaryRepository

    def require_approved_request(
        self, *, context: ConnectorContext, request_id: str,
    ) -> TrustedCloudUserScope:
        _require_human_aot(context, self.identities)
        approval = self.approvals.get(request_id)
        now = datetime.now(timezone.utc)
        if (approval is None or approval.status != "approved"
                or not str(approval.request_id or "").startswith("upn:")
                or approval.capability != "identity.user.create"
                or approval.organization_id != "aot"
                or approval.client_id != context.client_id
                or approval.requested_by != context.principal_id
                or not approval.decided_by
                or approval.expires_at is None or approval.expires_at <= now):
            raise ConnectorAuthorizationError("ENTRA_ONBOARDING_APPROVAL_NOT_VALID")
        read = self.boundaries.find_active_for_client(
            client_id=context.client_id, provider="microsoft_graph",
        )
        create = self.boundaries.find_active_for_client(
            client_id=context.client_id, provider="microsoft_graph_user_create",
        )
        if (read is None or create is None
                or read.status != BoundaryStatus.VALIDATED
                or create.status != BoundaryStatus.VALIDATED
                or read.profile != "directory-read"
                or create.profile != "user-create"
                or not create.primary_domain.strip()
                or not create.application_id.strip()
                or create.client_id != read.client_id
                or create.external_tenant_id.lower()
                   != read.external_tenant_id.lower()
                or "source:entra_cloud" not in create.external_scope_ids):
            raise ConnectorAuthorizationError("ENTRA_CLOUD_CREATE_BOUNDARY_NOT_VALIDATED")
        return TrustedCloudUserScope(
            client_id=context.client_id,
            tenant_id=create.external_tenant_id,
            managed_domains=frozenset({create.primary_domain.strip().casefold()}),
            source_authority=SOURCE_AUTHORITY,
            approved_user_principal_name=approval.request_id[4:].strip().casefold(),
        )
