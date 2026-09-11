from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.autotask_information_authorizer import AutotaskImpersonationInformationAuthorizer
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import (
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
    InformationRemediation,
)
from orchestrator.provider_read_capability_catalog import SERVICE_COMPANY_READ, SERVICE_TICKET_SEARCH
from orchestrator.service import InvocationResult


class _Delegate:
    def __init__(self, output):
        self.output = output

    def invoke(self, *, request, resolution):
        return InvocationResult(
            output=self.output,
            information_authorization=InformationAuthorizationEnvelope(
                handling_class=InformationHandlingClass.EXECUTION_ONLY,
                decisions={
                    InformationAction.FETCH: InformationAuthorizationDecision(
                        action=InformationAction.FETCH,
                        allowed=True,
                        reason_code="SERVICE_IDENTITY_FETCH_ALLOWED",
                        handling_class=InformationHandlingClass.EXECUTION_ONLY,
                        authorization_basis=("service_only",),
                    ),
                    **{
                        action: InformationAuthorizationDecision(
                            action=action,
                            allowed=False,
                            reason_code="SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED",
                            handling_class=InformationHandlingClass.EXECUTION_ONLY,
                            remediation=InformationRemediation.REQUEST_ACCESS,
                            authorization_basis=("service_only",),
                        )
                        for action in (
                            InformationAction.USE,
                            InformationAction.PROCESS,
                            InformationAction.RELEASE,
                        )
                    },
                },
                source_provider="autotask",
                source_resource_type=resolution.capability_name,
            ),
        )


class _Binding:
    email_address = "al@example.com"


class _Bindings:
    def __init__(self, value=_Binding()):
        self.value = value

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        return self.value if jason_identity_id == "person-al" else None


def _request(capability: str) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-autotask-info",
        correlation_id="corr-autotask-info",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name=capability,
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        authority_context_id="ctx-autotask-info",
    )


def _resolution(capability: str, provider: str = "autotask") -> CapabilityResolutionResult:
    return CapabilityResolutionResult(
        execution_id="exec-autotask-info",
        correlation_id="corr-autotask-info",
        capability_name=capability,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
        reason_codes=("resolved",),
        eligible_provider_ids=(provider,),
        selected_provider_id=provider,
    )


def test_supported_autotask_read_is_releasable_after_trusted_impersonated_execution() -> None:
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate({"provider": "autotask", "data": {"item": {"id": 2}}}),
        bindings=_Bindings(),
    ).invoke(
        request=_request(SERVICE_COMPANY_READ),
        resolution=_resolution(SERVICE_COMPANY_READ),
    )

    envelope = invocation.information_authorization
    assert envelope is not None
    assert envelope.handling_class is InformationHandlingClass.RELEASABLE
    assert all(envelope.require_allowed(action).allowed for action in InformationAction)
    assert "impersonated" in envelope.require_allowed(InformationAction.RELEASE).authorization_basis
    assert "provider_enforced_resource_security" in envelope.require_allowed(InformationAction.RELEASE).authorization_basis


def test_missing_trusted_binding_preserves_service_only_denial() -> None:
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate({"provider": "autotask", "data": {"items": []}}),
        bindings=_Bindings(None),
    ).invoke(
        request=_request(SERVICE_TICKET_SEARCH),
        resolution=_resolution(SERVICE_TICKET_SEARCH),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is False
    assert release.remediation is InformationRemediation.REQUEST_ACCESS


def test_unapproved_autotask_canonical_capability_stays_service_only() -> None:
    capability = "service.contact.read"
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate({"provider": "autotask", "data": {"item": {"id": 3}}}),
        bindings=_Bindings(),
    ).invoke(
        request=_request(capability),
        resolution=_resolution(capability),
    )

    assert invocation.information_authorization.require_allowed(InformationAction.RELEASE).allowed is False


def test_sensitive_impersonated_output_is_derived_only() -> None:
    invocation = AutotaskImpersonationInformationAuthorizer(
        delegate=_Delegate(
            {
                "provider": "autotask",
                "data": {"items": [{"title": "Credential", "password": "example-secret"}]},
            }
        ),
        bindings=_Bindings(),
    ).invoke(
        request=_request(SERVICE_TICKET_SEARCH),
        resolution=_resolution(SERVICE_TICKET_SEARCH),
    )

    assert invocation.information_authorization.handling_class is InformationHandlingClass.DERIVED_OUTPUT_ONLY
