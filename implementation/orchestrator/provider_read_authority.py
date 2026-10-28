"""Governed standing authority matching for approved provider reads and
a narrowly opt-in subset of routine Autotask ticket writes.

This module does not authenticate users and does not grant authority by itself.

It interprets an explicitly persisted JKD-001 policy grant of the form:

    provider-read:<provider_id>

The grant is usable only when:
- the request is observe-only;
- the requested capability is registered;
- capability metadata explicitly marks it read_only=true;
- capability metadata explicitly marks it provider_neutral=true; and
- the named approved execution provider advertises that capability.

An independently opt-in AOT human technician ticket-write grant matches only
three active, MCP-enabled Autotask ticket capabilities with approved providers
and their established authenticated-imperative approval behavior. No direct
provider access, provider permissions, or autonomous write grants are added.

All identity, organization, client, permission ceiling, approval, effective-time,
status, audit, and execution-context controls remain inside JKD-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kernel.capabilities import CapabilityRegistryService
from kernel.capabilities.repository import CapabilityNotFoundError
from kernel.execution_providers import ExecutionProviderRegistryService
from kernel.execution_providers.repository import ProviderNotFoundError
from kernel.execution_providers.contracts import ProviderApproval, ProviderLifecycle, ProviderType
from kernel.identity_authority import AuthorityGrant, AuthorityRequest, IdentityRecord, PermissionMode


PROVIDER_READ_POLICY_PREFIX = "provider-read:"
AOT_TECHNICIAN_OPERATIONAL_READ_POLICY = "provider-read:aot-technician-operational-v1"

# Only existing Autotask service-ticket capabilities qualify for the first
# standing technician RW rollout. This is not a provider-wide permission.
AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY = (
    "routine-write:aot-technician-autotask-ticket-v1"
)
AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS = {
    "service.ticket.create": "autotask_ticket_create",
    "service.ticket.update": "autotask_ticket_update",
    "service.ticket.note.create": "autotask_internal_note",
}
AOT_ROUTINE_AUTOTASK_WRITE_CAPABILITIES = frozenset(
    AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS
)

# A remote PowerShell script is an endpoint execution operation, not a passive
# provider information read, even when AST validation says it is read-only.
# It retains its separate bounded technician execution authorization.
ACTIVE_EXECUTION_EXCLUSIONS = frozenset({"endpoint.powershell.read"})


class ActiveIdentityReader(Protocol):
    def get(self, identity_id: str) -> IdentityRecord | None: ...


@dataclass(frozen=True, slots=True)
class GovernedProviderReadAuthorityMatcher:
    capabilities: CapabilityRegistryService
    providers: ExecutionProviderRegistryService
    identities: ActiveIdentityReader | None = None
    routine_write_enabled: bool = False

    def matches(
        self,
        *,
        grant: AuthorityGrant,
        request: AuthorityRequest,
    ) -> bool:
        expression = grant.capability.strip()

        if expression == AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY:
            return self._matches_routine_autotask_write(grant=grant, request=request)

        if not expression.startswith(PROVIDER_READ_POLICY_PREFIX):
            return False

        provider_id = expression[len(PROVIDER_READ_POLICY_PREFIX):].strip()

        if not provider_id or request.requested_mode is not PermissionMode.OBSERVE:
            return False

        try:
            capability = self.capabilities.get_current(
                capability_name=request.capability
            )
        except CapabilityNotFoundError:
            return False

        if capability.metadata.get("read_only", "false").lower() != "true":
            return False
        if capability.metadata.get("provider_neutral", "false").lower() != "true":
            return False

        if expression == AOT_TECHNICIAN_OPERATIONAL_READ_POLICY:
            # AOT's standing technician-read policy follows newly registered
            # provider reads without another one-off grant. Human identity and
            # approved provider are proven; it never grants an execution mode,
            # raw credential access or arbitrary endpoint script execution.
            if (request.organization_id != "aot" or self.identities is None
                    or request.capability in ACTIVE_EXECUTION_EXCLUSIONS):
                return False
            principal = self.identities.get(request.principal_id)
            if (principal is None or principal.status != "active"
                    or principal.organization_id != "aot"
                    or principal.identity_type not in ("human", "person")):
                return False
            return any(
                request.capability in provider.capabilities
                and provider.provider_type is ProviderType.EXTERNAL_CONNECTOR
                and provider.lifecycle_status is ProviderLifecycle.AVAILABLE
                and provider.approval_status in (
                    ProviderApproval.APPROVED, ProviderApproval.PILOT
                )
                for provider in self.providers.list_all()
            )

        # Historical explicit per-provider grants are unaffected.
        try:
            provider = self.providers.get(provider_id)
        except ProviderNotFoundError:
            return False
        return request.capability in provider.capabilities

    def _matches_routine_autotask_write(
        self, *, grant: AuthorityGrant, request: AuthorityRequest,
    ) -> bool:
        """Standing AOT ticket writes, retaining exact JKD-001 approval checks.

        The MCP path interprets a direct authenticated imperative only for
        capabilities that explicitly declare that behavior. It still creates
        an exact, short-lived, auditable approval and binds the provider plan.
        No autonomous/service principal inherits this standing write grant.
        """
        if (
            not self.routine_write_enabled
            or request.organization_id != "aot"
            or request.client_id is not None
            or request.requested_mode is not PermissionMode.EXECUTE
            or request.capability not in AOT_ROUTINE_AUTOTASK_WRITE_CAPABILITIES
            or grant.subject_id != "organization:aot"
            or grant.organization_id != "aot"
            or grant.client_id is not None
            or grant.permission is not PermissionMode.EXECUTE
            or grant.approval_required is not True
            or self.identities is None
        ):
            return False

        principal = self.identities.get(request.principal_id)
        if (
            principal is None or principal.status != "active"
            or principal.organization_id != "aot"
            or principal.identity_type not in ("human", "person")
        ):
            return False
        try:
            capability = self.capabilities.get_current(
                capability_name=request.capability
            )
        except CapabilityNotFoundError:
            return False
        if (
            capability.lifecycle_status.value != "active"
            or capability.approval.required is not True
            or capability.metadata.get("write_capability") != "true"
            or capability.metadata.get("mcp_action_enabled") != "true"
            or capability.metadata.get(
                "conversation_authenticated_imperative_is_approval"
            ) != "true"
        ):
            return False
        return any(
            request.capability in provider.capabilities
            and provider.provider_type is ProviderType.EXTERNAL_CONNECTOR
            and provider.lifecycle_status is ProviderLifecycle.AVAILABLE
            and provider.approval_status in (
                ProviderApproval.APPROVED, ProviderApproval.PILOT
            )
            and provider.provider_id == AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS[
                request.capability
            ]
            for provider in self.providers.list_all()
        )
