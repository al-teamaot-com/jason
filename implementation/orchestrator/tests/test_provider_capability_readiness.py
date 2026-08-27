from datetime import datetime, timezone

import pytest

from orchestrator.provider_capability_readiness import (
    ProviderCapabilityObservation,
    ProviderCapabilityReadiness,
    ReadinessDimension,
    ReadinessReason,
    ReadinessState,
    classify_readiness,
    evaluate_transition,
)


NOW = datetime(
    2026,
    8,
    24,
    10,
    0,
    tzinfo=timezone.utc,
)


def healthy_dimension():
    return ReadinessDimension(
        checked=True,
        healthy=True,
    )


def observation(
    *,
    component=None,
    reachability=None,
    authentication=None,
    capability=None,
    provider_status_code=None,
):
    return ProviderCapabilityObservation(
        provider_id="provider.example",
        capability_name="example.read",
        observed_at=NOW,
        component=component or healthy_dimension(),
        reachability=reachability or healthy_dimension(),
        authentication=authentication or healthy_dimension(),
        capability=capability or healthy_dimension(),
        evidence_source="governed-readiness-probe",
        probe_version="1",
        provider_status_code=provider_status_code,
    )


def test_all_four_dimensions_are_required_for_healthy():
    result = classify_readiness(
        observation()
    )

    assert result.state is ReadinessState.HEALTHY
    assert result.reason is ReadinessReason.NONE


def test_unchecked_capability_readiness_is_not_assumed_healthy():
    result = classify_readiness(
        observation(
            capability=ReadinessDimension(
                checked=False,
                healthy=None,
            )
        )
    )

    assert result.state is ReadinessState.UNKNOWN


def test_quota_exhaustion_marks_provider_capability_unavailable():
    result = classify_readiness(
        observation(
            capability=ReadinessDimension(
                checked=True,
                healthy=False,
                reason=ReadinessReason.QUOTA_EXHAUSTED,
            ),
            provider_status_code="429",
        )
    )

    assert result.state is ReadinessState.UNAVAILABLE
    assert result.reason is ReadinessReason.QUOTA_EXHAUSTED
    assert result.provider_status_code == "429"


def test_authentication_success_does_not_override_capability_failure():
    result = classify_readiness(
        observation(
            authentication=healthy_dimension(),
            capability=ReadinessDimension(
                checked=True,
                healthy=False,
                reason=ReadinessReason.QUOTA_EXHAUSTED,
            ),
        )
    )

    assert result.state is ReadinessState.UNAVAILABLE
    assert result.reason is ReadinessReason.QUOTA_EXHAUSTED


def test_runtime_failure_is_distinct_from_provider_failure():
    result = classify_readiness(
        observation(
            component=ReadinessDimension(
                checked=True,
                healthy=False,
                reason=ReadinessReason.RUNTIME_UNHEALTHY,
            )
        )
    )

    assert result.state is ReadinessState.UNAVAILABLE
    assert result.reason is ReadinessReason.RUNTIME_UNHEALTHY


def test_first_unavailable_observation_alerts():
    current = classify_readiness(
        observation(
            capability=ReadinessDimension(
                checked=True,
                healthy=False,
                reason=ReadinessReason.QUOTA_EXHAUSTED,
            )
        )
    )

    transition = evaluate_transition(
        previous=None,
        current=current,
    )

    assert transition.changed is True
    assert transition.should_alert is True
    assert transition.recovery is False


def test_same_unavailable_state_does_not_repeat_alert():
    previous = ProviderCapabilityReadiness(
        provider_id="provider.example",
        capability_name="example.read",
        state=ReadinessState.UNAVAILABLE,
        reason=ReadinessReason.QUOTA_EXHAUSTED,
        observed_at=NOW,
        evidence_source="probe",
        provider_status_code="429",
    )

    current = ProviderCapabilityReadiness(
        provider_id="provider.example",
        capability_name="example.read",
        state=ReadinessState.UNAVAILABLE,
        reason=ReadinessReason.QUOTA_EXHAUSTED,
        observed_at=NOW,
        evidence_source="probe",
        provider_status_code="429",
    )

    transition = evaluate_transition(
        previous=previous,
        current=current,
    )

    assert transition.changed is False
    assert transition.should_alert is False


def test_recovery_transition_alerts():
    previous = ProviderCapabilityReadiness(
        provider_id="provider.example",
        capability_name="example.read",
        state=ReadinessState.UNAVAILABLE,
        reason=ReadinessReason.QUOTA_EXHAUSTED,
        observed_at=NOW,
        evidence_source="probe",
    )

    current = classify_readiness(
        observation()
    )

    transition = evaluate_transition(
        previous=previous,
        current=current,
    )

    assert transition.changed is True
    assert transition.should_alert is True
    assert transition.recovery is True


def test_transition_cannot_change_provider_identity():
    previous = ProviderCapabilityReadiness(
        provider_id="provider.other",
        capability_name="example.read",
        state=ReadinessState.HEALTHY,
        reason=ReadinessReason.NONE,
        observed_at=NOW,
        evidence_source="probe",
    )

    current = classify_readiness(
        observation()
    )

    with pytest.raises(
        ValueError,
        match="provider identity",
    ):
        evaluate_transition(
            previous=previous,
            current=current,
        )


def test_healthy_dimension_cannot_contain_failure_reason():
    with pytest.raises(
        ValueError,
        match="healthy readiness dimension",
    ):
        ReadinessDimension(
            checked=True,
            healthy=True,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
        )
