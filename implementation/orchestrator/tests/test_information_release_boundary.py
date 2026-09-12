from __future__ import annotations

from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest, OrchestrationStatus
from orchestrator.information_authorization import (
    FailClosedInformationReleaseAuthorizer,
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
    InformationRemediation,
)
from orchestrator.service import CentralOrchestrator, InvocationResult


class _Resolution:
    def resolve(self, request):
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version=request.capability_version,
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
            reason_codes=("resolved",),
            eligible_provider_ids=("it_glue",),
            selected_provider_id="it_glue",
        )


class _Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class _Invoker:
    def __init__(self, authorization):
        self.authorization = authorization

    def invoke(self, *, request, resolution):
        return InvocationResult(
            output={"sensitive": "provider-value"},
            information_authorization=self.authorization,
        )


def _request() -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-release-boundary",
        correlation_id="corr-release-boundary",
        principal_id="person-al",
        organization_id="org-aot",
        client_id="client-aot",
        capability_name="documentation.document.read",
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
        principal_attributes={"email": "al@example.com"},
        authority_context_id="ctx-release-boundary",
    )


def _allowed_envelope() -> InformationAuthorizationEnvelope:
    return InformationAuthorizationEnvelope(
        handling_class=InformationHandlingClass.RELEASABLE,
        decisions={
            action: InformationAuthorizationDecision(
                action=action,
                allowed=True,
                reason_code=f"INFORMATION_{action.value.upper()}_ALLOWED",
                handling_class=InformationHandlingClass.RELEASABLE,
                policy_ids=("information-release-v1",),
                authorization_basis=("source_permission_verified",),
            )
            for action in InformationAction
        },
        source_provider="it_glue",
        source_resource_type="document",
        source_scope="client-aot",
    )


def _denied_envelope() -> InformationAuthorizationEnvelope:
    allowed = _allowed_envelope()
    decisions = dict(allowed.decisions)
    decisions[InformationAction.RELEASE] = InformationAuthorizationDecision(
        action=InformationAction.RELEASE,
        allowed=False,
        reason_code="SOURCE_ACCESS_NOT_ESTABLISHED",
        handling_class=InformationHandlingClass.RELEASABLE,
        remediation=InformationRemediation.REQUEST_ACCESS,
        policy_ids=("information-release-v1",),
        authorization_basis=("source_permission_unknown",),
    )
    return InformationAuthorizationEnvelope(
        handling_class=InformationHandlingClass.RELEASABLE,
        decisions=decisions,
        source_provider="it_glue",
        source_resource_type="document",
        source_scope="client-aot",
    )


def test_required_release_boundary_denies_missing_envelope_without_output() -> None:
    audit = _Audit()
    orchestrator = CentralOrchestrator(
        resolution=_Resolution(),
        invoker=_Invoker(None),
        audit=audit,
        information_release=FailClosedInformationReleaseAuthorizer(),
        require_information_release_authorization=True,
    )

    result = orchestrator.execute(_request())

    assert result.status is OrchestrationStatus.DENIED
    assert result.output == {}
    assert result.error_code == "INFORMATION_RELEASE_DENIED"
    assert "REQUEST_ACCESS" in result.reason_codes
    release_events = [payload for name, payload in audit.events if name == "orchestration.information_release.decided"]
    assert len(release_events) == 1
    assert release_events[0]["allowed"] is False
    assert release_events[0]["remediation"] == "request_access"
    assert "provider-value" not in repr(audit.events)


def test_required_release_boundary_allows_explicitly_authorized_output() -> None:
    audit = _Audit()
    orchestrator = CentralOrchestrator(
        resolution=_Resolution(),
        invoker=_Invoker(_allowed_envelope()),
        audit=audit,
        information_release=FailClosedInformationReleaseAuthorizer(),
        require_information_release_authorization=True,
    )

    result = orchestrator.execute(_request())

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert result.output == {"sensitive": "provider-value"}
    release_events = [payload for name, payload in audit.events if name == "orchestration.information_release.decided"]
    assert len(release_events) == 1
    assert release_events[0]["allowed"] is True
    assert release_events[0]["handling_class"] == "releasable"


def test_authorization_envelope_triggers_release_gate_without_global_switch() -> None:
    audit = _Audit()
    orchestrator = CentralOrchestrator(
        resolution=_Resolution(),
        invoker=_Invoker(_denied_envelope()),
        audit=audit,
    )

    result = orchestrator.execute(_request())

    assert result.status is OrchestrationStatus.DENIED
    assert result.output == {}
    assert result.error_code == "INFORMATION_RELEASE_DENIED"
    assert result.reason_codes == ("SOURCE_ACCESS_NOT_ESTABLISHED", "REQUEST_ACCESS")
    release_events = [payload for name, payload in audit.events if name == "orchestration.information_release.decided"]
    assert len(release_events) == 1
    assert release_events[0]["allowed"] is False
    assert release_events[0]["authorization_basis"] == ("source_permission_unknown",)
    assert "provider-value" not in repr(audit.events)


def test_legacy_invocation_without_envelope_is_unchanged_until_adapter_exists() -> None:
    audit = _Audit()
    orchestrator = CentralOrchestrator(
        resolution=_Resolution(),
        invoker=_Invoker(None),
        audit=audit,
    )

    result = orchestrator.execute(_request())

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert result.output == {"sensitive": "provider-value"}
    assert not [name for name, _ in audit.events if name == "orchestration.information_release.decided"]


def test_request_approval_is_distinct_from_request_access() -> None:
    envelope = _allowed_envelope()
    decisions = dict(envelope.decisions)
    decisions[InformationAction.RELEASE] = InformationAuthorizationDecision(
        action=InformationAction.RELEASE,
        allowed=False,
        reason_code="INFORMATION_RELEASE_APPROVAL_REQUIRED",
        handling_class=InformationHandlingClass.RELEASABLE,
        remediation=InformationRemediation.REQUEST_APPROVAL,
        policy_ids=("information-release-v1",),
        authorization_basis=("approval_required",),
    )
    envelope = InformationAuthorizationEnvelope(
        handling_class=InformationHandlingClass.RELEASABLE,
        decisions=decisions,
        source_provider="it_glue",
        source_resource_type="document",
        source_scope="client-aot",
    )
    orchestrator = CentralOrchestrator(
        resolution=_Resolution(),
        invoker=_Invoker(envelope),
        audit=_Audit(),
        information_release=FailClosedInformationReleaseAuthorizer(),
        require_information_release_authorization=True,
    )

    result = orchestrator.execute(_request())

    assert result.status is OrchestrationStatus.APPROVAL_REQUIRED
    assert result.output == {}
    assert "REQUEST_APPROVAL" in result.reason_codes
