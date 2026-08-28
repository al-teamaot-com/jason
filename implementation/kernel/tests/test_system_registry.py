from datetime import datetime, timezone

import pytest

from kernel.system_registry import (
    CredentialReference,
    EntityLifecycle,
    EntityType,
    InMemorySystemRegistry,
    InvalidLifecycleTransitionError,
    Observation,
    RegistryEntity,
    RegistryEntityNotFoundError,
    VerificationOutcome,
)


def entity(
    registry_id: str = "component.jason-runtime",
    *,
    lifecycle_status: EntityLifecycle = EntityLifecycle.REGISTERED,
    dependencies: frozenset[str] = frozenset(),
) -> RegistryEntity:
    return RegistryEntity(
        registry_id=registry_id,
        entity_type=EntityType.COMPONENT,
        display_name=registry_id,
        environment="production",
        lifecycle_status=lifecycle_status,
        declared_state={"service_state": "running", "network": "jason"},
        dependencies=dependencies,
        verification_methods=("runtime-health",),
        steward="technology-steward",
        authority_references=("J-002 Article XIX",),
        credential_references=(
            CredentialReference(
                provider="openbao",
                reference="jason/runtime",
            ),
        ),
    )


def now() -> datetime:
    return datetime(2026, 8, 11, 15, 30, tzinfo=timezone.utc)


def test_registry_keeps_declared_state_separate_from_observation() -> None:
    registry = InMemorySystemRegistry()
    declared = entity()
    registry.register(declared)

    registry.record_observation(
        Observation(
            registry_id=declared.registry_id,
            source="runtime-observer",
            observed_at=now(),
            observed_state={"service_state": "stopped", "network": "jason"},
        )
    )

    assert registry.get(declared.registry_id).declared_state["service_state"] == "running"
    assert registry.latest_observation(declared.registry_id).observed_state[
        "service_state"
    ] == "stopped"


def test_registry_detects_drift_without_mutating_declared_state() -> None:
    registry = InMemorySystemRegistry()
    declared = entity()
    registry.register(declared)
    registry.record_observation(
        Observation(
            registry_id=declared.registry_id,
            source="runtime-observer",
            observed_at=now(),
            observed_state={"service_state": "stopped", "network": "jason"},
            evidence_references=("evidence://health/123",),
        )
    )

    verification = registry.verify_from_latest_observation(
        registry_id=declared.registry_id,
        method="runtime-health",
        verified_at=now(),
    )

    assert verification.outcome is VerificationOutcome.DRIFTED
    assert registry.get(declared.registry_id).declared_state["service_state"] == "running"


def test_missing_observed_fields_are_unverified_not_assumed_success() -> None:
    registry = InMemorySystemRegistry()
    declared = entity()
    registry.register(declared)
    registry.record_observation(
        Observation(
            registry_id=declared.registry_id,
            source="runtime-observer",
            observed_at=now(),
            observed_state={"service_state": "running"},
        )
    )

    verification = registry.verify_from_latest_observation(
        registry_id=declared.registry_id,
        method="runtime-health",
        verified_at=now(),
    )

    assert verification.outcome is VerificationOutcome.UNVERIFIED


def test_active_lifecycle_requires_successful_verification() -> None:
    registry = InMemorySystemRegistry()
    declared = entity(lifecycle_status=EntityLifecycle.CONFIGURED)
    registry.register(declared)

    with pytest.raises(InvalidLifecycleTransitionError):
        registry.transition_lifecycle(
            registry_id=declared.registry_id,
            lifecycle_status=EntityLifecycle.VERIFIED,
        )

    registry.record_observation(
        Observation(
            registry_id=declared.registry_id,
            source="runtime-observer",
            observed_at=now(),
            observed_state={"service_state": "running", "network": "jason"},
        )
    )
    verification = registry.verify_from_latest_observation(
        registry_id=declared.registry_id,
        method="runtime-health",
        verified_at=now(),
    )
    assert verification.outcome is VerificationOutcome.VERIFIED

    registry.transition_lifecycle(
        registry_id=declared.registry_id,
        lifecycle_status=EntityLifecycle.VERIFIED,
    )
    active = registry.transition_lifecycle(
        registry_id=declared.registry_id,
        lifecycle_status=EntityLifecycle.ACTIVE,
    )
    assert active.lifecycle_status is EntityLifecycle.ACTIVE


def test_secret_bearing_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="Secret-bearing fields"):
        RegistryEntity(
            registry_id="provider.example",
            entity_type=EntityType.PROVIDER,
            display_name="Example provider",
            environment="production",
            lifecycle_status=EntityLifecycle.REGISTERED,
            declared_state={"api_token": "must-not-be-here"},
            dependencies=frozenset(),
            verification_methods=("provider-health",),
            steward="technology-steward",
        )


def test_dependencies_must_be_registered_and_reverse_lookup_is_available() -> None:
    registry = InMemorySystemRegistry()

    dependent = entity(
        "component.openclaw",
        dependencies=frozenset({"component.jason-runtime"}),
    )

    with pytest.raises(RegistryEntityNotFoundError):
        registry.register(dependent)

    registry.register(entity("component.jason-runtime"))
    registry.register(dependent)

    assert [item.registry_id for item in registry.dependents_of("component.jason-runtime")] == [
        "component.openclaw"
    ]
