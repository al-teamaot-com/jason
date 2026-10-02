from dataclasses import dataclass

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.microsoft_mail_investigation_information_authorizer import (
    MicrosoftMailInvestigationInformationAuthorizer,
)
from orchestrator.provider_read_capability_catalog import (
    COMMUNICATION_MAILBOX_FORWARDING_READ,
    COMMUNICATION_MAIL_INVESTIGATION_MESSAGE_SEARCH,
    MICROSOFT_EXCHANGE_PROVIDER,
    MICROSOFT_GRAPH_PROVIDER,
)
from orchestrator.service import InvocationResult


class Delegate:
    def invoke(self, *, request, resolution):
        return InvocationResult(
            output={"data": {"items": []}},
            attempts=1,
        )


class Bindings:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        return object() if jason_identity_id == "tech-1" else None


def request(capability, *, client_id="client-1", permission_mode="observe"):
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="tech-1",
        organization_id="aot",
        capability_name=capability,
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(),
        budget=ExecutionBudget(),
        client_id=client_id,
        requester_kind="human",
        permission_mode=permission_mode,
        authority_context_id="auth-1",
    )


def resolution(capability, provider):
    return CapabilityResolutionResult(
        capability_name=capability,
        capability_version="1.0",
        selected_provider_id=provider,
        selected_execution_mode="deterministic",
        candidate_provider_ids=(provider,),
        reason_codes=("TEST",),
    )


def test_graph_client_mail_evidence_is_releasable_for_authorized_tech():
    cap = COMMUNICATION_MAIL_INVESTIGATION_MESSAGE_SEARCH
    result = MicrosoftMailInvestigationInformationAuthorizer(
        delegate=Delegate(),
        bindings=Bindings(),
    ).invoke(
        request=request(cap),
        resolution=resolution(cap, MICROSOFT_GRAPH_PROVIDER),
    )
    assert result.information_authorization is not None
    assert all(
        decision.allowed
        for decision in result.information_authorization.decisions.values()
    )


def test_exchange_evidence_uses_same_client_scoped_release_gate():
    cap = COMMUNICATION_MAILBOX_FORWARDING_READ
    result = MicrosoftMailInvestigationInformationAuthorizer(
        delegate=Delegate(),
        bindings=Bindings(),
    ).invoke(
        request=request(cap),
        resolution=resolution(cap, MICROSOFT_EXCHANGE_PROVIDER),
    )
    assert result.information_authorization is not None
    assert all(
        decision.allowed
        for decision in result.information_authorization.decisions.values()
    )


def test_missing_client_context_does_not_upgrade_service_only_authority():
    cap = COMMUNICATION_MAIL_INVESTIGATION_MESSAGE_SEARCH
    result = MicrosoftMailInvestigationInformationAuthorizer(
        delegate=Delegate(),
        bindings=Bindings(),
    ).invoke(
        request=request(cap, client_id=None),
        resolution=resolution(cap, MICROSOFT_GRAPH_PROVIDER),
    )
    assert result.information_authorization is None


def test_execute_permission_mode_is_not_accepted_for_read_release():
    cap = COMMUNICATION_MAILBOX_FORWARDING_READ
    result = MicrosoftMailInvestigationInformationAuthorizer(
        delegate=Delegate(),
        bindings=Bindings(),
    ).invoke(
        request=request(cap, permission_mode="execute"),
        resolution=resolution(cap, MICROSOFT_EXCHANGE_PROVIDER),
    )
    assert result.information_authorization is None
