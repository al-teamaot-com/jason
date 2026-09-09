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

from kernel.capabilities import CapabilityRegistryService
from kernel.capabilities.repository import CapabilityNotFoundError
from kernel.execution_providers import ExecutionProviderRegistryService
from kernel.execution_providers.repository import ProviderNotFoundError
from kernel.identity_authority import AuthorityGrant, AuthorityRequest, PermissionMode


PROVIDER_READ_POLICY_PREFIX = "provider-read:"


@dataclass(frozen=True, slots=True)
class GovernedProviderReadAuthorityMatcher:
    capabilities: CapabilityRegistryService
    providers: ExecutionProviderRegistryService

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

        if not provider_id:
            return False

        if request.requested_mode is not PermissionMode.OBSERVE:
            return False

        try:
            capability = self.capabilities.get_current(
                capability_name=request.capability
            )
            provider = self.providers.get(provider_id)
        except (CapabilityNotFoundError, ProviderNotFoundError):
            return False

        if capability.metadata.get("read_only", "false").lower() != "true":
            return False

        if capability.metadata.get("provider_neutral", "false").lower() != "true":
            return False

        if request.capability not in provider.capabilities:
            return False

        return True
