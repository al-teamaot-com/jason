"""Governed Microsoft Teams identity binding for conversational ingress.

The transport supplies authenticated Microsoft tenant/object evidence. This adapter
maps that evidence to an existing Jason identity record; it does not create identity,
authority, organization, or client scope from transport claims.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Protocol

from connectors.core.contracts import ConnectorTransportError
from kernel.identity_authority import IdentityRecord

from .event_store import SQLiteOrchestrationEventStore
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    TeamsConversationPrincipalEvidence,
)


class IdentityRecordReader(Protocol):
    def get(self, identity_id: str) -> IdentityRecord | None: ...


class MicrosoftUserDirectoryReader(Protocol):
    """Resolve mutable Microsoft profile attributes from authenticated object identity."""

    def resolve_email(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> str | None: ...


class MicrosoftDirectoryUsageAudit(Protocol):
    """Record external directory consumption after Jason identity is established."""

    def record(
        self,
        event_type: str,
        *,
        principal_id: str,
        organization_id: str,
        client_id: str | None,
        evidence: TeamsConversationPrincipalEvidence,
        details: Mapping[str, object] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class SQLiteMicrosoftDirectoryUsageAudit:
    """Append safe Microsoft Graph usage events to Jason's orchestration audit store.

    The audit event contains the stable Jason principal and transport message scope,
    but never the Graph access token, Microsoft object ID, tenant ID, provider response,
    or user prompt. The `requested` event is written before Graph is called, so an API
    request remains observable even if completion logging or the provider later fails.
    """

    events: SQLiteOrchestrationEventStore

    def record(
        self,
        event_type: str,
        *,
        principal_id: str,
        organization_id: str,
        client_id: str | None,
        evidence: TeamsConversationPrincipalEvidence,
        details: Mapping[str, object] | None = None,
    ) -> None:
        stages = {
            "identity.directory.requested": "invoking",
            "identity.directory.completed": "completed",
            "identity.directory.failed": "failed",
        }
        if event_type not in stages:
            raise ValueError("unsupported Microsoft directory usage event type")

        # Only explicitly approved accounting fields can cross into durable audit.
        # Callers cannot smuggle arbitrary provider payload, tokens, or transport
        # evidence into the orchestration event store through `details`.
        supplied = dict(details or {})
        safe_details: dict[str, object] = {
            "provider": "microsoft_graph",
            "product": "Microsoft Graph",
            "operation": "user.profile.read",
            "source_channel": "teams",
            "purpose": "Enrich authenticated Jason human identity with directory email",
        }
        if "outcome" in supplied:
            safe_details["outcome"] = str(supplied["outcome"])[:80]
        if "exception_type" in supplied:
            safe_details["exception_type"] = str(supplied["exception_type"])[:120]
        email = str(supplied.get("email_address") or "").strip()
        if email and _valid_email(email):
            safe_details["email_address"] = email

        self.events.append(
            event_type,
            {
                "execution_id": f"directory:{evidence.message_id}",
                "correlation_id": f"teams-directory:{evidence.conversation_id}:{evidence.message_id}",
                "organization_id": organization_id,
                "principal_id": principal_id,
                "capability_name": "identity.profile.enrich",
                "stage": stages[event_type],
                "client_id": client_id,
                "requester_kind": "human",
                "permission_mode": "observe",
                "request_id": evidence.message_id,
                "details": safe_details,
            },
        )


@lru_cache(maxsize=4)
def _environment_directory_audit(path: str) -> SQLiteMicrosoftDirectoryUsageAudit:
    """Reuse one append-only audit connection per configured runtime event store."""

    return SQLiteMicrosoftDirectoryUsageAudit(
        SQLiteOrchestrationEventStore(path)
    )


def _default_directory_audit() -> MicrosoftDirectoryUsageAudit | None:
    """Enable durable directory accounting when the runtime event DB is configured.

    Unit/library callers that do not configure a runtime event store keep the historical
    no-audit behavior. Production Jason already supplies JASON_ORCHESTRATION_EVENTS_DB.
    """

    path = os.getenv("JASON_ORCHESTRATION_EVENTS_DB", "").strip()
    if not path:
        return None
    return _environment_directory_audit(path)


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
            if not _valid_email(email):
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
    """Bind authenticated Teams evidence to pre-existing Jason identity authority.

    The authoritative binding is the authenticated Microsoft tenant/object pair mapped
    to an active Jason identity record. Microsoft Graph directory data is optional
    mutable profile enrichment only; a transport outage or provider throttle may remove
    that enrichment from the turn, but it must not invalidate an already verified Jason
    identity binding. Semantic/authorization failures returned by the directory itself
    remain fail-closed.
    """

    bindings: MicrosoftIdentityBindingReader
    identities: IdentityRecordReader
    directory: MicrosoftUserDirectoryReader | None = None
    directory_audit: MicrosoftDirectoryUsageAudit | None = None
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

        email_address = binding.email_address
        if self.directory is not None:
            audit = self.directory_audit or _default_directory_audit()
            if audit is not None:
                # Fail before provider execution if the required usage audit cannot be
                # written. Jason should not knowingly consume an external API invisibly.
                audit.record(
                    "identity.directory.requested",
                    principal_id=identity.identity_id,
                    organization_id=identity.organization_id,
                    client_id=binding.client_id,
                    evidence=evidence,
                )
            try:
                email_address = self.directory.resolve_email(
                    microsoft_tenant_id=evidence.microsoft_tenant_id,
                    microsoft_object_id=evidence.microsoft_object_id,
                )
            except ConnectorTransportError as error:
                if audit is not None:
                    audit.record(
                        "identity.directory.failed",
                        principal_id=identity.identity_id,
                        organization_id=identity.organization_id,
                        client_id=binding.client_id,
                        evidence=evidence,
                        details={
                            "outcome": "transport_failed",
                            "exception_type": type(error).__name__,
                        },
                    )
                # Directory email is enrichment, not identity authority. Do not fall
                # back to potentially stale cached profile data when live enrichment
                # is unavailable; omit the mutable attribute and continue with the
                # already authenticated and Jason-bound principal.
                email_address = None
            except Exception as error:
                if audit is not None:
                    audit.record(
                        "identity.directory.failed",
                        principal_id=identity.identity_id,
                        organization_id=identity.organization_id,
                        client_id=binding.client_id,
                        evidence=evidence,
                        details={
                            "outcome": "failed",
                            "exception_type": type(error).__name__,
                        },
                    )
                raise
            else:
                if email_address is not None:
                    email_address = email_address.strip()
                    if not _valid_email(email_address):
                        if audit is not None:
                            audit.record(
                                "identity.directory.failed",
                                principal_id=identity.identity_id,
                                organization_id=identity.organization_id,
                                client_id=binding.client_id,
                                evidence=evidence,
                                details={
                                    "outcome": "invalid_profile",
                                    "exception_type": "ValueError",
                                },
                            )
                        raise ValueError("Microsoft directory returned an invalid email address")
                if audit is not None:
                    audit.record(
                        "identity.directory.completed",
                        principal_id=identity.identity_id,
                        organization_id=identity.organization_id,
                        client_id=binding.client_id,
                        evidence=evidence,
                        details={
                            "outcome": "completed",
                            "email_address": email_address or "",
                        },
                    )

        return BoundConversationPrincipal(
            principal_id=identity.identity_id,
            organization_id=identity.organization_id,
            client_id=binding.client_id,
            email_address=email_address,
        )


def _valid_email(value: str) -> bool:
    return bool(value and "@" in value and not value.startswith("@") and not value.endswith("@"))
