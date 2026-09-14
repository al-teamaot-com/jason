from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import InformationAction
from orchestrator.microsoft_graph_information_authorizer import (
    MicrosoftGraphInformationAuthorizer,
)
from orchestrator.provider_read_capability_catalog import (
    IDENTITY_USER_READ,
    IDENTITY_USER_SEARCH,
    MICROSOFT_GRAPH_PROVIDER,
)
from orchestrator.service import InvocationResult


class Delegate:
    def __init__(self, output):
        self.output = output

    def invoke(self, *, request, resolution):
        return InvocationResult(output=self.output)


class Binding:
    status = "active"


class Bindings:
    def __init__(self, value=Binding()):
        self.value = value

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        return self.value if jason_identity_id == "person-al" else None


def request(capability: str, *, authority_allowed=True, authority_context_id="ctx-entra"):
    return OrchestrationRequest(
        execution_id="exec-entra",
        correlation_id="corr-entra",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name=capability,
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=authority_allowed,
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
        requester_kind="human",
        permission_mode="observe",
        authority_context_id=authority_context_id,
    )


def resolution(capability: str):
    return CapabilityResolutionResult(
        execution_id="exec-entra",
        correlation_id="corr-entra",
        capability_name=capability,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
        reason_codes=("resolved",),
        eligible_provider_ids=(MICROSOFT_GRAPH_PROVIDER,),
        selected_provider_id=MICROSOFT_GRAPH_PROVIDER,
    )


def test_bound_authorized_human_can_receive_governed_entra_user_search():
    invocation = MicrosoftGraphInformationAuthorizer(
        delegate=Delegate(
            {
                "provider": MICROSOFT_GRAPH_PROVIDER,
                "data": {"items": [{"id": "object-1", "displayName": "Example User"}]},
            }
        ),
        bindings=Bindings(),
    ).invoke(
        request=request(IDENTITY_USER_SEARCH),
        resolution=resolution(IDENTITY_USER_SEARCH),
    )

    release = invocation.information_authorization.require_allowed(InformationAction.RELEASE)
    assert release.allowed is True
    assert "trusted_microsoft_identity_binding" in release.authorization_basis
    assert "validated_microsoft_tenant_boundary" in release.authorization_basis
    assert "central_orchestrator_governed_read" in release.authorization_basis


def test_missing_binding_preserves_delegate_service_only_authorization():
    base = InvocationResult(output={"provider": MICROSOFT_GRAPH_PROVIDER, "data": {"item": {}}})

    class ServiceOnlyDelegate:
        def invoke(self, *, request, resolution):
            return base

    invocation = MicrosoftGraphInformationAuthorizer(
        delegate=ServiceOnlyDelegate(),
        bindings=Bindings(None),
    ).invoke(
        request=request(IDENTITY_USER_READ),
        resolution=resolution(IDENTITY_USER_READ),
    )

    assert invocation.information_authorization is None


def test_missing_positive_authority_context_does_not_upgrade_release():
    invocation = MicrosoftGraphInformationAuthorizer(
        delegate=Delegate({"provider": MICROSOFT_GRAPH_PROVIDER, "data": {"items": []}}),
        bindings=Bindings(),
    ).invoke(
        request=request(IDENTITY_USER_SEARCH, authority_allowed=False),
        resolution=resolution(IDENTITY_USER_SEARCH),
    )

    assert invocation.information_authorization is None

    invocation = MicrosoftGraphInformationAuthorizer(
        delegate=Delegate({"provider": MICROSOFT_GRAPH_PROVIDER, "data": {"items": []}}),
        bindings=Bindings(),
    ).invoke(
        request=request(IDENTITY_USER_SEARCH, authority_context_id=None),
        resolution=resolution(IDENTITY_USER_SEARCH),
    )

    assert invocation.information_authorization is None
