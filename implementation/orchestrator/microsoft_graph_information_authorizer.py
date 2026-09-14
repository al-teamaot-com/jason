from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
    MICROSOFT_GRAPH_CAPABILITIES,
    MICROSOFT_GRAPH_PROVIDER,
)
from .service import CapabilityInvoker, InvocationResult


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


def _trusted_requester_proven(
    *,
    request: OrchestrationRequest,
    bindings: TrustedPrincipalBindingResolver | None,
) -> bool:
    if bindings is None:
        return False
    binding = bindings.find_active_by_jason_identity(
        jason_identity_id=request.principal_id
    )
    return bool(
        binding is not None
        and request.authority_allowed
        and request.authority_context_id
        and request.permission_mode == "observe"
        and request.requester_kind == "human"
        and request.orchestration_mode is OrchestrationMode.EXECUTE
    )


def _authorized_envelope(
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
        "jkd001_authority_context",
        "trusted_microsoft_identity_binding",
        "validated_microsoft_tenant_boundary",
        "central_orchestrator_governed_read",
        "microsoft_graph_directory_read",
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
        source_provider=MICROSOFT_GRAPH_PROVIDER,
        source_resource_type=capability_name,
    )


@dataclass(frozen=True, slots=True)
class MicrosoftGraphInformationAuthorizer:
    """Release Microsoft Entra user evidence only to the governed requester.

    Provider application credentials establish fetch authority only. Release additionally
    requires the already-authenticated human to have a unique trusted Microsoft/Jason
    binding, an allowed JKD-001 authority context, and observe-only execution. The
    connector separately derives the target tenant from that binding and a validated
    Microsoft client boundary.
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
        provider_id = (resolution.selected_provider_id or "").strip()
        if provider_id != MICROSOFT_GRAPH_PROVIDER:
            return invocation
        if (
            resolution.capability_name not in MICROSOFT_GRAPH_CAPABILITIES
            or not _trusted_requester_proven(request=request, bindings=self.bindings)
        ):
            return invocation

        sensitivity = assess_sensitive_evidence(invocation.output)
        return InvocationResult(
            output=invocation.output,
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=_authorized_envelope(
                capability_name=resolution.capability_name,
                sensitive=sensitivity.sensitive,
            ),
        )
