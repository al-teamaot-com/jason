from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)
from kernel.execution_policy import (
    CostEstimator,
    DataHandlingPolicy,
    DecisionOutcome,
    ExecutionBudget,
    ExecutionMode,
    ExecutionPolicyEngine,
    InMemoryPricingRegistry,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.resolution import (
    CapabilityResolutionRequest,
    CapabilityResolutionStatus,
    GovernedCapabilityResolutionEngine,
    ResolutionOutcome,
)


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def capability(
    *,
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.ACTIVE,
    approval_required: bool = False,
    client_isolation_required: bool = True,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name="governance.action.evaluate",
        version="1.0",
        display_name="Evaluate Governed Action",
        lifecycle_status=lifecycle,
        business_purpose="Evaluate governed execution requests.",
        owner_service="Jason Governance Engine",
        architectural_capability_ids=frozenset({"JAC-006"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://input/1.0",
        output_schema_reference="schema://output/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=approval_required,
            approver_classes=(
                ("service-manager",)
                if approval_required
                else ()
            ),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("request facts",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed.",
        tenant_isolation_required=True,
        client_isolation_required=client_isolation_required,
        stewardship=CapabilityStewardship(
            steward="architecture-authority",
            business_justification="Required for governed execution.",
            review_interval_days=90,
            retirement_criteria=("Replaced by approved equivalent.",),
        ),
        created_at=NOW,
    )


def provider(
    *,
    provider_id: str = "deterministic-primary",
    approval: ProviderApproval = ProviderApproval.APPROVED,
    health: ProviderHealth = ProviderHealth.HEALTHY,
) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=provider_id,
        display_name="Deterministic Provider",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=health,
        approval_status=approval,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"governance.action.evaluate"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset({"us-east"}),
        limits=ProviderLimits(
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(
            structured_output=True,
        ),
        pricing_profile_id="deterministic-zero-cost",
        stewardship=ProviderStewardship(
            technology_steward="architecture-authority",
            business_justification="Required deterministic provider.",
            review_interval_days=90,
            last_reviewed_at=NOW,
            retirement_criteria=("Replaced by approved equivalent.",),
        ),
        created_at=NOW,
    )


def request(
    *,
    capability_version: str | None = None,
    client_id: str | None = "client-1",
    authority_allowed: bool = True,
    approval_present: bool = True,
    allow_pilot_capability: bool = False,
    allow_pilot_provider: bool = False,
) -> CapabilityResolutionRequest:
    return CapabilityResolutionRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="governance.action.evaluate",
        capability_version=capability_version,
        tenant_id="tenant-1",
        client_id=client_id,
        requested_mode="deterministic",
        authority_allowed=authority_allowed,
        approval_present=approval_present,
        risk="high",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        region="us-east",
        policy_ids=("policy-1",),
        allow_pilot_capability=allow_pilot_capability,
        allow_pilot_provider=allow_pilot_provider,
    )


def engine(
    *,
    registered_capability: CapabilityDefinition | None = None,
    registered_provider: ExecutionProvider | None = None,
) -> GovernedCapabilityResolutionEngine:
    capability_service = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    provider_service = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    if registered_capability is not None:
        capability_service.register(registered_capability)

    if registered_provider is not None:
        provider_service.register(registered_provider)

    policy = ExecutionPolicyEngine(
        cost_estimator=CostEstimator(
            InMemoryPricingRegistry()
        )
    )

    return GovernedCapabilityResolutionEngine(
        capabilities=capability_service,
        providers=provider_service,
        policy=policy,
    )


def test_unknown_capability_fails_closed() -> None:
    result = engine().resolve(request())

    assert result.outcome is ResolutionOutcome.UNRESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.NOT_FOUND
    )
    assert result.reason_codes == ("capability_not_found",)
    assert result.execution_plan is None


def test_exact_version_resolves_successfully() -> None:
    result = engine(
        registered_capability=capability(),
        registered_provider=provider(),
    ).resolve(
        request(capability_version="1.0")
    )

    assert result.outcome is ResolutionOutcome.RESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.RESOLVED_EXACT
    )
    assert result.capability_version == "1.0"
    assert result.selected_provider_id == "deterministic-primary"
    assert result.execution_plan is not None


def test_current_version_resolves_successfully() -> None:
    result = engine(
        registered_capability=capability(),
        registered_provider=provider(),
    ).resolve(request())

    assert result.outcome is ResolutionOutcome.RESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.RESOLVED_CURRENT
    )
    assert result.execution_plan is not None


def test_inactive_capability_does_not_resolve() -> None:
    result = engine(
        registered_capability=capability(
            lifecycle=CapabilityLifecycle.BUILDING
        ),
        registered_provider=provider(),
    ).resolve(
        request(capability_version="1.0")
    )

    assert result.outcome is ResolutionOutcome.UNRESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.INELIGIBLE_LIFECYCLE
    )
    assert result.execution_plan is None


def test_missing_client_context_fails_closed() -> None:
    result = engine(
        registered_capability=capability(),
        registered_provider=provider(),
    ).resolve(
        request(client_id=None)
    )

    assert result.outcome is ResolutionOutcome.UNRESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.ISOLATION_CONTEXT_MISSING
    )
    assert result.reason_codes == ("client_context_required",)
    assert result.execution_plan is None


def test_required_capability_approval_remains_explicit() -> None:
    result = engine(
        registered_capability=capability(
            approval_required=True
        ),
        registered_provider=provider(),
    ).resolve(
        request(approval_present=False)
    )

    assert result.outcome is ResolutionOutcome.APPROVAL_REQUIRED
    assert result.reason_codes == (
        "capability_approval_required",
    )
    assert result.execution_plan is None


def test_no_eligible_provider_fails_closed() -> None:
    result = engine(
        registered_capability=capability(),
    ).resolve(request())

    assert result.outcome is ResolutionOutcome.UNRESOLVED
    assert result.reason_codes == ("no_eligible_provider",)
    assert result.execution_plan is None


def test_policy_denial_remains_authoritative() -> None:
    result = engine(
        registered_capability=capability(),
        registered_provider=provider(),
    ).resolve(
        request(authority_allowed=False)
    )

    assert result.outcome is ResolutionOutcome.DENIED
    assert result.execution_decision is not None
    assert (
        result.execution_decision.outcome
        is DecisionOutcome.DENIED
    )
    assert result.reason_codes == ("authority_denied",)
    assert result.execution_plan is None


def test_provider_ordering_is_deterministic() -> None:
    capability_service = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    provider_service = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    capability_service.register(capability())
    provider_service.register(
        provider(provider_id="provider-z")
    )
    provider_service.register(
        provider(provider_id="provider-a")
    )

    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capability_service,
        providers=provider_service,
        policy=ExecutionPolicyEngine(
            cost_estimator=CostEstimator(
                InMemoryPricingRegistry()
            )
        ),
    )

    result = resolution.resolve(request())

    assert result.eligible_provider_ids == (
        "provider-a",
        "provider-z",
    )
    assert result.selected_provider_id == "provider-a"
    assert (
        result.execution_plan.execution_mode
        is ExecutionMode.DETERMINISTIC
    )


def test_prohibited_execution_mode_fails_closed() -> None:
    record = capability()
    record = CapabilityDefinition(
        capability_name=record.capability_name,
        version=record.version,
        display_name=record.display_name,
        lifecycle_status=record.lifecycle_status,
        business_purpose=record.business_purpose,
        owner_service=record.owner_service,
        architectural_capability_ids=(
            record.architectural_capability_ids
        ),
        risk_level=record.risk_level,
        data_classifications=record.data_classifications,
        permitted_execution_modes=frozenset({"human"}),
        input_schema_reference=record.input_schema_reference,
        output_schema_reference=record.output_schema_reference,
        invoking_roles=record.invoking_roles,
        approval=record.approval,
        evidence=record.evidence,
        dependencies=record.dependencies,
        idempotency_behavior=record.idempotency_behavior,
        idempotency_key_required=record.idempotency_key_required,
        timeout_seconds=record.timeout_seconds,
        maximum_attempts=record.maximum_attempts,
        failure_behavior=record.failure_behavior,
        tenant_isolation_required=(
            record.tenant_isolation_required
        ),
        client_isolation_required=(
            record.client_isolation_required
        ),
        stewardship=record.stewardship,
        created_at=record.created_at,
        metadata=record.metadata,
    )

    result = engine(
        registered_capability=record,
        registered_provider=provider(),
    ).resolve(request())

    assert result.outcome is ResolutionOutcome.UNRESOLVED
    assert (
        result.capability_status
        is CapabilityResolutionStatus.EXECUTION_MODE_PROHIBITED
    )
    assert result.reason_codes == ("execution_mode_prohibited",)
    assert result.execution_plan is None


def test_pilot_capability_requires_explicit_permission() -> None:
    pilot = capability(
        lifecycle=CapabilityLifecycle.PILOT
    )

    denied = engine(
        registered_capability=pilot,
        registered_provider=provider(),
    ).resolve(
        request(capability_version="1.0")
    )

    allowed = engine(
        registered_capability=pilot,
        registered_provider=provider(),
    ).resolve(
        request(
            capability_version="1.0",
            allow_pilot_capability=True,
        )
    )

    assert denied.outcome is ResolutionOutcome.UNRESOLVED
    assert (
        denied.capability_status
        is CapabilityResolutionStatus.INELIGIBLE_LIFECYCLE
    )
    assert allowed.outcome is ResolutionOutcome.RESOLVED


def test_pilot_provider_requires_explicit_permission() -> None:
    pilot_provider = provider(
        approval=ProviderApproval.PILOT
    )

    denied = engine(
        registered_capability=capability(),
        registered_provider=pilot_provider,
    ).resolve(request())

    allowed = engine(
        registered_capability=capability(),
        registered_provider=pilot_provider,
    ).resolve(
        request(allow_pilot_provider=True)
    )

    assert denied.outcome is ResolutionOutcome.UNRESOLVED
    assert denied.reason_codes == ("no_eligible_provider",)
    assert allowed.outcome is ResolutionOutcome.RESOLVED
