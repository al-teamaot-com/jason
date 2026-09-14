from datetime import datetime, timezone

from kernel.execution_providers.contracts import (
    ExecutionProvider,
    ProviderApproval,
    ProviderCandidateQuery,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.execution_providers.repository import InMemoryExecutionProviderRegistry


CAPABILITY = "provider.resource.search"


def provider(provider_id: str) -> ExecutionProvider:
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=provider_id,
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({CAPABILITY}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(maximum_execution_seconds=30),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="external-zero",
        stewardship=ProviderStewardship(
            technology_steward="Jason Architecture Authority",
            business_justification="Test governed provider-resource affinity.",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("provider resource execution is retired",),
        ),
        created_at=now,
    )


def test_required_provider_affinity_selects_only_the_catalog_bound_provider():
    registry = InMemoryExecutionProviderRegistry()
    registry.register(provider("provider_a"))
    registry.register(provider("provider_b"))

    matches = registry.find_candidates(
        ProviderCandidateQuery(
            capability=CAPABILITY,
            execution_mode="deterministic",
            classification="internal",
            required_provider_id="provider_b",
        )
    )

    assert [item.provider_id for item in matches] == ["provider_b"]


def test_missing_required_provider_fails_closed_instead_of_falling_back():
    registry = InMemoryExecutionProviderRegistry()
    registry.register(provider("provider_a"))

    matches = registry.find_candidates(
        ProviderCandidateQuery(
            capability=CAPABILITY,
            execution_mode="deterministic",
            classification="internal",
            required_provider_id="not_registered",
        )
    )

    assert matches == ()
