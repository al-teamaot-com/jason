"""Governed provider-read authority matching.

This module does not authenticate users and does not grant authority by itself.

It interprets an explicitly persisted JKD-001 policy grant of the form:

    provider-read:<provider_id>

The grant is usable only when:
- the request is observe-only;
- the requested capability is registered;
- capability metadata explicitly marks it read_only=true;
- capability metadata explicitly marks it provider_neutral=true; and
- the named approved execution provider advertises that capability.

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

    def matches(
        self,
        *,
        grant: AuthorityGrant,
        request: AuthorityRequest,
    ) -> bool:
        expression = grant.capability.strip()

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
