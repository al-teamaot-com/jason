from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from connectors.autotask.impersonating_connector import (
    AUTOTASK_AUTH_MODE_IMPERSONATED,
    AUTOTASK_AUTH_MODE_JASON_MANAGED,
    autotask_requester_authorization_mode,
)
from kernel.resolution import CapabilityResolutionResult

from .contracts import OrchestrationMode, OrchestrationRequest
from .information_authorization import (
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
)
from .information_sensitivity import assess_sensitive_evidence
from .provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
)
from .service import CapabilityInvoker, InvocationResult


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


# Retained only for the provider-native impersonation compatibility path. The
# temporary Jason-managed path derives its eligible reads from the registered
# Autotask provider catalog rather than from another per-resource allowlist.
_IMPERSONATED_CANONICAL_READS = frozenset(
    {
        SERVICE_COMPANY_READ,
        SERVICE_COMPANY_SEARCH,
        SERVICE_TICKET_READ,
        SERVICE_TICKET_SEARCH,
    }
)


def _authorized_autotask_envelope(
    *,
    capability_name: str,
    sensitive: bool,
    basis: tuple[str, ...],
) -> InformationAuthorizationEnvelope:
    handling = (
        InformationHandlingClass.DERIVED_OUTPUT_ONLY
        if sensitive
        else InformationHandlingClass.RELEASABLE
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
    return bindings.find_active_by_jason_identity(
        jason_identity_id=request.principal_id
    )


def _jason_managed_requester_authorization_proven(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
) -> bool:
    """Require the same positive identity/authority facts used before execution.

    This authorizer is called only after Central Orchestrator has validated the
    authority context and resolved an eligible provider. These checks deliberately
    duplicate the minimum release-critical facts so a service-account fetch never
    becomes requester release authority by implication.
    """

    return bool(
        request.authority_allowed
        and request.authority_context_id
        and request.permission_mode == "observe"
        and request.requester_kind == "human"
        and request.orchestration_mode is OrchestrationMode.EXECUTE
        and _active_trusted_binding(request=request, bindings=bindings) is not None
    )


@dataclass(frozen=True, slots=True)
class AutotaskImpersonationInformationAuthorizer:
    """Authorize Autotask information release using the configured requester mode.

    ``impersonated`` retains the provider-enforced compatibility path: only the
    canonical Company/Ticket operations whose connector requests carry Autotask's
    requester impersonation header may be upgraded from service-only release.

    Temporary ``jason_managed`` mode does not treat service-account fetch authority
    as requester authority. It upgrades only a capability from the registered
    Autotask read catalog after the authenticated human has an active trusted
    Microsoft/Jason binding, an allowed JKD-001 decision, an authority context that
    Central Orchestrator has validated, and observe-only execution. All other cases
    preserve the delegate's service-only fail-closed envelope.
    """

    delegate: CapabilityInvoker
    bindings: TrustedPrincipalBindingResolver | None = None

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        provider_id = (resolution.selected_provider_id or "").strip()
        mode = (
            autotask_requester_authorization_mode()
            if provider_id == AUTOTASK_PROVIDER
            else None
        )

        invocation = self.delegate.invoke(request=request, resolution=resolution)

        if provider_id != AUTOTASK_PROVIDER:
            return invocation

        if mode == AUTOTASK_AUTH_MODE_JASON_MANAGED:
            if (
                resolution.capability_name not in AUTOTASK_CAPABILITIES
                or not _jason_managed_requester_authorization_proven(
                    request=request,
                    bindings=self.bindings,
                )
            ):
                return invocation
            basis = (
                "jason_managed",
                "jkd001_authority_context",
                "trusted_microsoft_identity_binding",
                "central_orchestrator_governed_read",
            )
        elif mode == AUTOTASK_AUTH_MODE_IMPERSONATED:
            if (
                resolution.capability_name not in _IMPERSONATED_CANONICAL_READS
                or _active_trusted_binding(request=request, bindings=self.bindings)
                is None
            ):
                return invocation
            basis = (
                "impersonated",
                "autotask_impersonation_resource_id",
                "trusted_microsoft_identity_binding",
                "provider_enforced_resource_security",
            )
        else:  # pragma: no cover - validated by the shared mode resolver.
            return invocation

        sensitivity = assess_sensitive_evidence(invocation.output)
        authorization = _authorized_autotask_envelope(
            capability_name=resolution.capability_name,
            sensitive=sensitivity.sensitive,
            basis=basis,
        )
        return InvocationResult(
            output=invocation.output,
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=authorization,
        )
