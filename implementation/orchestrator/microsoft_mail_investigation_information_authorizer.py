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
    MICROSOFT_EXCHANGE_CAPABILITIES,
    MICROSOFT_EXCHANGE_PROVIDER,
    MICROSOFT_GRAPH_MAIL_INVESTIGATION_CAPABILITIES,
    MICROSOFT_GRAPH_PROVIDER,
    MICROSOFT_PURVIEW_CAPABILITIES,
    MICROSOFT_PURVIEW_PROVIDER,
)
from .service import CapabilityInvoker, InvocationResult


class TrustedPrincipalBindingResolver(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


def _requester_authorized(
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
        and request.client_id
        and request.permission_mode == "observe"
        and request.requester_kind == "human"
        and request.orchestration_mode is OrchestrationMode.EXECUTE
    )


@dataclass(frozen=True, slots=True)
class MicrosoftMailInvestigationInformationAuthorizer:
    """Authorize release of client mail-investigation evidence to an AOT technician.

    Microsoft application credentials provide fetch authority only. Release authority
    requires an authenticated AOT requester, a validated JKD-001 authority context,
    an explicit governed client, and observe-only execution. The provider connectors
    independently derive the Microsoft tenant from that client's validated boundary.
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
        capability = resolution.capability_name

        is_graph_investigation = (
            provider_id == MICROSOFT_GRAPH_PROVIDER
            and capability in MICROSOFT_GRAPH_MAIL_INVESTIGATION_CAPABILITIES
        )
        is_exchange_investigation = (
            provider_id == MICROSOFT_EXCHANGE_PROVIDER
            and capability in MICROSOFT_EXCHANGE_CAPABILITIES
        )
        is_purview_investigation = (
            provider_id == MICROSOFT_PURVIEW_PROVIDER
            and capability in MICROSOFT_PURVIEW_CAPABILITIES
        )
        if not (
            is_graph_investigation
            or is_exchange_investigation
            or is_purview_investigation
        ):
            return invocation
        if not _requester_authorized(request=request, bindings=self.bindings):
            return invocation

        sensitivity = assess_sensitive_evidence(invocation.output)
        handling = (
            InformationHandlingClass.DERIVED_OUTPUT_ONLY
            if sensitivity.sensitive
            else InformationHandlingClass.RELEASABLE
        )
        authorization = InformationAuthorizationEnvelope(
            handling_class=handling,
            decisions={
                action: InformationAuthorizationDecision(
                    action=action,
                    allowed=True,
                    reason_code=f"INFORMATION_{action.value.upper()}_ALLOWED",
                    handling_class=handling,
                    policy_ids=("provider-information-authorization-v1",),
                    authorization_basis=(
                        "mail_investigation_read",
                        "jkd001_authority_context",
                        "authenticated_aot_requester",
                        "governed_client_context",
                        "validated_microsoft_client_boundary",
                        "central_orchestrator_governed_read",
                    ),
                )
                for action in InformationAction
            },
            source_provider=provider_id,
            source_resource_type=capability,
        )
        return InvocationResult(
            output=invocation.output,
            artifact_references=invocation.artifact_references,
            attempts=invocation.attempts,
            telemetry=invocation.telemetry,
            information_authorization=authorization,
        )
