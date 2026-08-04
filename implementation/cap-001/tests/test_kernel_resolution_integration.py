from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from jason_cap_001.resolution import (
    Cap001KernelResolutionAdapter,
)

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
    GovernedCapabilityResolutionEngine,
)


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def investigation_request() -> dict:
    return {
        "schema_version": "0.1",
        "request_id": "req-kernel-1",
        "correlation_id": "corr-kernel-1",
        "execution_context": {
            "context_id": "ctx-kernel-1",
            "requester_id": "tech-1",
            "organization_id": "aot",
            "client_id": "client-1",
            "capability": "operations.ticket.investigate",
            "maximum_mode": "recommend",
            "execution_mode": "deterministic",
            "expires_at": "2026-08-05T14:00:00Z",
        },
        "ticket": {
            "provider": "fixture",
            "external_id": "ticket-1",
            "title": "Diagnostic warning",
            "description": "Review the diagnostic evidence.",
            "client_id": "client-1",
            "configuration_item_id": None,
            "requester_identity_id": None,
            "created_at": "2026-08-04T13:00:00Z",
            "attachments": [],
        },
        "requested_depth": "standard",
    }


def capability_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name="operations.ticket.investigate",
        version="0.1",
        display_name="Professional Ticket Investigation",
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose=(
            "Produce an evidence-grounded, read-only ticket "
            "investigation recommendation."
        ),
        owner_service="CAP-001 Professional Ticket Investigation",
        architectural_capability_ids=frozenset(
            {
                "JAC-001",
                "JAC-004",
                "JAC-005",
                "JAC-006",
                "JAC-008",
            }
        ),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset(
            {"deterministic"}
        ),
        input_schema_reference=(
            "schema://operations.ticket.investigate/input/0.1"
        ),
        output_schema_reference=(
            "schema://operations.ticket.investigate/output/0.1"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authorized ticket",
                "client-scoped evidence",
                "structured reasoning result",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=(
            IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT
        ),
        idempotency_key_required=True,
        timeout_seconds=300,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without collecting evidence or producing "
            "a recommendation."
        ),
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="architecture-authority",
            business_justification=(
                "Ticket investigation is the first governed "
                "end-to-end Jason capability."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by an approved equivalent capability.",
            ),
        ),
        created_at=NOW,
    )


def provider_definition() -> ExecutionProvider:
    return ExecutionProvider(
        provider_id="cap-001-deterministic-pilot",
        display_name="CAP-001 Deterministic Pilot",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {"operations.ticket.investigate"}
        ),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_execution_seconds=300,
        ),
        features=ProviderFeatures(
            structured_output=True,
        ),
        pricing_profile_id="cap-001-zero-cost-pilot",
        stewardship=ProviderStewardship(
            technology_steward="architecture-authority",
            business_justification=(
                "Provides the deterministic pilot execution path "
                "for CAP-001."
            ),
            review_interval_days=90,
            last_reviewed_at=NOW,
            retirement_criteria=(
                "Replaced by an approved production provider.",
            ),
        ),
        created_at=NOW,
    )


def resolution_adapter() -> Cap001KernelResolutionAdapter:
    capability_registry = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    provider_registry = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    capability_registry.register(capability_definition())
    provider_registry.register(provider_definition())

    policy = ExecutionPolicyEngine(
        cost_estimator=CostEstimator(
            InMemoryPricingRegistry()
        )
    )

    engine = GovernedCapabilityResolutionEngine(
        capabilities=capability_registry,
        providers=provider_registry,
        policy=policy,
    )

    return Cap001KernelResolutionAdapter(engine)


def test_cap_001_resolves_through_real_kernel() -> None:
    authorization = resolution_adapter().authorize(
        investigation_request(),
        authority_allowed=True,
    )

    plan = authorization.execution_plan

    assert plan is not None
    assert plan.capability == "operations.ticket.investigate"
    assert plan.capability_version == "0.1"
    assert plan.provider_id == "cap-001-deterministic-pilot"
    assert plan.execution_mode.value == "deterministic"
    assert plan.tenant_id == "aot"
    assert plan.client_id == "client-1"
    assert plan.policy_ids == ("cap-001-read-only-v0.1",)


def test_cap_001_real_kernel_denies_missing_authority() -> None:
    adapter = resolution_adapter()

    try:
        adapter.authorize(
            investigation_request(),
            authority_allowed=False,
        )
    except PermissionError as error:
        assert "authority_denied" in str(error)
    else:
        raise AssertionError(
            "Kernel resolution unexpectedly allowed CAP-001."
        )
