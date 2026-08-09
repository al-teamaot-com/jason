"""Authenticated Microsoft Teams approval ingress boundary.

This module does not validate JWT cryptography itself. It consumes claims only
from an upstream token verifier that has already validated signature, issuer,
audience, lifetime, and tenant. It then binds Microsoft identity and tenant to
Jason organization/identity records before producing provider-neutral approval
responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from connectors.src.jason_connectors.approval_requests import ApprovalResponse

from .teams_approval_channel import parse_teams_response


@dataclass(frozen=True, slots=True)
class VerifiedMicrosoftPrincipal:
    tenant_id: str
    object_id: str
    subject: str
    audience: str
    issuer: str
    authentication_assurance: str

    def validate(self) -> None:
        for name, value in {
            "tenant_id": self.tenant_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "audience": self.audience,
            "issuer": self.issuer,
            "authentication_assurance": self.authentication_assurance,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


class MicrosoftTenantBindingResolver(Protocol):
    def organization_for_tenant(self, tenant_id: str) -> str | None: ...


class MicrosoftIdentityBindingResolver(Protocol):
    def jason_identity_for_object(
        self,
        *,
        tenant_id: str,
        object_id: str,
        organization_id: str,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class TeamsApprovalIngress:
    tenant_bindings: MicrosoftTenantBindingResolver
    identity_bindings: MicrosoftIdentityBindingResolver

    def accept_verified_interaction(
        self,
        *,
        principal: VerifiedMicrosoftPrincipal,
        payload: Mapping[str, str],
        decided_at: datetime,
    ) -> ApprovalResponse:
        principal.validate()
        organization_id = self.tenant_bindings.organization_for_tenant(principal.tenant_id)
        if organization_id is None:
            raise PermissionError("Microsoft tenant is not bound to a Jason organization")

        payload_organization = payload.get("organization_id", "").strip()
        if not payload_organization:
            raise PermissionError("approval payload organization is required")
        if payload_organization != organization_id:
            raise PermissionError("approval payload organization does not match authenticated tenant")

        identity_id = self.identity_bindings.jason_identity_for_object(
            tenant_id=principal.tenant_id,
            object_id=principal.object_id,
            organization_id=organization_id,
        )
        if identity_id is None:
            raise PermissionError("authenticated Microsoft principal is not bound to a Jason identity")

        response = parse_teams_response(
            payload,
            authenticated_identity_id=identity_id,
            decided_at=decided_at,
        )
        if response.organization_id != organization_id:
            raise PermissionError("translated approval response escaped authenticated tenant scope")
        return response


@dataclass
class InMemoryMicrosoftTenantBindings:
    records: dict[str, str]

    def organization_for_tenant(self, tenant_id: str) -> str | None:
        return self.records.get(tenant_id)


@dataclass
class InMemoryMicrosoftIdentityBindings:
    records: dict[tuple[str, str, str], str]

    def jason_identity_for_object(
        self,
        *,
        tenant_id: str,
        object_id: str,
        organization_id: str,
    ) -> str | None:
        return self.records.get((tenant_id, object_id, organization_id))
