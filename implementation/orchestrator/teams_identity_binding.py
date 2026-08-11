"""Governed Microsoft Teams identity binding for conversational ingress.

The transport supplies authenticated Microsoft tenant/object evidence. This adapter
maps that evidence to an existing Jason identity record; it does not create identity,
authority, organization, or client scope from transport claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kernel.identity_authority import IdentityRecord

from .teams_conversation_flow import (
    BoundConversationPrincipal,
    TeamsConversationPrincipalEvidence,
)


class IdentityRecordReader(Protocol):
    def get(self, identity_id: str) -> IdentityRecord | None: ...


@dataclass(frozen=True, slots=True)
class MicrosoftIdentityBinding:
    microsoft_tenant_id: str
    microsoft_object_id: str
    jason_identity_id: str
    client_id: str | None = None
    email_address: str | None = None
    status: str = "active"

    def __post_init__(self) -> None:
        required = {
            "microsoft_tenant_id": self.microsoft_tenant_id,
            "microsoft_object_id": self.microsoft_object_id,
            "jason_identity_id": self.jason_identity_id,
            "status": self.status,
        }
        missing = sorted(name for name, value in required.items() if not value.strip())
        if missing:
            raise ValueError("Microsoft identity binding fields are empty: " + ", ".join(missing))
        if self.client_id is not None and not self.client_id.strip():
            raise ValueError("client_id must be non-empty when supplied")
        if self.email_address is not None:
            email = self.email_address.strip()
            if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
                raise ValueError("email_address must be a valid non-empty address when supplied")


class MicrosoftIdentityBindingReader(Protocol):
    def find(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> MicrosoftIdentityBinding | None: ...


@dataclass(frozen=True, slots=True)
class JasonTeamsIdentityBinder:
    """Bind authenticated Teams evidence to pre-existing Jason identity authority."""

    bindings: MicrosoftIdentityBindingReader
    identities: IdentityRecordReader
    required_authentication_assurance: str = "botframework-authenticated"

    def bind(
        self,
        evidence: TeamsConversationPrincipalEvidence,
    ) -> BoundConversationPrincipal | None:
        if evidence.authentication_assurance != self.required_authentication_assurance:
            return None

        binding = self.bindings.find(
            microsoft_tenant_id=evidence.microsoft_tenant_id,
            microsoft_object_id=evidence.microsoft_object_id,
        )
        if binding is None or binding.status != "active":
            return None

        identity = self.identities.get(binding.jason_identity_id)
        if identity is None or identity.status != "active":
            return None

        return BoundConversationPrincipal(
            principal_id=identity.identity_id,
            organization_id=identity.organization_id,
            client_id=binding.client_id,
            email_address=binding.email_address,
        )
