from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationRequest
from .information_authorization import (
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
)
from .information_sensitivity import assess_sensitive_evidence
from .provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
)
from .service import CapabilityInvoker, InvocationResult


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


_IMPERSONATED_CANONICAL_READS = frozenset(
    {
        SERVICE_COMPANY_READ,
        SERVICE_COMPANY_SEARCH,
        SERVICE_TICKET_READ,
        SERVICE_TICKET_SEARCH,
    }
)


def _authorized_impersonated_envelope(
    *,
    capability_name: str,
    sensitive: bool,
) -> InformationAuthorizationEnvelope:
    handling = (
        InformationHandlingClass.DERIVED_OUTPUT_ONLY
        if sensitive
        else InformationHandlingClass.RELEASABLE
    )
    basis = (
        "impersonated",
        "autotask_impersonation_resource_id",
        "trusted_microsoft_identity_binding",
        "provider_enforced_resource_security",
    )
    return InformationAuthorizationEnvelope(
        handling_class=handling,
        decisions={
            action: InformationAuthorizationDecision(
                action=action,
                allowed=True,
                reason_code=f"INFORMATION_{action.value.upper()}_ALLOWED",
                handling_class=handling,
                policy_ids=("provider-information-authorization-v1",),
                authorization_basis=basis,
            )
            for action in InformationAction
        },
        source_provider=AUTOTASK_PROVIDER,
        source_resource_type=capability_name,
    )


def _active_trusted_binding(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
):
    if bindings is None:
        return None
    binding = bindings.find_active_by_jason_identity(
        jason_identity_id=request.principal_id
    )
    if binding is None:
        return None
    email = str(getattr(binding, "email_address", "") or "").strip()
    if not email:
        return None
    return binding


@dataclass(frozen=True, slots=True)
class AutotaskImpersonationInformationAuthorizer:
    """Upgrade only proven Autotask impersonated reads from service-only release.

    The delegate performs normal provider information authorization first. This
    wrapper can replace that service-only envelope only for the small canonical set
    whose connector operations are configured to apply Autotask requester
    impersonation. Successful return from the connector means Autotask accepted the
    impersonated request; missing/ambiguous trusted identity fails closed because no
    upgrade occurs.
    """

    delegate: CapabilityInvoker
    bindings: TrustedPrincipalBindingResolver | None = None

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        invocation = self.delegate.invoke(request=request, resolution=resolution)

        if (
            (resolution.selected_provider_id or "").strip() != AUTOTASK_PROVIDER
            or resolution.capability_name not in _IMPERSONATED_CANONICAL_READS
            or _active_trusted_binding(request=request, bindings=self.bindings) is None
        ):
            return invocation

        sensitivity = assess_sensitive_evidence(invocation.output)
        authorization = _authorized_impersonated_envelope(
            capability_name=resolution.capability_name,
            sensitive=sensitivity.sensitive,
        )
        return InvocationResult(
            output=invocation.output,
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=authorization,
        )
