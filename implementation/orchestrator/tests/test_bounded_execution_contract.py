from __future__ import annotations

from datetime import datetime, timezone

from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)


def test_execution_provider_limit_exposes_governed_maximum_execution_seconds():
    provider = ExecutionProvider(
        provider_id="synthetic-provider",
        display_name="Synthetic Provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"synthetic.resource.read"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset({"us"}),
        limits=ProviderLimits(maximum_execution_seconds=17),
        features=ProviderFeatures(),
        pricing_profile_id=None,
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="bounded execution contract regression",
            review_interval_days=90,
            last_reviewed_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            retirement_criteria=("provider retired",),
        ),
        created_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
    )

    assert provider.limits.maximum_execution_seconds == 17
