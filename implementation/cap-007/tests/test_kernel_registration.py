from __future__ import annotations

from decimal import Decimal

from jason_cap_007.kernel_registration import (
    aws_ses_provider,
    email_send_capability,
    register_email_send,
)
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_policy import CostEstimator, DataHandlingPolicy, ExecutionBudget, ExecutionPolicyEngine, InMemoryPricingRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from kernel.resolution import CapabilityResolutionRequest, GovernedCapabilityResolutionEngine, ResolutionOutcome


def _engine():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_email_send(capabilities=capabilities, providers=providers)
    return GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=ExecutionPolicyEngine(cost_estimator=CostEstimator(InMemoryPricingRegistry())),
    )


def _request(*, approval_present: bool, allow_pilot_capability: bool, allow_pilot_provider: bool):
    return CapabilityResolutionRequest(
        execution_id="exec-email-1",
        correlation_id="corr-email-1",
        capability_name="communication.email.send",
        capability_version=None,
        tenant_id="aot",
        client_id=None,
        requested_mode="deterministic",
        authority_allowed=True,
        approval_present=approval_present,
        risk="high",
        data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0"), maximum_attempts=1),
        region=None,
        policy_ids=("cap-007-pilot",),
        allow_pilot_capability=allow_pilot_capability,
        allow_pilot_provider=allow_pilot_provider,
    )


def test_registration_records_are_pilot_and_provider_neutral():
    capability = email_send_capability()
    provider = aws_ses_provider()
    assert capability.capability_name == "communication.email.send"
    assert capability.metadata["roadmap_id"] == "CAP-007"
    assert capability.approval.required is True
    assert capability.idempotency_key_required is True
    assert provider.provider_id == "aws-ses"
    assert "communication.email.send" in provider.capabilities
    assert provider.metadata["secret_name"] == "aws_ses.sendmail"
    assert provider.metadata["automatic_fallback"] == "prohibited"


def test_pilot_capability_is_not_resolved_without_explicit_pilot_authority():
    result = _engine().resolve(_request(approval_present=True, allow_pilot_capability=False, allow_pilot_provider=False))
    assert result.outcome is ResolutionOutcome.UNRESOLVED


def test_pilot_requires_explicit_approval_before_provider_resolution():
    result = _engine().resolve(_request(approval_present=False, allow_pilot_capability=True, allow_pilot_provider=True))
    assert result.outcome is ResolutionOutcome.APPROVAL_REQUIRED
    assert result.reason_codes == ("capability_approval_required",)


def test_approved_pilot_resolves_only_to_aws_ses():
    result = _engine().resolve(_request(approval_present=True, allow_pilot_capability=True, allow_pilot_provider=True))
    assert result.outcome is ResolutionOutcome.RESOLVED
    assert result.selected_provider_id == "aws-ses"
    assert result.execution_plan is not None
    assert result.execution_plan.maximum_attempts == 1
    assert result.execution_plan.audit_required is True
