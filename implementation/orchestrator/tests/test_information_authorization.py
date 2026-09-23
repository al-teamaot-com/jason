from __future__ import annotations

from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.information_authorization import (
    FailClosedInformationReleaseAuthorizer,
    InformationAction,
    InformationAuthorizationDecision,
    InformationAuthorizationEnvelope,
    InformationHandlingClass,
    InformationRemediation,
)


class _Resolution:
    capability_name = "documentation.document.read"
    selected_provider_id = "it_glue"


def _request() -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-info-auth",
        correlation_id="corr-info-auth",
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
        arguments={"resource_id": "opaque-test-resource"},
        permission_mode="observe",
        authority_context_id="ctx-info-auth",
    )


def _decision(
    action: InformationAction,
    *,
    allowed: bool = True,
    handling_class: InformationHandlingClass = InformationHandlingClass.RELEASABLE,
    remediation: InformationRemediation = InformationRemediation.NONE,
) -> InformationAuthorizationDecision:
    return InformationAuthorizationDecision(
        action=action,
        allowed=allowed,
        reason_code=(
            f"INFORMATION_{action.value.upper()}_ALLOWED"
            if allowed
            else f"INFORMATION_{action.value.upper()}_DENIED"
        ),
        handling_class=handling_class,
        remediation=remediation,
        policy_ids=("policy-info-release-v1",),
        authorization_basis=("provider_permission_verified", "jason_policy_verified"),
    )


def _envelope(
    handling_class: InformationHandlingClass = InformationHandlingClass.RELEASABLE,
) -> InformationAuthorizationEnvelope:
    return InformationAuthorizationEnvelope(
        handling_class=handling_class,
        decisions={
            action: _decision(action, handling_class=handling_class)
            for action in InformationAction
        },
        source_provider="it_glue",
        source_resource_type="document",
        source_scope="client-aot",
    )


def test_missing_authorization_envelope_fails_closed_without_output() -> None:
    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=_request(),
        resolution=_Resolution(),
        output={"secret": "must-never-be-released"},
        authorization=None,
    )

    assert decision.allowed is False
    assert decision.output == {}
    assert decision.reason_code == "INFORMATION_AUTHORIZATION_REQUIRED"
    assert decision.remediation is InformationRemediation.REQUEST_ACCESS


def test_missing_release_decision_fails_closed() -> None:
    envelope = _envelope()
    envelope = InformationAuthorizationEnvelope(
        handling_class=envelope.handling_class,
        decisions={
            action: decision
            for action, decision in envelope.decisions.items()
            if action is not InformationAction.RELEASE
        },
        source_provider=envelope.source_provider,
        source_resource_type=envelope.source_resource_type,
        source_scope=envelope.source_scope,
    )

    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=_request(),
        resolution=_Resolution(),
        output={"value": "restricted"},
        authorization=envelope,
    )

    assert decision.allowed is False
    assert decision.output == {}
    assert decision.reason_code == "INFORMATION_RELEASE_AUTHORIZATION_UNKNOWN"
    assert decision.remediation is InformationRemediation.REQUEST_ACCESS


def test_explicit_provider_release_denial_cannot_be_overridden_by_request_approval() -> None:
    request = _request()
    request = OrchestrationRequest(
        **{
            field: getattr(request, field)
            for field in request.__dataclass_fields__
            if field != "approval_present"
        },
        approval_present=True,
    )
    envelope = _envelope()
    decisions = dict(envelope.decisions)
    decisions[InformationAction.RELEASE] = _decision(
        InformationAction.RELEASE,
        allowed=False,
        remediation=InformationRemediation.REQUEST_ACCESS,
    )
    envelope = InformationAuthorizationEnvelope(
        handling_class=envelope.handling_class,
        decisions=decisions,
        source_provider=envelope.source_provider,
        source_resource_type=envelope.source_resource_type,
        source_scope=envelope.source_scope,
    )

    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=request,
        resolution=_Resolution(),
        output={"value": "restricted"},
        authorization=envelope,
    )

    assert decision.allowed is False
    assert decision.output == {}
    assert decision.remediation is InformationRemediation.REQUEST_ACCESS


@pytest.mark.parametrize(
    "handling_class",
    [
        InformationHandlingClass.EXECUTION_ONLY,
        InformationHandlingClass.REASONING_ALLOWED_NON_RELEASABLE,
    ],
)
def test_non_releasable_classes_never_return_raw_output(handling_class) -> None:
    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=_request(),
        resolution=_Resolution(),
        output={"credential": "never-return"},
        authorization=_envelope(handling_class),
    )

    assert decision.allowed is False
    assert decision.output == {}
    assert decision.reason_code == "INFORMATION_CLASS_NOT_RELEASABLE"
    assert decision.remediation is InformationRemediation.REQUEST_APPROVAL


def test_derived_output_only_requires_explicit_transformation() -> None:
    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=_request(),
        resolution=_Resolution(),
        output={"raw_financial_records": [1, 2, 3]},
        authorization=_envelope(InformationHandlingClass.DERIVED_OUTPUT_ONLY),
    )

    assert decision.allowed is False
    assert decision.output == {}
    assert decision.reason_code == "DERIVED_OUTPUT_TRANSFORMATION_REQUIRED"
    assert decision.remediation is InformationRemediation.REQUEST_APPROVAL


def test_explicit_fetch_use_process_release_authorization_returns_output() -> None:
    output = {"safe_fact": "printer configured by IP"}
    decision = FailClosedInformationReleaseAuthorizer().authorize_release(
        request=_request(),
        resolution=_Resolution(),
        output=output,
        authorization=_envelope(),
    )

    assert decision.allowed is True
    assert decision.output == output
    assert decision.remediation is InformationRemediation.NONE
    assert decision.policy_ids == ("policy-info-release-v1",)
    assert decision.authorization_basis == (
        "provider_permission_verified",
        "jason_policy_verified",
    )


def test_denied_decision_must_offer_recoverable_path() -> None:
    with pytest.raises(ValueError, match="remediation"):
        InformationAuthorizationDecision(
            action=InformationAction.RELEASE,
            allowed=False,
            reason_code="DENY",
            handling_class=InformationHandlingClass.RELEASABLE,
        )
