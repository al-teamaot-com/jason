from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.execution_providers import (
    DuplicateProviderError,
    ExecutionProvider,
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderCandidateQuery,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderNotFoundError,
    ProviderStewardship,
    ProviderType,
)


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def provider(
    *,
    provider_id: str = "hosted-primary",
    lifecycle: ProviderLifecycle = ProviderLifecycle.AVAILABLE,
    health: ProviderHealth = ProviderHealth.HEALTHY,
    approval: ProviderApproval = ProviderApproval.APPROVED,
    capabilities: frozenset[str] = frozenset(
        {"ticket.summary", "ticket.classification"}
    ),
    classifications: frozenset[str] = frozenset(
        {"public", "internal", "confidential"}
    ),
    regions: frozenset[str] = frozenset({"us"}),
    pricing_profile_id: str | None = "pricing-hosted-primary",
) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=provider_id,
        display_name="Hosted Primary",
        provider_type=ProviderType.HOSTED_AI,
        lifecycle_status=lifecycle,
        health_status=health,
        approval_status=approval,
        execution_modes=frozenset({"hosted_ai"}),
        capabilities=capabilities,
        supported_classifications=classifications,
        regions=regions,
        limits=ProviderLimits(
            maximum_context_tokens=128000,
            maximum_output_tokens=16000,
        ),
        features=ProviderFeatures(
            tools=True,
            structured_output=True,
        ),
        pricing_profile_id=pricing_profile_id,
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Approved hosted reasoning provider",
            review_interval_days=90,
            last_reviewed_at=NOW,
            retirement_criteria=(
                "Provider is no longer approved.",
            ),
            vendor_change_sources=(
                "Official provider documentation",
            ),
            operational_owner="platform-operations",
            approval_owner="architecture-authority",
        ),
        created_at=NOW,
    )


def service() -> ExecutionProviderRegistryService:
    return ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )


def test_registers_and_retrieves_provider() -> None:
    registry = service()
    record = provider()

    registry.register(record)

    assert registry.get(record.provider_id) == record
    assert registry.list_all() == (record,)


def test_rejects_duplicate_provider_id() -> None:
    registry = service()
    record = provider()

    registry.register(record)

    with pytest.raises(DuplicateProviderError):
        registry.register(record)


def test_missing_provider_raises_not_found() -> None:
    registry = service()

    with pytest.raises(ProviderNotFoundError):
        registry.get("missing-provider")


def test_available_provider_requires_approved_or_pilot_state() -> None:
    registry = service()

    with pytest.raises(
        ValueError,
        match="approved or pilot",
    ):
        registry.register(
            provider(
                approval=ProviderApproval.BLOCKED,
            )
        )


def test_available_provider_requires_known_health() -> None:
    registry = service()

    with pytest.raises(
        ValueError,
        match="unknown health",
    ):
        registry.register(
            provider(
                health=ProviderHealth.UNKNOWN,
            )
        )


def test_available_provider_requires_pricing_profile() -> None:
    registry = service()

    with pytest.raises(
        ValueError,
        match="pricing profile",
    ):
        registry.register(
            provider(
                pricing_profile_id=None,
            )
        )


def test_candidate_filtering_requires_capability_classification_and_region() -> None:
    registry = service()
    registry.register(provider())

    assert registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
            execution_mode="hosted_ai",
            classification="confidential",
            region="us",
        )
    ) == (provider(),)

    assert registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
            execution_mode="hosted_ai",
            classification="restricted",
            region="us",
        )
    ) == ()


@pytest.mark.parametrize(
    ("health", "include_warning", "expected"),
    [
        (ProviderHealth.HEALTHY, False, True),
        (ProviderHealth.WARNING, False, False),
        (ProviderHealth.WARNING, True, True),
        (ProviderHealth.UNAVAILABLE, True, False),
        (ProviderHealth.MAINTENANCE, True, False),
        (ProviderHealth.UNKNOWN, True, False),
    ],
)
def test_health_controls_candidate_eligibility(
    health: ProviderHealth,
    include_warning: bool,
    expected: bool,
) -> None:
    registry = service()
    record = provider(
        lifecycle=ProviderLifecycle.PLANNED,
        health=health,
    )
    registry.register(record)
    registry.set_lifecycle(
        provider_id=record.provider_id,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    result = registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
            include_warning=include_warning,
        )
    )

    assert bool(result) is expected


def test_pilot_provider_requires_explicit_query_permission() -> None:
    registry = service()
    registry.register(
        provider(
            approval=ProviderApproval.PILOT,
        )
    )

    normal = registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
        )
    )
    pilot = registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
            allow_pilot=True,
        )
    )

    assert normal == ()
    assert len(pilot) == 1


def test_deprecated_provider_requires_explicit_query_permission() -> None:
    registry = service()
    registry.register(
        provider(
            lifecycle=ProviderLifecycle.DEPRECATED,
        )
    )

    normal = registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
        )
    )
    deprecated = registry.find_candidates(
        ProviderCandidateQuery(
            capability="ticket.summary",
            include_deprecated=True,
        )
    )

    assert normal == ()
    assert len(deprecated) == 1


def test_health_approval_and_lifecycle_updates_are_reflected() -> None:
    registry = service()
    registry.register(provider())

    updated_health = registry.set_health(
        provider_id="hosted-primary",
        health_status=ProviderHealth.WARNING,
    )
    updated_approval = registry.set_approval(
        provider_id="hosted-primary",
        approval_status=ProviderApproval.PILOT,
    )
    updated_lifecycle = registry.set_lifecycle(
        provider_id="hosted-primary",
        lifecycle_status=ProviderLifecycle.DEPRECATED,
    )

    assert updated_health.health_status is ProviderHealth.WARNING
    assert updated_approval.approval_status is ProviderApproval.PILOT
    assert (
        updated_lifecycle.lifecycle_status
        is ProviderLifecycle.DEPRECATED
    )
    assert registry.get("hosted-primary") == updated_lifecycle
