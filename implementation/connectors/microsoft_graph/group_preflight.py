"""Read-only preflight for a prospective Microsoft 365 group-write pilot.

This verifies already-authorized tenant mappings, application identities,
token tenancy, and basic Graph group/user READ access without issuing writes.
It does not claim that Graph write permissions have been consented or tested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorTransportError, HttpTransport
from .group_executor import MicrosoftGroupBoundaryValidator, GroupWriteScope
from .token import GRAPH_DEFAULT_SCOPE, MicrosoftApplicationTokenProvider
from .group_reader import canonical_uuid


@dataclass(frozen=True, slots=True)
class GroupTenantPreflightResult:
    client_id: str
    tenant_id: str
    read_identity_verified: bool
    write_identity_verified: bool
    group_read_verified: bool
    user_read_verified: bool
    write_permission_grant_verified: bool = False
    live_mutation_permitted: bool = False


@dataclass(frozen=True, slots=True)
class MicrosoftGroupTenantPreflight:
    boundaries: MicrosoftGroupBoundaryValidator
    read_tokens: MicrosoftApplicationTokenProvider
    write_tokens: MicrosoftApplicationTokenProvider
    read_transport: HttpTransport

    @staticmethod
    def _validate_token(token, *, scope: GroupWriteScope, application_id: str) -> str:
        try:
            matches = (
                canonical_uuid(token.tenant_id) == scope.tenant_id
                and canonical_uuid(token.application_id) == application_id
                and token.scope == GRAPH_DEFAULT_SCOPE
                and token.token_type.lower() == "bearer"
                and bool(token.access_token)
            )
        except (ValueError, AttributeError):
            matches = False
        if not matches:
            raise ConnectorAuthorizationError("M365_GROUP_PREFLIGHT_TOKEN_SCOPE_MISMATCH")
        return token.access_token

    def inspect(self, *, client_id: str, correlation_id: str) -> GroupTenantPreflightResult:
        if not correlation_id or not isinstance(correlation_id, str):
            raise ValueError("Correlation ID required for tenant preflight")
        scope = self.boundaries.require_scope(client_id=client_id)
        read_token = self._validate_token(
            self.read_tokens.acquire_for_client(
                client_id=scope.client_id, correlation_id=correlation_id),
            scope=scope, application_id=scope.read_application_id,
        )
        self._validate_token(
            self.write_tokens.acquire_for_client(
                client_id=scope.client_id, correlation_id=correlation_id),
            scope=scope, application_id=scope.write_application_id,
        )

        for collection in ("groups", "users"):
            result = self.read_transport.request(
                method="GET", url="https://graph.microsoft.com/v1.0/" + collection,
                headers={"Authorization": "Bearer " + read_token},
                params={"$select": "id", "$top": 1},
                timeout_seconds=20.0,
            )
            if not isinstance(result, Mapping) or not isinstance(result.get("value"), list):
                raise ConnectorTransportError("Microsoft group preflight read response invalid")
        return GroupTenantPreflightResult(
            client_id=scope.client_id, tenant_id=scope.tenant_id,
            read_identity_verified=True, write_identity_verified=True,
            group_read_verified=True, user_read_verified=True,
        )
